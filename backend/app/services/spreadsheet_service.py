from __future__ import annotations

import base64
import json
import time
import unicodedata
from copy import deepcopy
from threading import Lock
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from backend.app.config import get_settings
from backend.app.models import Solicitud


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
_requests_lock = Lock()
_requests_cache = None
SHEET_CACHE_SECONDS = 60


def invalidate_sheet_requests() -> None:
    global _requests_cache
    with _requests_lock:
        _requests_cache = None


class SpreadsheetConfigError(RuntimeError):
    pass


def append_review_to_spreadsheet(solicitud: Solicitud) -> None:
    settings = get_settings()
    if not settings.google_sheets_enabled:
        return
    if not settings.google_sheets_spreadsheet_id:
        raise SpreadsheetConfigError("Falta GOOGLE_SHEETS_SPREADSHEET_ID.")

    credentials = load_service_account_credentials(
        settings.google_service_account_json,
        settings.google_service_account_file,
    )
    access_token = fetch_access_token(credentials)
    append_values(
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
        sheet_name=settings.google_sheets_sheet_name,
        access_token=access_token,
        row=build_review_row(solicitud),
    )


def update_sheet_request_from_solicitud(solicitud: Solicitud) -> None:
    datos = solicitud.datos or {}
    origin = datos.get("origenGoogleSheet") or {}
    row_number = origin.get("rowNumber")
    if not row_number:
        return
    if isinstance(row_number, bool) or not str(row_number).isdigit() or int(row_number) < 2:
        raise SpreadsheetConfigError("La fila de origen de Google Sheets no es valida.")
    settings = get_settings()
    if not settings.google_sheets_enabled:
        raise SpreadsheetConfigError("Google Sheets no esta habilitado.")
    if not settings.google_sheets_spreadsheet_id:
        raise SpreadsheetConfigError("Falta GOOGLE_SHEETS_SPREADSHEET_ID.")

    credentials = load_service_account_credentials(
        settings.google_service_account_json,
        settings.google_service_account_file,
    )
    access_token = fetch_access_token(credentials)
    update_values(
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
        sheet_name=settings.google_sheets_sheet_name,
        access_token=access_token,
        row_number=int(row_number),
        row=build_sheet_request_row(solicitud),
    )


def list_sheet_requests(force_refresh: bool = False) -> list[dict]:
    global _requests_cache
    settings = get_settings()
    key = (settings.google_sheets_enabled, settings.google_sheets_spreadsheet_id, settings.google_sheets_sheet_name,
           settings.google_service_account_file, settings.google_service_account_json)
    # Una sola lectura concurrente evita multiplicar llamadas a Google.
    with _requests_lock:
        if force_refresh or _requests_cache is None or _requests_cache[0] != key or time.monotonic() >= _requests_cache[1]:
            requests = _read_sheet_requests()
            _requests_cache = (key, time.monotonic() + SHEET_CACHE_SECONDS, requests)
        return deepcopy(_requests_cache[2])


def list_sheet_requests_page(page: int = 1, page_size: int = 50, query: str = "", force_refresh: bool = False) -> dict:
    requests = list_sheet_requests(force_refresh=force_refresh)
    requests.sort(key=lambda item: item["sheet_row_number"], reverse=True)
    terms = remove_accents(query.casefold()).split()
    if terms:
        requests = [item for item in requests if all(term in remove_accents(" ".join([
            item.get("nombre_completo") or "", item.get("correo_electronico") or "",
            item.get("curp") or "", str(item.get("sheet_row_number", "")),
            (item.get("datos") or {}).get("telefono") or "",
        ]).casefold()) for term in terms)]
    total = len(requests)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    fields = ("id", "nombre_completo", "correo_electronico", "curp", "created_at", "source", "sheet_row_number")
    items = [{field: item.get(field) for field in fields} for item in requests[(page - 1) * page_size:page * page_size]]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


def _read_sheet_requests() -> list[dict]:
    settings = get_settings()
    if not settings.google_sheets_enabled:
        raise SpreadsheetConfigError("Google Sheets no esta habilitado.")
    if not settings.google_sheets_spreadsheet_id:
        raise SpreadsheetConfigError("Falta GOOGLE_SHEETS_SPREADSHEET_ID.")

    credentials = load_service_account_credentials(
        settings.google_service_account_json,
        settings.google_service_account_file,
    )
    access_token = fetch_access_token(credentials)
    values = get_values(
        spreadsheet_id=settings.google_sheets_spreadsheet_id,
        sheet_name=settings.google_sheets_sheet_name,
        access_token=access_token,
    )
    return sheet_values_to_requests(values)


def load_service_account_credentials(raw_json: str | None, file_path: Path | None) -> dict:
    if raw_json:
        return json.loads(raw_json)
    if file_path:
        return json.loads(file_path.read_text(encoding="utf-8"))
    raise SpreadsheetConfigError("Falta GOOGLE_SERVICE_ACCOUNT_FILE o GOOGLE_SERVICE_ACCOUNT_JSON.")


def fetch_access_token(credentials: dict) -> str:
    private_key = credentials.get("private_key")
    client_email = credentials.get("client_email")
    if not private_key or not client_email:
        raise SpreadsheetConfigError("La cuenta de servicio no tiene private_key o client_email.")

    token_uri = credentials.get("token_uri") or GOOGLE_TOKEN_URI
    now = int(time.time())
    claim = {
        "iss": client_email,
        "scope": SHEETS_SCOPE,
        "aud": token_uri,
        "iat": now,
        "exp": now + 3600,
    }
    assertion = sign_jwt({"alg": "RS256", "typ": "JWT"}, claim, private_key)
    response = httpx.post(
        token_uri,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=20,
    )
    raise_for_google_error(response)
    payload = response.json()
    return payload["access_token"]


def sign_jwt(header: dict, claim: dict, private_key_pem: str) -> str:
    signing_input = ".".join(
        [
            base64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            base64url(json.dumps(claim, separators=(",", ":")).encode("utf-8")),
        ]
    ).encode("ascii")
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode('ascii')}.{base64url(signature)}"


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def append_values(spreadsheet_id: str, sheet_name: str, access_token: str, row: list[str]) -> None:
    escaped_sheet_name = sheet_name.replace("'", "''")
    range_name = f"'{escaped_sheet_name}'!A1"
    encoded_range = quote(range_name, safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}:append"
    response = httpx.post(
        url,
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        headers={"Authorization": f"Bearer {access_token}"},
        json={"values": [row]},
        timeout=20,
    )
    raise_for_google_error(response)
    invalidate_sheet_requests()


def update_values(spreadsheet_id: str, sheet_name: str, access_token: str, row_number: int, row: list[str]) -> None:
    escaped_sheet_name = sheet_name.replace("'", "''")
    range_name = f"'{escaped_sheet_name}'!A{row_number}:P{row_number}"
    encoded_range = quote(range_name, safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}"
    response = httpx.put(
        url,
        params={"valueInputOption": "RAW"},
        headers={"Authorization": f"Bearer {access_token}"},
        json={"values": [row]},
        timeout=20,
    )
    raise_for_google_error(response)
    invalidate_sheet_requests()


def get_values(spreadsheet_id: str, sheet_name: str, access_token: str) -> list[list[str]]:
    escaped_sheet_name = sheet_name.replace("'", "''")
    range_name = f"'{escaped_sheet_name}'!A:P"
    encoded_range = quote(range_name, safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}"
    response = httpx.get(
        url,
        params={"majorDimension": "ROWS"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    raise_for_google_error(response)
    return response.json().get("values", [])


def raise_for_google_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    message = response.text
    try:
        message = response.json().get("error", {}).get("message") or message
    except ValueError:
        pass
    raise SpreadsheetConfigError(f"Google Sheets respondio {response.status_code}: {message}")


def build_review_row(solicitud: Solicitud) -> list[str]:
    datos = solicitud.datos or {}
    domicilio = datos.get("domicilio") or {}
    return [
        format_datetime(datetime.utcnow()),
        text(solicitud.folio),
        text(solicitud.id),
        text(solicitud.estado),
        text(solicitud.nombre_completo or datos.get("nombreCompleto")),
        text(solicitud.curp or datos.get("curp")),
        text(solicitud.correo_electronico or datos.get("correoElectronico")),
        text(datos.get("telefono")),
        text(datos.get("rfc")),
        text(datos.get("claveCobro")),
        text(datos.get("descripcionClave")),
        text(datos.get("estadoCivil")),
        text(format_address(domicilio)),
        text(solicitud.revisado_por),
        format_datetime(solicitud.revisado_at),
        format_datetime(solicitud.created_at),
        text(solicitud.notas_operador),
    ]


def build_sheet_request_row(solicitud: Solicitud) -> list[str]:
    datos = solicitud.datos or {}
    origin = datos.get("origenGoogleSheet") or {}
    referencias = datos.get("referencias") or []
    return [
        text(origin.get("timestamp") or format_datetime(solicitud.created_at)),
        text(solicitud.nombre_completo or datos.get("nombreCompleto")),
        text((datos.get("rasgos") or {}).get("estatura")),
        text(datos.get("estadoCivil")),
        text(datos.get("nombreConyuge")),
        text(format_address(datos.get("domicilio") or {})),
        text(solicitud.correo_electronico or datos.get("correoElectronico")),
        text(datos.get("telefono")),
        text(reference_name(referencias, 0)),
        text(reference_address(referencias, 0)),
        text(reference_name(referencias, 1)),
        text(reference_address(referencias, 1)),
        text(reference_name(referencias, 2)),
        text(reference_address(referencias, 2)),
        text(reference_name(referencias, 3)),
        text(reference_address(referencias, 3)),
    ]


def reference_name(references: list, index: int) -> str:
    if index >= len(references) or not isinstance(references[index], dict):
        return ""
    return text(references[index].get("nombre"))


def reference_address(references: list, index: int) -> str:
    if index >= len(references) or not isinstance(references[index], dict):
        return ""
    return format_address(references[index].get("domicilio") or {})


SHEET_HEADERS = {
    "timestamp": "Marca temporal",
    "nombre": "NOMBRE COMPLETO (apellido paterno, apellido materno, nombre/s)",
    "estatura": "ESTATURA",
    "estado_civil": "ESTADO CIVIL",
    "conyuge": "NOMBRE DEL CONYUGE  (apellido paterno, apellido materno, nombre/s)",
    "domicilio": "DOMICILIO COMPLETO (calle, numero, colonia o población, municipio, estado, código postal) ",
    "correo": "CORREO ELECTRONICO",
    "telefono": "NUMERO DE TELEFONO",
    "conocido_1_nombre": "REFERENCIA 1: PERSONA CONOCIDA - NOMBRE  (apellido paterno, apellido materno, nombre/s)",
    "conocido_1_domicilio": "REFERENCIA 1: PERSONA CONOCIDA -  DOMICILIO COMPLETO (calle, numero, colonia o población, municipio, estado)",
    "conocido_2_nombre": "REFERENCIA 2: PERSONA CONOCIDA - NOMBRE  (apellido paterno, apellido materno, nombre/s)",
    "conocido_2_domicilio": "REFERENCIA 2: PERSONA CONOCIDA -  DOMICILIO COMPLETO (calle, numero, colonia o población, municipio, estado)",
    "familiar_1_nombre": "REFERENCIA 1: FAMILIAR - NOMBRE  (apellido paterno, apellido materno, nombre/s)",
    "familiar_1_domicilio": "REFERENCIA 1: FAMILIAR - DOMICILIO COMPLETO (calle, numero, colonia o población, municipio, estado)",
    "familiar_2_nombre": "REFERENCIA 2: FAMILIAR - NOMBRE  (apellido paterno, apellido materno, nombre/s)",
    "familiar_2_domicilio": "REFERENCIA 2: FAMILIAR -  DOMICILIO COMPLETO (calle, numero, colonia o población, municipio, estado)",
}


def sheet_values_to_requests(values: list[list[str]]) -> list[dict]:
    if not values:
        return []
    headers = [normalize_header(header) for header in values[0]]
    requests = []
    for index, row in enumerate(values[1:], start=2):
        row_data = {
            header: row[column].strip() if column < len(row) else ""
            for column, header in enumerate(headers)
            if header
        }
        if not any(row_data.values()):
            continue
        request = sheet_row_to_request(row_data, index)
        requests.append(request)
    return requests


def sheet_row_to_request(row: dict[str, str], row_number: int) -> dict:
    nombre = upper_text(row.get(normalize_header(SHEET_HEADERS["nombre"]), ""))
    correo = row.get(normalize_header(SHEET_HEADERS["correo"]), "")
    timestamp = clean_spaces(row.get(normalize_header(SHEET_HEADERS["timestamp"]), ""))
    conyuge = upper_text(row.get(normalize_header(SHEET_HEADERS["conyuge"]), ""))
    datos = {
        "nombreCompleto": nombre,
        "nombrePartes": split_stored_name(nombre),
        "correoElectronico": correo,
        "telefono": row.get(normalize_header(SHEET_HEADERS["telefono"]), ""),
        "estadoCivil": normalize_civil_status(row.get(normalize_header(SHEET_HEADERS["estado_civil"]), "")),
        "nombreConyuge": conyuge,
        "conyugeNombrePartes": split_stored_name(conyuge),
        "domicilio": parse_sheet_address(row.get(normalize_header(SHEET_HEADERS["domicilio"]), "")),
        "referencias": [
            sheet_reference(row, "conocido_1_nombre", "conocido_1_domicilio", "Conocido"),
            sheet_reference(row, "conocido_2_nombre", "conocido_2_domicilio", "Conocido"),
            sheet_reference(row, "familiar_1_nombre", "familiar_1_domicilio", "Familiar"),
            sheet_reference(row, "familiar_2_nombre", "familiar_2_domicilio", "Familiar"),
        ],
        "rasgos": {"estatura": upper_text(row.get(normalize_header(SHEET_HEADERS["estatura"]), ""))},
        "origenGoogleSheet": {"rowNumber": row_number, "timestamp": timestamp},
    }
    return {
        "id": f"sheet-row-{row_number}",
        "estado": "pendiente",
        "curp": None,
        "nombre_completo": nombre or None,
        "correo_electronico": correo or None,
        "datos": datos,
        "extracciones": [],
        "notas_operador": None,
        "revisado_por": None,
        "revisado_at": None,
        "created_at": parse_sheet_datetime(timestamp),
        "source": "google_sheet",
        "sheet_row_number": row_number,
    }


def sheet_reference(row: dict[str, str], name_key: str, address_key: str, relationship: str) -> dict:
    name = upper_text(row.get(normalize_header(SHEET_HEADERS[name_key]), ""))
    return {
        "nombre": name,
        "nombrePartes": split_stored_name(name),
        "domicilio": parse_sheet_address(row.get(normalize_header(SHEET_HEADERS[address_key]), "")),
        "parentesco": relationship,
    }


def parse_sheet_address(value: str) -> dict:
    return {
        "completo": value,
        "calle": "",
        "numeroExterior": "",
        "numeroInterior": "",
        "colonia": "",
        "municipio": "",
        "estado": "",
        "cp": "",
    }


def split_stored_name(value: str) -> dict:
    return {"apellidos": "", "nombres": clean_spaces(value)}


def parse_sheet_datetime(value: str) -> str:
    clean = clean_spaces(value)
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(clean, fmt).isoformat()
        except ValueError:
            pass
    return datetime.utcnow().isoformat()


def normalize_header(value: str) -> str:
    return clean_spaces(value).upper()


def clean_spaces(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def upper_text(value: str) -> str:
    return clean_spaces(value).upper()


def normalize_civil_status(value: str) -> str:
    normalized = remove_accents(upper_text(value)).replace("�", "O")
    if normalized in {"SOLTEROS", "SOTERO"}:
        return "SOLTERO"
    if normalized.startswith("UNI") and "LIBRE" in normalized:
        return "UNION LIBRE"
    if normalized in {"SOLTERO", "SOLTERA", "CASADO", "CASADA"}:
        return normalized
    return normalized


def remove_accents(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )


def format_address(address: dict) -> str:
    if address.get("completo") is not None:
        return str(address["completo"])
    parts = [
        address.get("calle"),
        f"No. {address.get('numeroExterior')}" if address.get("numeroExterior") else "",
        f"Int. {address.get('numeroInterior')}" if address.get("numeroInterior") else "",
        address.get("colonia"),
        address.get("municipio"),
        address.get("estado"),
        f"C.P. {address.get('cp')}" if address.get("cp") else "",
    ]
    return ", ".join(str(part).strip() for part in parts if part)


def restore_complete_sheet_addresses(datos: dict, sheet_data: dict) -> dict:
    restored = deepcopy(datos)
    address = restored.get("domicilio")
    source = sheet_data.get("domicilio") or {}
    if isinstance(address, dict) and "completo" not in address and "completo" in source:
        restored["domicilio"] = deepcopy(source)
    for index, reference in enumerate(restored.get("referencias") or []):
        sheet_references = sheet_data.get("referencias") or []
        if index >= len(sheet_references):
            break
        address = reference.get("domicilio")
        source = sheet_references[index].get("domicilio") or {}
        if isinstance(address, dict) and "completo" not in address and "completo" in source:
            reference["domicilio"] = deepcopy(source)
    return restored


def format_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def text(value) -> str:
    return "" if value is None else str(value)

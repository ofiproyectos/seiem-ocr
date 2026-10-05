from __future__ import annotations

import base64
import json
import time
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
    response.raise_for_status()
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
    response.raise_for_status()


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


def format_address(address: dict) -> str:
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


def format_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def text(value) -> str:
    return "" if value is None else str(value)

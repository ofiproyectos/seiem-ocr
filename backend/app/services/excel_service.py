from __future__ import annotations

from datetime import datetime
from pathlib import Path
from re import DOTALL, compile, escape as re_escape, match, sub
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from backend.app.config import get_settings


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

MONTHS = {
    "01": "ENERO",
    "02": "FEBRERO",
    "03": "MARZO",
    "04": "ABRIL",
    "05": "MAYO",
    "06": "JUNIO",
    "07": "JULIO",
    "08": "AGOSTO",
    "09": "SEPTIEMBRE",
    "10": "OCTUBRE",
    "11": "NOVIEMBRE",
    "12": "DICIEMBRE",
}


def exportar_filiacion_excel(solicitud_id: str, datos: dict) -> Path:
    settings = get_settings()
    template = settings.filiacion_template_path
    if not template.exists():
        raise FileNotFoundError(f"No se encontro la plantilla Excel: {template}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = settings.export_dir / f"filiacion_{safe_name(datos.get('curp') or solicitud_id)}_{stamp}.xlsx"
    patch_xlsx(template, output, build_cell_values(datos))
    return output


def patch_xlsx(template: Path, output: Path, values: dict[str, str]) -> None:
    with ZipFile(template, "r") as source:
        sheet_path = find_sheet_path(source, "Plantilla")
        shared_strings_path = "xl/sharedStrings.xml"
        shared_xml, indexes = patch_shared_strings(source.read(shared_strings_path), list(values.values()))
        patched_sheet = patch_sheet_xml(source.read(sheet_path), values, indexes)

        with ZipFile(output, "w", ZIP_DEFLATED) as target:
            for item in source.infolist():
                if item.filename == sheet_path:
                    content = patched_sheet
                elif item.filename == shared_strings_path:
                    content = shared_xml
                else:
                    content = source.read(item.filename)
                target.writestr(item, content)


def find_sheet_path(workbook: ZipFile, sheet_name: str) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rels = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")}

    for sheet in workbook_root.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            rel_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = rels[rel_id].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def patch_shared_strings(shared_xml: bytes, strings: list[str]) -> tuple[bytes, dict[str, int]]:
    xml = shared_xml.decode("utf-8")
    base_count = xml.count("<si>")
    original_count_match = compile(r'count="(\d+)"').search(xml)
    original_unique_match = compile(r'uniqueCount="(\d+)"').search(xml)
    original_count = int(original_count_match.group(1)) if original_count_match else base_count
    original_unique = int(original_unique_match.group(1)) if original_unique_match else base_count
    indexes: dict[str, int] = {}
    additions = []

    for value in strings:
        if value in indexes:
            continue
        indexes[value] = base_count + len(additions)
        additions.append(f"<si><t>{xml_escape(value)}</t></si>")

    xml = xml.replace("</sst>", "".join(additions) + "</sst>")
    xml = sub(r'count="\d+"', f'count="{original_count + len(strings)}"', xml, count=1)
    xml = sub(r'uniqueCount="\d+"', f'uniqueCount="{original_unique + len(additions)}"', xml, count=1)
    return xml.encode("utf-8"), indexes


def patch_sheet_xml(sheet_xml: bytes, values: dict[str, str], indexes: dict[str, int]) -> bytes:
    xml = sheet_xml.decode("utf-8")
    for coordinate, value in values.items():
        xml = patch_cell_xml(xml, coordinate, indexes[value])
    return xml.encode("utf-8")


def patch_cell_xml(xml: str, coordinate: str, shared_string_index: int) -> str:
    coordinate_pattern = re_escape(coordinate)
    self_closing_pattern = compile(rf'(<c\b(?=[^>]*\br="{coordinate_pattern}")[^>]*)/>')
    full_pattern = compile(
        rf'(<c\b(?=[^>]*\br="{coordinate_pattern}")[^>]*>)(.*?)(</c>)',
        DOTALL,
    )

    match_self_closing = self_closing_pattern.search(xml)
    if match_self_closing:
        opening = make_shared_string_opening(f"{match_self_closing.group(1)}>")
        replacement = f"{opening}<v>{shared_string_index}</v></c>"
        return f"{xml[:match_self_closing.start()]}{replacement}{xml[match_self_closing.end():]}"

    match_full = full_pattern.search(xml)
    if match_full:
        opening = make_shared_string_opening(match_full.group(1))
        replacement = f"{opening}<v>{shared_string_index}</v></c>"
        return f"{xml[:match_full.start()]}{replacement}{xml[match_full.end():]}"

    return insert_cell_xml(xml, coordinate, shared_string_index)


def insert_cell_xml(xml: str, coordinate: str, shared_string_index: int) -> str:
    column, row_number = split_coordinate(coordinate)
    if not row_number:
        return xml

    row_pattern = compile(rf'(<row\b(?=[^>]*\br="{row_number}")[^>]*>)(.*?)(</row>)', DOTALL)
    row_match = row_pattern.search(xml)
    if not row_match:
        return xml

    target_column_index = column_index(column)
    row_opening, row_body, row_closing = row_match.groups()
    style = find_neighbor_style(row_body, target_column_index, row_number)
    style_attribute = f' s="{style}"' if style else ""
    cell_xml = f'<c r="{coordinate}"{style_attribute} t="s"><v>{shared_string_index}</v></c>'

    cell_pattern = compile(r'<c\b[^>]*\br="([A-Z]+)' + re_escape(row_number) + r'"[^>]*(?:/>|>.*?</c>)', DOTALL)
    insert_at = len(row_body)
    for cell_match in cell_pattern.finditer(row_body):
        if column_index(cell_match.group(1)) > target_column_index:
            insert_at = cell_match.start()
            break

    new_body = f"{row_body[:insert_at]}{cell_xml}{row_body[insert_at:]}"
    replacement = f"{row_opening}{new_body}{row_closing}"
    return f"{xml[:row_match.start()]}{replacement}{xml[row_match.end():]}"


def find_neighbor_style(row_body: str, target_column_index: int, row_number: str) -> str:
    cell_pattern = compile(r'<c\b([^>]*)\br="([A-Z]+)' + re_escape(row_number) + r'"([^>]*)', DOTALL)
    candidates: list[tuple[int, str]] = []
    for cell_match in cell_pattern.finditer(row_body):
        attributes = f"{cell_match.group(1)} {cell_match.group(3)}"
        style_match = compile(r'\bs="(\d+)"').search(attributes)
        if style_match:
            candidates.append((abs(column_index(cell_match.group(2)) - target_column_index), style_match.group(1)))
    if not candidates:
        return ""
    return sorted(candidates, key=lambda item: item[0])[0][1]


def split_coordinate(coordinate: str) -> tuple[str, str]:
    coordinate_match = match(r"^([A-Z]+)(\d+)$", coordinate)
    if not coordinate_match:
        return coordinate, ""
    return coordinate_match.group(1), coordinate_match.group(2)


def column_index(column: str) -> int:
    result = 0
    for char in column:
        result = result * 26 + ord(char) - ord("A") + 1
    return result


def make_shared_string_opening(opening: str) -> str:
    cleaned = sub(r'\s+t="[^"]*"', "", opening)
    cleaned = sub(r"/\s*>$", ">", cleaned)
    return cleaned[:-1] + ' t="s">'


def build_cell_values(datos: dict) -> dict[str, str]:
    domicilio = datos.get("domicilio") or {}
    rasgos = datos.get("rasgos") or {}
    referencias = datos.get("referencias") or []

    values = {
        "B9": datos.get("rfc"),
        "G9": datos.get("curp"),
        "C10": datos.get("claveCobro"),
        "C11": datos.get("descripcionClave"),
        "C12": datos.get("nombreCompleto"),
        "C13": format_date_long(datos.get("fechaNacimiento")),
        "C14": datos.get("lugarNacimiento"),
        "C15": datos.get("padre"),
        "C16": datos.get("madre"),
        "A17": label_value("NO. DE ACTA:", datos.get("noActa")),
        "C17": label_value("AÑO:", valid_year(datos.get("anioActa"))),
        "F17": label_value("LIBRO:", datos.get("libro")),
        "C18": datos.get("cartillaSmn"),
        "G18": datos.get("clase"),
        "B19": datos.get("estadoCivil"),
        "C20": datos.get("nombreConyuge"),
        "B21": format_address(domicilio),
        "C23": datos.get("correoElectronico"),
        "A24": label_value("LUGAR:", datos.get("lugar") or "TOLUCA, MEXICO"),
        "E24": label_value("FECHA:", format_date_long(datos.get("fechaFiliacion"))),
        "C42": rasgos.get("senasVisibles"),
        "M42": rasgos.get("estatura"),
    }

    values.update(reference_values(referencias, 0, "B28", "B29"))
    values.update(reference_values(referencias, 1, "B31", "B32"))
    values.update(reference_values(referencias, 2, "I28", "I29"))
    values.update(reference_values(referencias, 3, "I31", "I32"))
    values.update(option_marks(rasgos.get("tonoPiel"), {"Claro": "B37", "Mediano": "B38", "Obscuro": "B39"}))
    values.update(option_marks(rasgos.get("frente"), {"Pequeña": "F37", "Pequena": "F37", "Mediana": "F38", "Grande": "F39"}))
    values.update(option_marks(rasgos.get("cejas"), {"Abundantes": "H37", "Regulares": "H38", "Escasas": "H39"}))
    values.update(option_marks(rasgos.get("nariz"), {"Cóncava": "M37", "Concava": "M37", "Convexa": "M38", "Rectilínea": "M39", "Rectilinea": "M39"}))
    values.update(option_marks(rasgos.get("boca"), {"Pequeña": "O37", "Pequena": "O37", "Regular": "O38", "Grande": "O39"}))
    values.update(
        option_marks(
            rasgos.get("pelo"),
            {
                "Castaño claro": "D37",
                "Castano claro": "D37",
                "Castaño oscuro": "D38",
                "Castano oscuro": "D38",
                "Negro": "D39",
                "Cano": "D40",
                "Calvo": "D41",
            },
        )
    )
    values.update(
        option_marks(
            rasgos.get("ojos"),
            {
                "Castaño oscuro": "K37",
                "Castano oscuro": "K37",
                "Castaño claro": "K38",
                "Castano claro": "K38",
                "Pardos": "K39",
                "Verdosos": "K40",
                "Azules": "K41",
            },
        )
    )

    return {cell: str(value).upper() for cell, value in values.items() if value not in (None, "")}


def label_value(label: str, value) -> str:
    return f"{label} {value or ''}".strip()


def valid_year(value) -> str:
    text = str(value or "")
    return text if match(r"^(19|20)\d{2}$", text) else ""


def format_address(address: dict) -> str:
    parts = [
        address.get("calle"),
        address.get("numeroExterior"),
        f"INT. {address.get('numeroInterior')}" if address.get("numeroInterior") else "",
        address.get("colonia"),
        address.get("municipio"),
        address.get("estado"),
        f"C.P. {address.get('cp')}" if address.get("cp") else "",
    ]
    return ", ".join(str(part).strip() for part in parts if part)


def reference_values(references: list, index: int, name_cell: str, address_cell: str) -> dict[str, str]:
    if len(references) <= index:
        return {}
    reference = references[index] or {}
    return {name_cell: reference.get("nombre"), address_cell: format_address(reference.get("domicilio") or {})}


def option_marks(value: str | None, mapping: dict[str, str]) -> dict[str, str]:
    if not value:
        return {}
    normalized = normalize(value)
    for option, cell in mapping.items():
        if normalize(option) == normalized:
            return {cell: "X"}
    return {}


def normalize(value: str) -> str:
    return sub(r"\s+", " ", value.strip().lower())


def format_date_long(value: str | None) -> str:
    if not value:
        return ""
    if "-" in value:
        year, month, day = value.split("-")[:3]
    elif "/" in value:
        day, month, year = value.split("/")[:3]
    else:
        return value
    return f"{int(day)} DE {MONTHS.get(month.zfill(2), month)} DE {year}"


def safe_name(value: str) -> str:
    return sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_") or "solicitud"

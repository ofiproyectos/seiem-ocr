from __future__ import annotations

from base64 import b64decode
from datetime import datetime
from posixpath import basename, dirname, join, normpath
from pathlib import Path
from re import DOTALL, compile, escape as re_escape, findall, match, search, sub
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import cv2
import numpy as np

from backend.app.config import get_settings


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
IMAGE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
DRAWING_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"

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
    patch_xlsx(template, output, build_cell_values(datos), build_photo_values(datos))
    return output


def patch_xlsx(template: Path, output: Path, values: dict[str, str], photos: list[dict[str, str]]) -> None:
    with ZipFile(template, "r") as source:
        sheet_path = find_sheet_path(source, "Plantilla")
        shared_strings_path = "xl/sharedStrings.xml"
        shared_xml, indexes = patch_shared_strings(source.read(shared_strings_path), list(values.values()))
        patched_sheet = patch_sheet_xml(source.read(sheet_path), values, indexes)
        extra_files = build_photo_xlsx_parts(source, sheet_path, patched_sheet, photos)
        patched_sheet = extra_files.pop(sheet_path, patched_sheet)

        with ZipFile(output, "w", ZIP_DEFLATED) as target:
            for item in source.infolist():
                if item.filename == sheet_path:
                    content = patched_sheet
                elif item.filename == shared_strings_path:
                    content = shared_xml
                elif item.filename in extra_files:
                    content = extra_files[item.filename]
                else:
                    content = source.read(item.filename)
                target.writestr(item, content)
            for filename, content in extra_files.items():
                if filename not in source.namelist():
                    target.writestr(filename, content)


def build_photo_xlsx_parts(source: ZipFile, sheet_path: str, sheet_xml: bytes, photos: list[dict[str, str]]) -> dict[str, bytes]:
    photo_cache: dict[str, bytes] = {}
    prepared = [photo for photo in (prepare_photo(photo, photo_cache) for photo in photos) if photo]
    if not prepared:
        return {}

    files: dict[str, bytes] = {}
    sheet_xml_text = sheet_xml.decode("utf-8")
    sheet_rels_path = worksheet_rels_path(sheet_path)
    sheet_rels_xml = source.read(sheet_rels_path).decode("utf-8") if sheet_rels_path in source.namelist() else empty_rels_xml()
    drawing_rel_id, drawing_path = find_or_create_drawing(source, sheet_xml_text, sheet_rels_xml, sheet_path)

    if drawing_rel_id not in sheet_rels_xml:
        sheet_rels_xml = add_relationship(sheet_rels_xml, drawing_rel_id, DRAWING_REL_TYPE, relative_target(sheet_rels_path, drawing_path))
    if "<drawing " not in sheet_xml_text:
        sheet_xml_text = insert_drawing_reference(sheet_xml_text, drawing_rel_id)

    drawing_rels_path = drawing_relationships_path(drawing_path)
    drawing_xml = source.read(drawing_path).decode("utf-8") if drawing_path in source.namelist() else empty_drawing_xml()
    drawing_rels_xml = source.read(drawing_rels_path).decode("utf-8") if drawing_rels_path in source.namelist() else empty_rels_xml()
    next_pic_id = next_drawing_id(drawing_xml)
    existing_media = [name for name in source.namelist() if name.startswith("xl/media/image")]
    next_image_id = next_number(existing_media, r"xl/media/image(\d+)\.")

    for photo in prepared:
        image_name = f"xl/media/image{next_image_id}.{photo['extension']}"
        rel_id = next_relationship_id(drawing_rels_xml)
        drawing_rels_xml = add_relationship(drawing_rels_xml, rel_id, IMAGE_REL_TYPE, f"../media/{basename(image_name)}")
        drawing_xml = append_picture_anchor(drawing_xml, rel_id, next_pic_id, photo["name"], photo["anchor"])
        files[image_name] = photo["bytes"]
        next_pic_id += 1
        next_image_id += 1

    files[sheet_path] = sheet_xml_text.encode("utf-8")
    files[sheet_rels_path] = sheet_rels_xml.encode("utf-8")
    files[drawing_path] = drawing_xml.encode("utf-8")
    files[drawing_rels_path] = drawing_rels_xml.encode("utf-8")
    files["[Content_Types].xml"] = patch_content_types(source.read("[Content_Types].xml").decode("utf-8"), drawing_path).encode("utf-8")
    return files


def prepare_photo(photo: dict[str, str], photo_cache: dict[str, bytes]) -> dict[str, str | bytes] | None:
    data_url = photo.get("data") or ""
    if not data_url.startswith("data:image/") or "," not in data_url:
        return None
    if data_url not in photo_cache:
        _, payload = data_url.split(",", 1)
        photo_cache[data_url] = clean_photo_background(b64decode(payload))
    image_bytes = fit_photo_to_anchor(photo_cache[data_url], photo["anchor"])
    return {
        "name": photo["name"],
        "anchor": photo["anchor"],
        "extension": "jpeg",
        "bytes": image_bytes,
    }


def clean_photo_background(image_bytes: bytes) -> bytes:
    raw = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        return image_bytes

    height, width = image.shape[:2]
    if max(height, width) > 720:
        scale = 720 / max(height, width)
        image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        height, width = image.shape[:2]

    mask = np.zeros((height, width), np.uint8)
    rect = (
        max(1, int(width * 0.12)),
        max(1, int(height * 0.04)),
        max(2, int(width * 0.76)),
        max(2, int(height * 0.92)),
    )
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    try:
        cv2.grabCut(image, mask, rect, bgd_model, fgd_model, 2, cv2.GC_INIT_WITH_RECT)
        foreground = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
        kernel = np.ones((3, 3), np.uint8)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=1)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel, iterations=1)
        foreground = cv2.GaussianBlur(foreground, (5, 5), 0)
        foreground = remove_border_background_from_mask(image, foreground)
        alpha = foreground.astype(np.float32) / 255.0
        white = np.full_like(image, 255)
        cleaned = (image * alpha[..., None] + white * (1 - alpha[..., None])).astype(np.uint8)
    except cv2.error:
        cleaned = image

    ok, encoded = cv2.imencode(".jpg", cleaned, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return encoded.tobytes() if ok else image_bytes


def remove_border_background_from_mask(image: np.ndarray, foreground: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    border = max(8, min(height, width) // 18)
    samples = np.concatenate(
        [
            image[:border].reshape(-1, 3),
            image[-border:].reshape(-1, 3),
            image[:, :border].reshape(-1, 3),
            image[:, -border:].reshape(-1, 3),
        ],
        axis=0,
    )
    background_bgr = np.median(samples, axis=0).astype(np.uint8).reshape(1, 1, 3)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.int16)
    background_lab = cv2.cvtColor(background_bgr, cv2.COLOR_BGR2LAB).astype(np.int16)[0, 0]
    distance = np.linalg.norm(lab - background_lab, axis=2)
    background_like = (distance < 24).astype(np.uint8) * 255
    edge_background = np.zeros((height + 2, width + 2), np.uint8)
    flood = background_like.copy()
    for point in [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]:
        cv2.floodFill(flood, edge_background, point, 128)
    connected_background = flood == 128
    result = foreground.copy()
    result[connected_background] = 0
    return result


def fit_photo_to_anchor(image_bytes: bytes, anchor: str) -> bytes:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return image_bytes

    target_width, target_height = {
        "frente_cuadro": (420, 420),
        "frente_ovalo": (420, 580),
        "perfil_ovalo": (420, 580),
    }[anchor]
    height, width = image.shape[:2]
    scale = min(target_width / width, target_height / height)
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
    canvas = np.full((target_height, target_width, 3), 255, dtype=np.uint8)
    x = (target_width - new_width) // 2
    y = (target_height - new_height) // 2
    canvas[y : y + new_height, x : x + new_width] = resized
    ok, encoded = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return encoded.tobytes() if ok else image_bytes


def worksheet_rels_path(sheet_path: str) -> str:
    return f"{dirname(sheet_path)}/_rels/{basename(sheet_path)}.rels"


def drawing_relationships_path(drawing_path: str) -> str:
    return f"{dirname(drawing_path)}/_rels/{basename(drawing_path)}.rels"


def empty_rels_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'


def empty_drawing_xml() -> str:
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><xdr:wsDr xmlns:xdr="{DRAWING_NS}" xmlns:a="{A_NS}"></xdr:wsDr>'


def find_or_create_drawing(source: ZipFile, sheet_xml: str, sheet_rels_xml: str, sheet_path: str) -> tuple[str, str]:
    drawing_match = search(r'<drawing\b[^>]*\br:id="([^"]+)"[^>]*/?>', sheet_xml)
    if drawing_match:
        rel_id = drawing_match.group(1)
        target_match = search(rf'<Relationship\b(?=[^>]*\bId="{re_escape(rel_id)}")(?=[^>]*\bTarget="([^"]+)")[^>]*/>', sheet_rels_xml)
        if target_match:
            return rel_id, normalize_part_path(sheet_path, target_match.group(1))

    existing_drawings = [name for name in source.namelist() if name.startswith("xl/drawings/drawing") and name.endswith(".xml")]
    next_drawing_number = next_number(existing_drawings, r"xl/drawings/drawing(\d+)\.xml")
    drawing_path = f"xl/drawings/drawing{next_drawing_number}.xml"
    return next_relationship_id(sheet_rels_xml), drawing_path


def normalize_part_path(base_path: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return normpath(join(dirname(base_path), target))


def relative_target(rels_path: str, part_path: str) -> str:
    if rels_path.startswith("xl/worksheets/"):
        return f"../drawings/{basename(part_path)}"
    return part_path


def next_relationship_id(rels_xml: str) -> str:
    numbers = [int(value) for value in findall(r'\bId="rId(\d+)"', rels_xml)]
    return f"rId{(max(numbers) if numbers else 0) + 1}"


def next_number(names: list[str], pattern: str) -> int:
    numbers = [int(value) for name in names for value in findall(pattern, name)]
    return (max(numbers) if numbers else 0) + 1


def next_drawing_id(drawing_xml: str) -> int:
    numbers = [int(value) for value in findall(r'\bid="(\d+)"', drawing_xml)]
    return (max(numbers) if numbers else 0) + 1


def add_relationship(rels_xml: str, rel_id: str, rel_type: str, target: str) -> str:
    relationship = f'<Relationship Id="{rel_id}" Type="{rel_type}" Target="{xml_escape(target)}"/>'
    return rels_xml.replace("</Relationships>", f"{relationship}</Relationships>")


def insert_drawing_reference(sheet_xml: str, rel_id: str) -> str:
    drawing = f'<drawing r:id="{rel_id}"/>'
    if "xmlns:r=" not in sheet_xml:
        sheet_xml = sheet_xml.replace("<worksheet ", f'<worksheet xmlns:r="{REL_NS}" ', 1)
    if "</worksheet>" in sheet_xml:
        return sheet_xml.replace("</worksheet>", f"{drawing}</worksheet>")
    return sheet_xml


def append_picture_anchor(drawing_xml: str, rel_id: str, picture_id: int, name: str, anchor: str) -> str:
    from_col, from_row, to_col, to_row, geometry = {
        "frente_cuadro": (10, 10, 12, 15, "rect"),
        "frente_ovalo": (12, 7, 15, 16, "ellipse"),
        "perfil_ovalo": (12, 17, 15, 26, "ellipse"),
    }[anchor]
    anchor_xml = f"""
  <xdr:twoCellAnchor editAs="oneCell">
    <xdr:from><xdr:col>{from_col}</xdr:col><xdr:colOff>80000</xdr:colOff><xdr:row>{from_row}</xdr:row><xdr:rowOff>80000</xdr:rowOff></xdr:from>
    <xdr:to><xdr:col>{to_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{to_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
    <xdr:pic>
      <xdr:nvPicPr><xdr:cNvPr id="{picture_id}" name="{xml_escape(name)}"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>
      <xdr:blipFill><a:blip r:embed="{rel_id}" xmlns:r="{REL_NS}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
      <xdr:spPr><a:prstGeom prst="{geometry}"><a:avLst/></a:prstGeom></xdr:spPr>
    </xdr:pic>
    <xdr:clientData/>
  </xdr:twoCellAnchor>"""
    return drawing_xml.replace("</xdr:wsDr>", f"{anchor_xml}</xdr:wsDr>").replace("</wsDr>", f"{anchor_xml}</wsDr>")


def patch_content_types(xml: str, drawing_path: str) -> str:
    if 'Extension="jpeg"' not in xml:
        xml = xml.replace("</Types>", '<Default Extension="jpeg" ContentType="image/jpeg"/></Types>')
    if 'Extension="jpg"' not in xml:
        xml = xml.replace("</Types>", '<Default Extension="jpg" ContentType="image/jpeg"/></Types>')
    if 'Extension="png"' not in xml:
        xml = xml.replace("</Types>", '<Default Extension="png" ContentType="image/png"/></Types>')
    part_name = f"/{drawing_path}"
    if part_name not in xml:
        xml = xml.replace(
            "</Types>",
            f'<Override PartName="{part_name}" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>',
        )
    return xml


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

    return {
        cell: normalize_excel_value(cell, value)
        for cell, value in values.items()
        if value not in (None, "")
    }


def build_photo_values(datos: dict) -> list[dict[str, str]]:
    fotos = datos.get("fotos") or {}
    values = []
    frente_cuadro = fotos.get("frenteCuadro") or fotos.get("frente")
    frente_ovalo = fotos.get("frenteOvalo") or fotos.get("frente")
    perfil_ovalo = fotos.get("perfilOvalo") or fotos.get("perfil")
    if frente_cuadro:
        values.append({"name": "Foto de frente cuadro", "anchor": "frente_cuadro", "data": frente_cuadro})
    if frente_ovalo:
        values.append({"name": "Foto de frente ovalo", "anchor": "frente_ovalo", "data": frente_ovalo})
    if perfil_ovalo:
        values.append({"name": "Foto de perfil ovalo", "anchor": "perfil_ovalo", "data": perfil_ovalo})
    return values


def normalize_excel_value(cell: str, value) -> str:
    text = " ".join(str(value).split())
    if cell == "C23":
        return text
    return preserve_address_prefixes(text.upper())


def preserve_address_prefixes(text: str) -> str:
    return text.replace("NO.", "No.").replace("INT.", "Int.")


def label_value(label: str, value) -> str:
    return f"{label} {value or ''}".strip()


def valid_year(value) -> str:
    text = str(value or "")
    return text if match(r"^(19|20)\d{2}$", text) else ""


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

import argparse
import csv
from pathlib import Path

from sqlalchemy import delete

from backend.app.db.session import Base, SessionLocal, engine
from backend.app.models import CodigoPostal


def read_rows(path: Path) -> list[dict[str, str]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")
    lines = [line for line in text.splitlines() if line.strip()]
    header_index = next((index for index, line in enumerate(lines) if line.startswith("d_codigo|")), -1)
    if header_index < 0:
        raise ValueError("No se encontro el encabezado SEPOMEX esperado: d_codigo|d_asenta|...")

    data_lines = lines[header_index:]
    sample = "\n".join(data_lines[:20])
    dialect = csv.Sniffer().sniff(sample, delimiters="|,\t")
    reader = csv.DictReader(data_lines, dialect=dialect)
    rows = []

    for row in reader:
        clean_row = {}
        for key, value in row.items():
            if key is None:
                continue
            clean_row[key.strip()] = value.strip() if isinstance(value, str) else ""
        rows.append(clean_row)

    return rows


def import_file(path: Path, replace: bool = False) -> int:
    Base.metadata.create_all(bind=engine)
    rows = read_rows(path)
    records = []

    for row in rows:
        cp = row.get("d_codigo") or row.get("cp") or row.get("codigo_postal")
        asentamiento = row.get("d_asenta") or row.get("asentamiento")
        municipio = row.get("D_mnpio") or row.get("d_mnpio") or row.get("municipio")
        estado = row.get("d_estado") or row.get("estado")
        if not cp or not asentamiento or not municipio or not estado:
            continue

        records.append(
            CodigoPostal(
                cp=cp.zfill(5),
                asentamiento=asentamiento,
                tipo_asentamiento=row.get("d_tipo_asenta") or row.get("tipo_asentamiento"),
                municipio=municipio,
                estado=estado,
                ciudad=row.get("d_ciudad") or row.get("ciudad") or None,
            )
        )

    with SessionLocal() as db:
        if replace:
            db.execute(delete(CodigoPostal))
        db.add_all(records)
        db.commit()

    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa el catalogo SEPOMEX de codigos postales.")
    parser.add_argument("archivo", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    total = import_file(args.archivo, replace=args.replace)
    print(f"Registros importados: {total}")


if __name__ == "__main__":
    main()

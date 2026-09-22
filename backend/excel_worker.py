import json
import sys
from pathlib import Path

from backend.app.services.excel_service import write_with_excel


def main() -> int:
    if len(sys.argv) != 3:
        print("Uso: python -m backend.excel_worker archivo.xlsx valores.json", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    values_path = Path(sys.argv[2])
    values = json.loads(values_path.read_text(encoding="utf-8"))
    write_with_excel(path, values)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

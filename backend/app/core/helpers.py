from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
import json


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def norm(v) -> str:
    return "" if v is None else str(v).strip()


def to_num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace(" ", "").strip())
    except Exception:
        return None


def write_json(path: str | Path, data) -> Path:
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return p


def zip_dir(source_dir: str | Path, zip_path: str | Path) -> Path:
    source = Path(source_dir)
    target = Path(zip_path)
    ensure_dir(target.parent)
    with ZipFile(target, "w", ZIP_DEFLATED) as zf:
        for file_path in source.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(source).as_posix())
    return target

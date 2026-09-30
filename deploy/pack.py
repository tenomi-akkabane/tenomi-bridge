#!/usr/bin/env python3
"""Build a distribution ZIP (src + deploy + config example + license notices)."""

from __future__ import annotations

import argparse
import re
import stat
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

_ROOT = Path(__file__).resolve().parent.parent
_FOLDER = "tenomi-bridge"
_FILES = [
    "pyproject.toml",
    "config.example.toml",
    "requirements.txt",
    "src/__init__.py",
    "src/__main__.py",
    "src/main.py",
    "src/config.py",
    "src/metrics.py",
    "src/nus_central.py",
    "src/protocol.py",
    "src/serial_bridge.py",
    "deploy/install.sh",
    "deploy/tenomi-bridge.service.in",
    "INSTALL.md",
    "LICENSE",
    "NOTICE.md",
]


def _version() -> str:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("version not found in pyproject.toml")
    return match.group(1)


def _unix_mode(path: Path) -> int:
    if path.suffix == ".sh":
        return 0o755
    return 0o644


def _payload(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix in {".sh", ".in", ".py", ".toml", ".txt", ".md"}:
        text = data.decode("utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.endswith("\n"):
            text += "\n"
        return text.encode("utf-8")
    return data


def pack(out_dir: Path) -> Path:
    version = _version()  # still read from pyproject.toml; validates the file even though unused in the name
    out_dir.mkdir(parents=True, exist_ok=True)
    # Neither the ZIP's file name nor the folder inside it carries the version,
    # so install instructions (`unzip tenomi-bridge.zip`, `cd tenomi-bridge`)
    # never need to change across releases. The version itself still lives in
    # pyproject.toml inside the archive.
    zip_path = out_dir / "tenomi-bridge.zip"
    missing = [rel for rel in _FILES if not (_ROOT / rel).is_file()]
    if missing:
        raise SystemExit("missing files:\n  " + "\n  ".join(missing))

    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for rel in _FILES:
            src = _ROOT / rel
            _add(zf, f"{_FOLDER}/{rel}", src, _payload(src), _unix_mode(src))

    return zip_path


def _date_time(path: Path) -> tuple[int, int, int, int, int, int]:
    t = time.localtime(path.stat().st_mtime)
    year = t.tm_year if t.tm_year >= 1980 else 1980
    return (year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)


def _add(
    zf: ZipFile, arcname: str, src: Path, data: bytes, mode: int
) -> None:
    info = ZipInfo(filename=arcname, date_time=_date_time(src))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | mode) << 16
    zf.writestr(info, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create tenomi-bridge distribution ZIP")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=_ROOT / "dist",
        help="Directory for the ZIP (default: ./dist)",
    )
    args = parser.parse_args()
    path = pack(args.output_dir.resolve())
    size = path.stat().st_size
    print(f"{path} ({size} bytes)")


if __name__ == "__main__":
    main()

"""Build a distributable .ankiaddon package for AnkiMinder."""

from __future__ import annotations

import argparse
import json
import re
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ENTRIES = [
    "__init__.py",
    "manifest.json",
    "config.json",
    "config.md",
    "ankiminder",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build .ankiaddon package.")
    parser.add_argument(
        "-v",
        "--version",
        required=True,
        help="Version token used in filename, e.g. 102 or 1.0.3",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="Optional output path. File name must still be ankiminderV<version>.ankiaddon",
    )
    return parser.parse_args()


def normalize_version_token(raw: str) -> str:
    value = raw.strip()
    if value.lower().startswith("v"):
        value = value[1:]
    if not value:
        raise ValueError("Version is required.")
    if not re.fullmatch(r"[0-9A-Za-z._-]+", value):
        raise ValueError("Version contains unsupported characters.")
    return value


def load_manifest() -> dict:
    manifest_path = REPO_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("package", "name"):
        if not manifest.get(key):
            raise ValueError(f"manifest.json must include '{key}'.")
    manifest["mod"] = int(time.time())
    return manifest


def iter_package_files() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []

    def add_file(rel_path: str) -> None:
        path = REPO_ROOT / rel_path
        if not path.exists():
            raise FileNotFoundError(f"Required path not found: {rel_path}")
        if path.is_file():
            items.append((path, rel_path))
            return
        for child in sorted(path.rglob("*")):
            if child.is_dir():
                continue
            if "__pycache__" in child.parts or child.suffix in {".pyc", ".pyo"}:
                continue
            if "mocks" in child.parts:
                # Test doubles are for tests/ only; they must not ship in
                # the distributed .ankiaddon package.
                continue
            items.append((child, str(child.relative_to(REPO_ROOT)).replace("\\", "/")))

    for entry in REQUIRED_ENTRIES:
        add_file(entry)
    return items


def main() -> int:
    args = parse_args()
    version = normalize_version_token(args.version)
    expected_name = f"ankiminderV{version}.ankiaddon"

    if args.output:
        out_path = Path(args.output).resolve()
        if out_path.name != expected_name:
            raise ValueError(f"Output file must be named '{expected_name}'.")
    else:
        out_path = (REPO_ROOT / "dist" / expected_name).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    files = iter_package_files()

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source, arcname in files:
            if arcname == "manifest.json":
                zf.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
            else:
                zf.write(source, arcname)

    print(f"Built: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

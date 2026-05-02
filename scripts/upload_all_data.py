"""
Upload all supported files in data/ to the /ingest API.

Usage:
  python -m scripts.upload_all_data [--data-dir data] [--api http://localhost:8000]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_API = os.environ.get("API_BASE", "http://localhost:8000")
SUPPORTED_EXTS = {".jpeg", ".jpg", ".pdf", ".xlsx", ".xls"}


def iter_files(data_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in data_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            files.append(path)
    return sorted(files)


def upload_file(client: httpx.Client, file_path: Path, api_base: str) -> dict:
    with file_path.open("rb") as fh:
        files = {"file": (file_path.name, fh, "application/octet-stream")}
        resp = client.post(f"{api_base}/ingest", files=files)
        resp.raise_for_status()
        return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload data/ files to /ingest")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise SystemExit(f"Data dir not found: {data_dir}")

    files = iter_files(data_dir)
    if not files:
        print("No supported files found in data/.")
        return

    print(f"Uploading {len(files)} files to {args.api}/ingest")

    ok = 0
    failed = 0
    with httpx.Client(timeout=300.0) as client:
        for path in files:
            try:
                result = upload_file(client, path, args.api)
                ok += 1
                extracted = result.get("extracted", "?")
                print(f"[ok] {path.name} -> extracted {extracted}")
            except Exception as exc:
                failed += 1
                print(f"[fail] {path.name} -> {exc}")

    print(f"Done. ok={ok} failed={failed}")


if __name__ == "__main__":
    main()

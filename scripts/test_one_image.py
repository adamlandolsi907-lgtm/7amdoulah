"""
Quick smoke test: run the extractor on one real JPEG and print the result.

Usage (from project root, with venv active):
    python scripts/test_one_image.py
    python scripts/test_one_image.py "data/WhatsApp Image 2026-04-27 at 21.39.25 (38).jpeg"
"""
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.extractors.image import extract_image


def main() -> int:
    # Default: first JPEG in data/
    default = Path("data") / "WhatsApp Image 2026-04-27 at 21.39.25 (38).jpeg"
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default

    if not target.exists():
        # Fallback: any JPEG in data/
        jpegs = sorted(Path("data").glob("*.jpeg"))
        if not jpegs:
            print("No JPEG files found in data/")
            return 1
        target = jpegs[0]

    print(f"\nExtracting: {target.name}")
    print("-" * 60)

    record = extract_image(str(target))
    print(json.dumps(record.model_dump(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

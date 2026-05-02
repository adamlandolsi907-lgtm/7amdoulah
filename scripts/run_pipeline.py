"""
Full pipeline runner — processes all data files and populates the DB.

Usage:
    python -m scripts.run_pipeline [--data-dir data/] [--qdrant]
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.store import init_db, upsert_energy_records, upsert_co2_estimates, upsert_anomalies
from app.pipeline.co2 import estimate_co2_batch
from app.pipeline.normalize import normalize_record
from app.pipeline.anomaly import detect_all

_DEFAULT_DATA = Path(__file__).parent.parent / "data"
_DEFAULT_DB   = _DEFAULT_DATA / "pipeline.db"


def run(data_dir: Path, db_path: str, upsert_qdrant: bool) -> None:
    print(f"[init] DB: {db_path}")
    init_db(db_path)

    all_records = []

    # ── Images ───────────────────────────────────────────────────────────────
    print("\n[1/3] Extracting JPEG images ...")
    try:
        from app.extractors.image import extract_all_images
        img_records = extract_all_images(str(data_dir))
        for r in img_records:
            upsert_energy_records([r], db_path)
        print(f"  extracted {len(img_records)} image records")
        all_records.extend(img_records)
    except Exception as exc:
        print(f"  WARN: image extraction failed — {exc}")

    # ── PDFs ─────────────────────────────────────────────────────────────────
    print("\n[2/3] Extracting PDF files ...")
    try:
        from app.extractors.pdf import extract_all_pdfs
        pdf_records = extract_all_pdfs(str(data_dir))
        for r in pdf_records:
            upsert_energy_records([r], db_path)
        print(f"  extracted {len(pdf_records)} PDF records")
        all_records.extend(pdf_records)
    except Exception as exc:
        print(f"  WARN: PDF extraction failed — {exc}")

    # ── Excel ────────────────────────────────────────────────────────────────
    print("\n[3/3] Extracting Excel reports ...")
    try:
        from app.extractors.excel import extract_all_excel
        xl_records = extract_all_excel(str(data_dir))
        for r in xl_records:
            normalize_record(r)
        upsert_energy_records(xl_records, db_path)
        print(f"  extracted {len(xl_records)} Excel records")
        all_records.extend(xl_records)
    except Exception as exc:
        print(f"  WARN: Excel extraction failed — {exc}")

    # ── CO2 ──────────────────────────────────────────────────────────────────
    print("\n[CO2] Estimating emissions ...")
    try:
        estimates = estimate_co2_batch(all_records)
        upsert_co2_estimates(estimates, db_path)
        total_co2 = sum(e.co2_kg for e in estimates)
        print(f"  {len(estimates)} CO2 estimates | total = {total_co2:.0f} kgCO2")
    except Exception as exc:
        print(f"  WARN: CO2 estimation failed — {exc}")

    # ── Anomaly detection ─────────────────────────────────────────────────────
    print("\n[Anomaly] Running detectors ...")
    try:
        from app.models.schemas import EnergyRecord
        energy_recs = [r for r in all_records if isinstance(r, EnergyRecord)]
        anomalies = detect_all(energy_recs)
        upsert_anomalies(anomalies, db_path)
        print(f"  {len(anomalies)} anomalies detected")
    except Exception as exc:
        print(f"  WARN: Anomaly detection failed — {exc}")

    print(f"\n[done] Pipeline complete. {len(all_records)} total records in {db_path}")

    if upsert_qdrant:
        print("\n[Qdrant] Upserting extracted records ...")
        try:
            from app.pipeline.qdrant_ingest import upsert_records_to_qdrant
            result = upsert_records_to_qdrant(all_records)
            print(f"  upserted {result['upserted']} points into {result['collection']}")
        except Exception as exc:
            print(f"  WARN: Qdrant upsert failed — {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NRTF energy pipeline runner")
    parser.add_argument("--data-dir", default=str(_DEFAULT_DATA))
    parser.add_argument("--qdrant", action="store_true", help="upsert extracted records to Qdrant")
    args = parser.parse_args()
    run(Path(args.data_dir), str(_DEFAULT_DB), args.qdrant)

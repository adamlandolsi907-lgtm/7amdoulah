"""
STEG PDF extractor — handles scanned multi-page PDFs.

Strategy:
  1. Try pdfplumber text extraction (fast, for native text PDFs)
    2. Fall back to Ollama vision per page (for scanned/image PDFs — all current data)

PDF-to-image uses pymupdf (fitz) at 200 DPI; pages are then processed by
the same classify → extract pipeline used for JPEG invoices.
"""

import uuid
from pathlib import Path
from typing import Union

import fitz  # pymupdf
import pdfplumber
from PIL import Image

from app.extractors.image import (
    classify_image,
    _extract_bill,
    _extract_meter_reading,
    _call_ollama,
    _parse_json,
    _to_float,
    _BILL_PROMPT,
    _METER_PROMPT,
)
from app.models.schemas import (
    DocumentType,
    EnergyRecord,
    EnergyType,
    StegBillRecord,
    StegMeterReadingRecord,
)

AnyRecord = Union[StegBillRecord, StegMeterReadingRecord, EnergyRecord]

_DPI = 200  # render resolution for scanned pages


# ── PDF → images ──────────────────────────────────────────────────────────────

def _render_pages(pdf_path: str) -> list[Image.Image]:
    """Render every page of a PDF to a PIL RGB Image at _DPI."""
    doc = fitz.open(pdf_path)
    zoom = _DPI / 72.0
    mat = fitz.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()
    return images


# ── Text-layer extraction (fallback for future native PDFs) ──────────────────

def _has_text_layer(pdf_path: str) -> bool:
    """Return True if page 0 yields non-trivial text via pdfplumber."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
            return len(text.strip()) > 50
    except Exception:
        return False


def _extract_text_page(page_text: str, source_file: str) -> EnergyRecord | None:
    """
    Minimal parser for structured text PDFs.
    Returns None if the page doesn't look like an energy record.
    Expand this as more text-based PDF formats are encountered.
    """
    text_lower = page_text.lower()
    if "facture" not in text_lower and "releve" not in text_lower and "énergie" not in text_lower:
        return None

    import re
    kwh_match = re.search(r"([\d\s,]+)\s*kwh", text_lower)
    date_match = re.search(r"(\d{1,2})[/\-](\d{4})", page_text)

    if not kwh_match:
        return None

    quantity = _to_float(kwh_match.group(1))
    date = "unknown"
    if date_match:
        m, y = date_match.group(1).zfill(2), date_match.group(2)
        date = f"{y}-{m}"

    return EnergyRecord(
        document_id=f"pdf_text_{uuid.uuid4().hex[:8]}",
        document_type=DocumentType.pdf_invoice,
        source_file=source_file,
        date=date,
        supplier="STEG",
        energy_type=EnergyType.electricity,
        quantity_raw=quantity or 0.0,
        unit_raw="kWh",
        quantity_kwh=quantity,
        extraction_confidence=0.6,
        extraction_method="pdfplumber_text",
    )


# ── Vision extraction per page ────────────────────────────────────────────────

def _extract_page_vision(image: Image.Image, source_file: str, page_num: int) -> AnyRecord:
    """Classify + extract a single rendered PDF page via Ollama vision."""
    doc_type = classify_image(image)
    page_source = f"{source_file}:p{page_num}"

    if doc_type == DocumentType.steg_bill:
        return _extract_bill(image, page_source)
    elif doc_type == DocumentType.steg_meter_reading:
        return _extract_meter_reading(image, page_source)
    else:
        # Attempt generic energy record via bill prompt
        try:
            raw = _call_ollama(image, _BILL_PROMPT)
            data = _parse_json(raw)
            date = data.get("date") or "unknown"
            energy_kwh = _to_float(data.get("active_energy_kwh"))
            return EnergyRecord(
                document_id=f"pdf_vision_{uuid.uuid4().hex[:8]}",
                document_type=DocumentType.pdf_invoice,
                source_file=page_source,
                date=date,
                supplier="STEG",
                energy_type=EnergyType.electricity,
                quantity_raw=energy_kwh or 0.0,
                unit_raw="kWh",
                quantity_kwh=energy_kwh,
                extraction_confidence=min(float(data.get("confidence", 0.5)), 0.5),
                extraction_method="ollama_vision_fallback",
            )
        except Exception:
            return EnergyRecord(
                document_id=f"pdf_vision_{uuid.uuid4().hex[:8]}",
                document_type=DocumentType.unknown,
                source_file=page_source,
                date="unknown",
                energy_type=EnergyType.electricity,
                quantity_raw=0.0,
                unit_raw="kWh",
                extraction_confidence=0.0,
                extraction_method="ollama_vision_fallback",
            )


# ── Public entry points ───────────────────────────────────────────────────────

def extract_pdf(pdf_path: str) -> list[AnyRecord]:
    """
    Extract all pages from a PDF. Returns a list (one record per page).
    Uses pdfplumber for text PDFs; Ollama vision for scanned PDFs.
    """
    source_file = Path(pdf_path).name
    records: list[AnyRecord] = []

    if _has_text_layer(pdf_path):
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                rec = _extract_text_page(text, source_file)
                if rec:
                    records.append(rec)
        if records:
            return records

    # Vision path: render each page and classify
    images = _render_pages(pdf_path)
    for i, image in enumerate(images):
        rec = _extract_page_vision(image, source_file, page_num=i + 1)
        records.append(rec)

    return records


def extract_all_pdfs(data_dir: str) -> list[AnyRecord]:
    """Process every PDF in data_dir. Returns flat list of records."""
    results: list[AnyRecord] = []
    for path in sorted(Path(data_dir).glob("*.pdf")):
        print(f"  [{path.name}]")
        try:
            records = extract_pdf(str(path))
            results.extend(records)
            for r in records:
                conf = getattr(r, "extraction_confidence", "?")
                date = getattr(r, "date", "?")
                dtype = getattr(r, "document_type", type(r).__name__)
                print(f"    → {dtype} | date={date} | conf={conf:.2f}")
        except Exception as e:
            print(f"    ERROR: {e}")
    return results

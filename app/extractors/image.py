"""
STEG invoice image extractor — Ollama vision backend (local).

Handles two document subtypes found in data/*.jpeg:
  - steg_bill          : Facture Moyenne Tension
  - steg_meter_reading : Fiche Relevé Énergie Achat et Vente

Pipeline per file:
  1. Load + preprocess (CLAHE contrast, deskew rotation)
    2. Classify document subtype via Ollama vision
    3. Extract structured fields via Ollama vision
  4. Return typed Pydantic record
"""

import base64
import json
import os
import re
import uuid
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
import httpx
from PIL import Image

from app.models.schemas import (
    DocumentType,
    StegBillRecord,
    StegMeterReadingRecord,
)

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_VISION_MODEL", os.environ.get("OLLAMA_MODEL", "llava"))


# ── Image preprocessing ───────────────────────────────────────────────────────

def _load_and_preprocess(image_path: str) -> Image.Image:
    """
    Load a phone-photographed invoice and apply:
      - CLAHE contrast enhancement (fixes dark/uneven lighting)
      - Deskew rotation correction (fixes tilted photos)
    Returns a PIL Image for the Ollama API.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    enhanced = _deskew(enhanced)

    # Convert grayscale numpy array → PIL RGB Image
    rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb)


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Rotate image to correct small tilt (±15°). Skips if angle is negligible."""
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle += 90
    if abs(angle) < 0.5 or abs(angle) > 15:
        return gray

    h, w = gray.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_CONTEXT = """
You are an industrial energy data extraction specialist reading STEG documents.
STEG = Société Tunisienne de l'Électricité et du Gaz (Tunisian utility).
Factory: SOCIÉTÉ ADWYA — pharmaceutical manufacturer, Sidi Daoud, Tunisia.
Client reference: 226570, District: KRAM.
Documents are bilingual French (left-to-right) and Arabic (right-to-left).
Return ONLY valid JSON. No explanation, no markdown fences.
""".strip()

_CLASSIFY_PROMPT = """
Identify the document type. Return exactly one of:
{"type": "steg_bill"}
{"type": "steg_meter_reading"}
{"type": "unknown"}

- "steg_bill" if header says "FACTURE MOYENNE TENSION" or "فاتورة استهلاك الجهد المتوسط"
- "steg_meter_reading" if header says "FICHE RELEVE ENERGIE ACHAT ET VENTE"
- "unknown" otherwise
""".strip()

_BILL_PROMPT = """
Extract fields from this STEG Facture Moyenne Tension (electricity bill).

- date: billing month as YYYY-MM (from "Mois", e.g. "10/2025" → "2025-10")
- facture_number: alphanumeric code after "N° Facture" (e.g. "69105258R")
- active_energy_kwh: main consumption figure labelled "Consommation à facturer kWh" (large integer ~10,000–30,000)
- reactive_energy_kvarh: figure labelled "Réactif" or "Énergie réactive" (smaller number)
- power_subscribed_kva: contracted demand after "Puissance souscrite" (typically 1300)
- amount_tnd: total payable after "NET À PAYER" (Tunisian Dinars, decimal number)
- site: customer name (usually "STE ADWYA")
- district: district name (usually "KRAM")
- confidence: your confidence 0.0–1.0

Return JSON:
{
  "date": "YYYY-MM",
  "facture_number": "string or null",
  "active_energy_kwh": number_or_null,
  "reactive_energy_kvarh": number_or_null,
  "power_subscribed_kva": number_or_null,
  "amount_tnd": number_or_null,
  "site": "string or null",
  "district": "string or null",
  "confidence": 0.0
}
""".strip()

_METER_PROMPT = """
Extract fields from this STEG Fiche Relevé Énergie Achat et Vente.

Key concepts:
- Energy consumed per slot = Nouveau index - Ancien index (kWh)
- PURCHASE slots (from STEG grid): Jour=1.8.3, Pointe=1.8.2, Nuit=1.8.1, Soir=1.8.4, Réactive=5.8.0
- INJECTION slots (sold to grid from tri-gen): Jour=2.8.3, Pointe=2.8.2, Nuit=2.8.1, Soir=2.8.4
- net_consumption_kwh = total purchase - total injection (compute this yourself)
- IMax = maximum demand in kVA

Return JSON:
{
  "date": "YYYY-MM",
  "client_ref": "string or null",
  "purchase_jour_kwh": number_or_null,
  "purchase_pointe_kwh": number_or_null,
  "purchase_nuit_kwh": number_or_null,
  "purchase_soir_kwh": number_or_null,
  "purchase_reactive_kvarh": number_or_null,
  "injection_jour_kwh": number_or_null,
  "injection_pointe_kwh": number_or_null,
  "injection_nuit_kwh": number_or_null,
  "injection_soir_kwh": number_or_null,
  "net_consumption_kwh": number_or_null,
  "max_demand_j_kva": number_or_null,
  "max_demand_p_kva": number_or_null,
  "max_demand_s_kva": number_or_null,
  "confidence": 0.0
}
""".strip()


# ── Ollama API call ───────────────────────────────────────────────────────────

def _call_ollama(image: Image.Image, prompt: str) -> str:
    """Send PIL image + prompt to Ollama, return raw text."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_CONTEXT},
            {"role": "user", "content": prompt, "images": [image_b64]},
        ],
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

    content = data.get("message", {}).get("content", "")
    return content.strip()


def _parse_json(raw: str) -> dict:
    """Strip accidental markdown fences and parse JSON."""
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)


# ── Classification ────────────────────────────────────────────────────────────

def classify_image(image: Image.Image) -> DocumentType:
    try:
        raw = _call_ollama(image, _CLASSIFY_PROMPT)
        data = _parse_json(raw)
        t = data.get("type", "unknown")
        return DocumentType(t) if t in DocumentType._value2member_map_ else DocumentType.unknown
    except Exception:
        return DocumentType.unknown


# ── Per-type extraction ───────────────────────────────────────────────────────

def _extract_bill(image: Image.Image, source_file: str) -> StegBillRecord:
    raw = _call_ollama(image, _BILL_PROMPT)
    data = _parse_json(raw)
    return StegBillRecord(
        document_id=f"bill_{uuid.uuid4().hex[:8]}",
        source_file=source_file,
        date=data.get("date") or "unknown",
        facture_number=data.get("facture_number"),
        active_energy_kwh=_to_float(data.get("active_energy_kwh")),
        reactive_energy_kvarh=_to_float(data.get("reactive_energy_kvarh")),
        power_subscribed_kva=_to_float(data.get("power_subscribed_kva")),
        amount_tnd=_to_float(data.get("amount_tnd")),
        site=data.get("site"),
        district=data.get("district"),
        extraction_confidence=float(data.get("confidence", 0.8)),
        extraction_method="ollama_vision",
    )


def _extract_meter_reading(image: Image.Image, source_file: str) -> StegMeterReadingRecord:
    raw = _call_ollama(image, _METER_PROMPT)
    data = _parse_json(raw)

    purchase_slots = [
        _to_float(data.get("purchase_jour_kwh")),
        _to_float(data.get("purchase_pointe_kwh")),
        _to_float(data.get("purchase_nuit_kwh")),
        _to_float(data.get("purchase_soir_kwh")),
    ]
    injection_slots = [
        _to_float(data.get("injection_jour_kwh")),
        _to_float(data.get("injection_pointe_kwh")),
        _to_float(data.get("injection_nuit_kwh")),
        _to_float(data.get("injection_soir_kwh")),
    ]
    purchase_total = sum(v for v in purchase_slots if v is not None)
    injection_total = sum(v for v in injection_slots if v is not None)
    net = _to_float(data.get("net_consumption_kwh")) or (
        purchase_total - injection_total if purchase_total > 0 else None
    )

    return StegMeterReadingRecord(
        document_id=f"meter_{uuid.uuid4().hex[:8]}",
        source_file=source_file,
        date=data.get("date") or "unknown",
        client_ref=data.get("client_ref"),
        purchase_jour_kwh=_to_float(data.get("purchase_jour_kwh")),
        purchase_pointe_kwh=_to_float(data.get("purchase_pointe_kwh")),
        purchase_nuit_kwh=_to_float(data.get("purchase_nuit_kwh")),
        purchase_soir_kwh=_to_float(data.get("purchase_soir_kwh")),
        purchase_reactive_kvarh=_to_float(data.get("purchase_reactive_kvarh")),
        injection_jour_kwh=_to_float(data.get("injection_jour_kwh")),
        injection_pointe_kwh=_to_float(data.get("injection_pointe_kwh")),
        injection_nuit_kwh=_to_float(data.get("injection_nuit_kwh")),
        injection_soir_kwh=_to_float(data.get("injection_soir_kwh")),
        net_consumption_kwh=net,
        max_demand_j_kva=_to_float(data.get("max_demand_j_kva")),
        max_demand_p_kva=_to_float(data.get("max_demand_p_kva")),
        max_demand_s_kva=_to_float(data.get("max_demand_s_kva")),
        extraction_confidence=float(data.get("confidence", 0.8)),
        extraction_method="ollama_vision",
    )


# ── Public entry point ────────────────────────────────────────────────────────

def extract_image(image_path: str) -> StegBillRecord | StegMeterReadingRecord:
    """
    Full pipeline: preprocess → classify → extract.
    Returns a typed Pydantic record.
    """
    source_file = Path(image_path).name
    image = _load_and_preprocess(image_path)

    doc_type = classify_image(image)

    if doc_type == DocumentType.steg_bill:
        return _extract_bill(image, source_file)
    elif doc_type == DocumentType.steg_meter_reading:
        return _extract_meter_reading(image, source_file)
    else:
        # Best-effort fallback: try bill extraction
        record = _extract_bill(image, source_file)
        record.extraction_confidence = min(record.extraction_confidence, 0.4)
        return record


def extract_all_images(data_dir: str) -> list[StegBillRecord | StegMeterReadingRecord]:
    """Process every JPEG in data_dir. Returns list of records."""
    results = []
    for path in sorted(Path(data_dir).glob("*.jpeg")):
        print(f"  [{path.name}]")
        try:
            record = extract_image(str(path))
            results.append(record)
            print(f"    → {record.document_type if hasattr(record, 'document_type') else type(record).__name__} | date={record.date} | conf={record.extraction_confidence:.2f}")
        except Exception as e:
            print(f"    ERROR: {e}")
    return results


# ── Helper ────────────────────────────────────────────────────────────────────

def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return None

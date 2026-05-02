"""
Qdrant ingestion pipeline powered by Ollama embeddings.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Iterable

import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

load_dotenv()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_TEXT_EXTRACT_MODEL = os.environ.get("OLLAMA_VISION_MODEL", "llava")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text-v1.5")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "adwya_docs")
QDRANT_DISTANCE = os.environ.get("QDRANT_DISTANCE", "cosine").lower()
QDRANT_VECTOR_SIZE = os.environ.get("QDRANT_VECTOR_SIZE")

_DISTANCE_MAP = {
    "cosine": qmodels.Distance.COSINE,
    "dot": qmodels.Distance.DOT,
    "euclid": qmodels.Distance.EUCLID,
}


def _qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def _ollama_chat(prompt: str) -> str:
    payload = {
        "model": OLLAMA_TEXT_EXTRACT_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": "Return plain text only."},
            {"role": "user", "content": prompt},
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
    return (data.get("message", {}).get("content") or "").strip()


def _ollama_embed(text: str) -> list[float]:
    payload = {
        "model": OLLAMA_EMBED_MODEL,
        "prompt": text,
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(f"{OLLAMA_HOST}/api/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()
    embedding = data.get("embedding")
    if not isinstance(embedding, list):
        raise ValueError("Ollama embeddings returned no vector")
    return embedding


def _ensure_collection(client: QdrantClient, vector_size: int) -> None:
    distance = _DISTANCE_MAP.get(QDRANT_DISTANCE, qmodels.Distance.COSINE)
    try:
        client.get_collection(QDRANT_COLLECTION)
        return
    except Exception:
        pass

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=qmodels.VectorParams(
            size=vector_size,
            distance=distance,
        ),
    )


def _infer_doc_type(record: Any) -> str:
    if hasattr(record, "document_type"):
        doc_type = getattr(record, "document_type")
        return doc_type.value if hasattr(doc_type, "value") else str(doc_type)
    if hasattr(record, "facture_number") or hasattr(record, "active_energy_kwh"):
        return "steg_bill"
    if hasattr(record, "purchase_jour_kwh") or hasattr(record, "client_ref"):
        return "steg_meter_reading"
    return "unknown"


def _record_payload(record: Any, text: str) -> dict:
    data = record.model_dump()
    doc_type = _infer_doc_type(record)
    energy_type = data.get("energy_type")
    if hasattr(energy_type, "value"):
        energy_type = energy_type.value

    return {
        "document_id": data.get("document_id"),
        "document_type": doc_type,
        "date": data.get("date"),
        "source_file": data.get("source_file"),
        "energy_type": energy_type,
        "quantity_kwh": data.get("quantity_kwh") or data.get("active_energy_kwh") or data.get("net_consumption_kwh"),
        "extraction_method": data.get("extraction_method"),
        "extraction_confidence": data.get("extraction_confidence"),
        "text": text,
        "fields": data,
    }


def _build_fallback_text(record: Any) -> str:
    data = record.model_dump()
    lines = []
    for key in sorted(data.keys()):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def extract_index_text(record: Any) -> str:
    data = json.dumps(record.model_dump(), ensure_ascii=True)
    prompt = (
        "Extract a clean, searchable text summary from this JSON. "
        "Include key facts like date, document type, energy values, amounts, and references.\n\n"
        f"JSON:\n{data}"
    )
    try:
        text = _ollama_chat(prompt)
        return text if text else _build_fallback_text(record)
    except Exception:
        return _build_fallback_text(record)


def upsert_records_to_qdrant(records: Iterable[Any]) -> dict:
    records = list(records)
    if not records:
        return {"upserted": 0, "collection": QDRANT_COLLECTION}

    try:
        texts = [extract_index_text(r) for r in records]
        embeddings = [_ollama_embed(t) for t in texts]

        vector_size = len(embeddings[0])
        if QDRANT_VECTOR_SIZE:
            try:
                expected = int(QDRANT_VECTOR_SIZE)
            except ValueError as exc:
                raise ValueError("QDRANT_VECTOR_SIZE must be an integer") from exc
            if expected != vector_size:
                raise ValueError(f"Embedding size {vector_size} does not match QDRANT_VECTOR_SIZE {expected}")
            vector_size = expected

        client = _qdrant_client()
        _ensure_collection(client, vector_size)

        points = []
        for record, text, vector in zip(records, texts, embeddings, strict=True):
            payload = _record_payload(record, text)
            point_id = str(uuid.uuid4())
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        client.upsert(collection_name=QDRANT_COLLECTION, points=points)
        return {"upserted": len(points), "collection": QDRANT_COLLECTION, "status": "ok"}
    except Exception as exc:
        return {
            "upserted": 0,
            "collection": QDRANT_COLLECTION,
            "status": "unavailable",
            "error": str(exc),
        }


def list_recent_documents(limit: int = 100) -> list[dict]:
    try:
        client = _qdrant_client()
        client.get_collection(QDRANT_COLLECTION)
    except Exception:
        return []

    documents: list[dict] = []
    offset = None
    batch_size = 128

    while len(documents) < limit:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for p in points:
            payload = p.payload or {}
            documents.append(payload)
        if offset is None:
            break

    def _sort_key(payload: dict) -> tuple:
        date_str = payload.get("date") or ""
        try:
            dt = datetime.strptime(date_str, "%Y-%m")
            return (dt.year, dt.month)
        except Exception:
            return (0, 0)

    documents.sort(key=_sort_key, reverse=True)
    return documents[:limit]


def list_similar_documents(document_id: str, limit: int = 5) -> list[dict]:
    try:
        client = _qdrant_client()
        client.get_collection(QDRANT_COLLECTION)
    except Exception:
        return []

    # Locate the point by payload.document_id and fetch its vector.
    source_point = None
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=128,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            break

        for p in points:
            payload = p.payload or {}
            if payload.get("document_id") == document_id:
                source_point = p
                break

        if source_point is not None or offset is None:
            break

    if source_point is None:
        return []

    vector = source_point.vector
    if vector is None:
        return []
    if isinstance(vector, dict):
        try:
            vector = next(iter(vector.values()))
        except StopIteration:
            return []

    results = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=vector,
        limit=limit + 1,
        with_payload=True,
        with_vectors=False,
    )

    docs: list[dict] = []
    for r in results:
        payload = r.payload or {}
        if payload.get("document_id") == document_id:
            continue
        docs.append(payload)
        if len(docs) >= limit:
            break

    return docs

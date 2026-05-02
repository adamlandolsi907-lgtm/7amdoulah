const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

export async function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Upload failed (${res.status})`);
  }

  return res.json();
}

export async function fetchQdrantDocuments(limit = 100) {
  const res = await fetch(`${API_BASE}/qdrant/documents?limit=${limit}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Fetch failed (${res.status})`);
  }
  return res.json();
}

export async function fetchSimilarQdrantDocuments(documentId: string, limit = 5) {
  const res = await fetch(
    `${API_BASE}/qdrant/similar?document_id=${encodeURIComponent(documentId)}&limit=${limit}`
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Fetch failed (${res.status})`);
  }
  return res.json();
}

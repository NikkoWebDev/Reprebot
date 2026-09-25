"""Reranking con la API de Jina (misma key que embeddings).

Toma candidatos (denso+BM25 fusionados) y los reordena con un cross-encoder
multilingüe. Ante cualquier fallo (red, 429, key), devuelve el orden de
entrada: degradación graceful, nunca rompe la respuesta.
"""

import httpx

from app.core.config import get_settings

_MODEL = "jina-reranker-v2-base-multilingual"
_URL = "https://api.jina.ai/v1/rerank"
_RRF_K = 60


def rrf(rankeds: list[list[int]], k: int = _RRF_K) -> list[int]:
    """Reciprocal Rank Fusion sobre listas de índices (ordenadas mejor→peor)."""
    puntaje: dict[int, float] = {}
    for lista in rankeds:
        for rank, idx in enumerate(lista):
            puntaje[idx] = puntaje.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(puntaje, key=puntaje.get, reverse=True)  # type: ignore[arg-type]


def rerank(query: str, textos: list[str], top_n: int) -> list[tuple[int, float]] | None:
    """[(índice, relevance_score)] ordenados, o None si el reranker falla."""
    if not query or not textos:
        return []
    s = get_settings()
    if not s.embeddings_api_key:
        return None
    try:
        r = httpx.post(
            _URL,
            headers={
                "Authorization": f"Bearer {s.embeddings_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _MODEL,
                "query": query,
                "documents": [t[:1500] for t in textos],
                "top_n": min(top_n, len(textos)),
            },
            timeout=60,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        res = r.json()["results"]
    except (ValueError, KeyError):
        return None
    return [
        (d["index"], float(d["relevance_score"]))
        for d in sorted(res, key=lambda d: d["relevance_score"], reverse=True)
    ]

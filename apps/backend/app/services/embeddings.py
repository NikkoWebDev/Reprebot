"""Embeddings.

Dos modos:
- API remota (recomendado para hosts con poca RAM): se activa con
  EMBEDDINGS_API_URL + EMBEDDINGS_API_KEY. El proceso se queda en ~150 MB.
- Local con fastembed: fallback si no hay API configurada. Carga el modelo en
  memoria (onnxruntime pide ~1 GB con un BERT-base) en el primer embed.

El formato de la API es el de OpenAI/Jina: POST {model, input, ...} y
respuesta {"data": [{"embedding": [...], "index": n}]}.
"""

import time

import httpx
import numpy as np

from app.core.config import get_settings

_model = None

# la API cuenta por tokens: lotes acotados para no pasarse del TPM del plan free
_BATCH = 64


def _use_api() -> bool:
    s = get_settings()
    return bool(s.embeddings_api_url and s.embeddings_api_key)


def _get_model():
    global _model
    if _model is None:
        # import perezoso: si se usa la API remota, fastembed/onnxruntime no se cargan
        from fastembed import TextEmbedding

        _model = TextEmbedding(get_settings().embeddings_model)
    return _model


def _embed_api(texts: list[str], task: str | None) -> np.ndarray:
    s = get_settings()
    salida: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        lote = texts[i : i + _BATCH]
        body: dict = {
            "model": s.embeddings_model,
            "input": lote,
            "normalized": True,
            # el router de preguntas arma texto libre; jina rechaza con 422 si pasa
            # del contexto del modelo, asi que se trunca en vez de fallar
            "truncate": True,
        }
        if task:
            body["task"] = task

        r = None
        for intento in range(5):
            try:
                r = httpx.post(
                    s.embeddings_api_url,
                    json=body,
                    headers={"Authorization": f"Bearer {s.embeddings_api_key}"},
                    timeout=120,
                )
            except httpx.TransportError:
                # DNS/red transitoria: no hay respuesta, se reintenta
                time.sleep(2**intento)
                continue
            if r.status_code == 429 or r.status_code >= 500:  # rate limit / error del server
                time.sleep(2**intento)
                continue
            break
        else:
            if r is None:
                raise RuntimeError("no se pudo contactar la API de embeddings (red)")

        if r.status_code >= 400:
            # incluye el motivo: la API devuelve detalle util en el cuerpo
            raise RuntimeError(f"embeddings API {r.status_code}: {r.text[:300]}")

        datos = sorted(r.json()["data"], key=lambda d: d["index"])
        salida.extend(d["embedding"] for d in datos)

    return np.array(salida, dtype=np.float32)


def embed(texts: list[str], task: str | None = None) -> np.ndarray:
    """task: "retrieval.query" para consultas, "retrieval.passage" para indexar.

    Solo lo usa la API remota (los modelos jina v3+ tienen adaptadores por tarea).
    """
    if not texts:
        return np.zeros((0, get_settings().embeddings_dim), dtype=np.float32)

    if _use_api():
        vecs = _embed_api(texts, task)
    else:
        # batch acotado: lotes grandes de onnxruntime disparan el uso de memoria
        # de activaciones y el sistema termina swapeando (embedding se vuelve lento)
        vecs = np.array(list(_get_model().embed(texts, batch_size=32)), dtype=np.float32)

    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms

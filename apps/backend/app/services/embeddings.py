import numpy as np
from fastembed import TextEmbedding

from app.core.config import get_settings

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    # lazy: la primera llamada carga/descarga el modelo (~600MB)
    global _model
    if _model is None:
        _model = TextEmbedding(get_settings().embeddings_model)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, get_settings().embeddings_dim), dtype=np.float32)
    # batch acotado: lotes grandes de onnxruntime disparan el uso de memoria
    # de activaciones y el sistema termina swapeando (embedding se vuelve lento)
    vecs = np.array(list(_get_model().embed(texts, batch_size=32)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms

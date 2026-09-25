"""BM25 léxico puro-python sobre los chunks del store.

Complementa la búsqueda densa: gana donde hay señal léxica exacta (nombres,
códigos SNIES/SIA, números de acuerdo, "libre elección"). Sin dependencias
nuevas; el índice se construye lazy y se reconstruye si cambia el corpus.
"""

import math
import re

_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+")

_K1 = 1.2
_B = 0.75

_INDEX: dict = {"n": -1, "idf": {}, "doc_len": [], "avg_len": 0.0, "tf": []}


def tokenizar(texto: str) -> list[str]:
    return _TOKEN_RE.findall((texto or "").lower())


def _reconstruir(textos: list[str]) -> None:
    n = len(textos)
    df: dict[str, int] = {}
    tf: list[dict[str, int]] = []
    doc_len = []
    for t in textos:
        toks = tokenizar(t)
        doc_len.append(len(toks))
        frec: dict[str, int] = {}
        for w in toks:
            frec[w] = frec.get(w, 0) + 1
        tf.append(frec)
        for w in frec:
            df[w] = df.get(w, 0) + 1
    avg = sum(doc_len) / n if n else 0.0
    idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
    _INDEX.update({"n": n, "idf": idf, "doc_len": doc_len, "avg_len": avg, "tf": tf})


def _asegurar(textos: list[str]) -> None:
    if _INDEX["n"] != len(textos):
        _reconstruir(textos)


def top(query: str, textos: list[str], k: int) -> list[tuple[int, float]]:
    """Devuelve [(índice_chunk, score)] ordenados, top-k."""
    if not query or not textos:
        return []
    _asegurar(textos)
    idf, tf, doc_len, avg = (
        _INDEX["idf"],
        _INDEX["tf"],
        _INDEX["doc_len"],
        _INDEX["avg_len"],
    )
    scores: dict[int, float] = {}
    for w in set(tokenizar(query)):
        w_idf = idf.get(w)
        if w_idf is None:
            continue
        for i, frec in enumerate(tf):
            f = frec.get(w, 0)
            if not f:
                continue
            denom = f + _K1 * (1 - _B + _B * (doc_len[i] / avg if avg else 1))
            scores[i] = scores.get(i, 0.0) + w_idf * (f * (_K1 + 1) / denom)
    return sorted(scores.items(), key=lambda p: p[1], reverse=True)[:k]

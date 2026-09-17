"""Reindexa data/ con el modelo de embeddings configurado.

Uso (desde apps/backend):
    python tools/reindex.py ["--data", "data"] [--dry-run]

Lee data/chunks.json, recalcula el vector de cada chunk con el proveedor
configurado (EMBEDDINGS_API_URL + EMBEDDINGS_API_KEY, o fastembed local) y
reescribe data/vectors.npy. Conserva toda la metadata de los chunks
(source_url, doc_type, program, year, title).

Hay que reindexar SIEMPRE que cambie EMBEDDINGS_MODEL: los vectores de un
modelo no sirven para otro.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services import embeddings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="directorio con chunks.json (default: settings.data_dir)")
    ap.add_argument("--dry-run", action="store_true", help="no escribe vectors.npy")
    args = ap.parse_args()

    s = get_settings()
    data = Path(args.data or s.data_dir)
    chunks_path = data / "chunks.json"
    if not chunks_path.exists():
        raise SystemExit(f"no existe {chunks_path}")

    chunks = json.loads(chunks_path.read_text())
    textos = [c["text"] for c in chunks]
    proveedor = "API " + s.embeddings_api_url if s.embeddings_api_url and s.embeddings_api_key else "local fastembed"
    print(f"chunks: {len(textos)} | modelo: {s.embeddings_model} | dim: {s.embeddings_dim} | proveedor: {proveedor}")

    vecs = embeddings.embed(textos, task="retrieval.passage")
    if vecs.shape != (len(textos), s.embeddings_dim):
        raise SystemExit(f"dimensiones inesperadas: {vecs.shape} (esperado ({len(textos)}, {s.embeddings_dim}))")

    if args.dry_run:
        print("dry-run: no se escribe nada")
        return

    np.save(data / "vectors.npy", vecs)
    print(f"escrito {data / 'vectors.npy'}  shape={vecs.shape}")


if __name__ == "__main__":
    main()

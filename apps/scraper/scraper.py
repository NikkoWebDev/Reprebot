"""CLI del scraper de documentos UNAL.

Uso:
    python scraper.py --dry-run                 # solo descubre candidatos
    python scraper.py                           # descubre, descarga e ingiere al store
    python scraper.py --max-pages 100 --delay 0.5
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")
os.environ.setdefault("DATA_DIR", str(BACKEND_DIR / "data"))

from app.core.config import get_settings
from app.services import chunker, embeddings, store
from crawler import Crawler
from extract import extract_text
from metadata import classify

SEEDS = [
    "https://ingenieria.bogota.unal.edu.co/es/departamentos/departamento-ingenieria-sistemas-industrial",
    "https://ingenieria.bogota.unal.edu.co/es/areas-curriculares/area-curricular-ingenieria-sistemas-industrial",
    "https://ingenieria.bogota.unal.edu.co/es/programas-academicos/ingenieria-de-sistemas-y-computacion",
    "https://ingenieria.bogota.unal.edu.co/es/programas-academicos/maestria-en-ingenieria-de-sistemas-y-computacion",
    "https://ingenieria.bogota.unal.edu.co/en/facultad-de-ingenieria-unal",
    "https://pregrado.unal.edu.co/marconormativo",
    "https://posgrados.unal.edu.co/normativa",
    "https://diracad.bogota.unal.edu.co/recursos/pdf/unal-aspirante/PEP/PEP-ing-sistemas-y-computacion.pdf",
    "https://ingbiomedica.unal.edu.co/files/Normatividad/ACUERDO_008_2008_CSU_Estatuto_Estudiantil.pdf",
    "https://bienestaruniversitario.medellin.unal.edu.co/integral/images/PDF-Seccion/Acuerdo_044_2009_CSU.PDF",
]

MAX_SIZE = 20 * 1024 * 1024
MIN_HTML_TEXT = 1500
MIN_DOC_TEXT = 200


def text_hash(chunks: list[str]) -> str:
    return hashlib.sha256("\n".join(chunks).encode()).hexdigest()


def existing_urls() -> set[str]:
    return {d.get("source_url") for d in store.store.list_docs() if d.get("source_url")}


def ingest_candidate(cand, client, known_hashes: set[str]) -> dict | str | None:
    try:
        r = client.get(cand.url)
    except Exception:  # noqa: BLE001 - red/URL arbitraria, cualquier error = candidato invalido
        return None
    if r.status_code >= 400 or len(r.content) > MAX_SIZE:
        return None

    try:
        text = extract_text(cand.url, r.headers.get("content-type", ""), r.content)
    except Exception as e:  # noqa: BLE001 - pypdf/HTML arbitrarios, cualquier error = descartar
        print(f"  ! extraccion fallida {cand.url}: {e!r}", file=sys.stderr)
        return None
    if not text.strip():
        return None
    if not cand.is_document and len(text) < MIN_HTML_TEXT:
        return None
    if cand.is_document and len(text) < MIN_DOC_TEXT:
        return None

    s = get_settings()
    chunks = chunker.chunk_text(text, s.chunk_size, s.chunk_overlap)
    if not chunks:
        return None

    h = text_hash(chunks)
    if h in known_hashes:
        return "dup"

    meta = classify(cand.url, cand.title)
    meta["source_url"] = cand.url
    meta["content_hash"] = h
    if cand.title:
        meta["title"] = cand.title

    vectors = embeddings.embed(chunks)
    name = Path(cand.url).name or cand.url
    return store.store.add(name, chunks, vectors, metadata=meta)


def load_candidates(path: Path) -> list:
    from crawler import Candidate

    data = json.loads(path.read_text())
    return [Candidate(**c) for c in data]


def save_candidates(path: Path, candidates: list) -> None:
    path.write_text(
        json.dumps([c.__dict__ for c in candidates], ensure_ascii=False, indent=1)
    )


def main():
    ap = argparse.ArgumentParser(
        description="Scraper de documentos UNAL Ingeniería Sistemas Bogotá"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="solo descubrir candidatos, sin descargar ni ingerir",
    )
    ap.add_argument("--max-pages", type=int, default=300)
    ap.add_argument("--max-docs", type=int, default=200)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="máximo de documentos a ingerir (0 = todos)",
    )
    ap.add_argument(
        "--candidates-file",
        type=Path,
        default=Path(__file__).parent / "candidates.json",
        help="caché de candidatos: si existe se carga, si no se descubre y guarda",
    )
    args = ap.parse_args()

    crawler = Crawler(
        delay=args.delay, max_pages=args.max_pages, max_docs=args.max_docs
    )
    if args.candidates_file.exists():
        print(f"Cargando candidatos desde {args.candidates_file}...")
        candidates = load_candidates(args.candidates_file)
    else:
        print(f"Descubriendo candidatos desde {len(SEEDS)} seeds...")
        candidates = crawler.crawl(SEEDS)
        save_candidates(args.candidates_file, candidates)
        print(f"Candidatos: {len(candidates)} (guardados en {args.candidates_file})")

    if args.dry_run:
        for c in candidates:
            kind = "PDF" if c.is_document else "HTML"
            print(f"  [{kind}] {c.url}")
        return

    store.store.load()
    known = existing_urls()
    known_hashes = {
        d.get("content_hash") for d in store.store.list_docs() if d.get("content_hash")
    }
    print(f"Ya en el store: {len(known)} documentos")

    client = crawler.client
    ingested = skipped = failed = 0
    for c in candidates:
        if c.url in known:
            skipped += 1
            continue
        if args.limit and ingested >= args.limit:
            break
        doc = None
        try:
            doc = ingest_candidate(c, client, known_hashes)
        except Exception as e:  # noqa: BLE001 - un candidato roto no debe tumbar la corrida
            print(f"  ! error ingiriendo {c.url}: {e!r}", file=sys.stderr)
        if doc == "dup":
            skipped += 1
        elif doc:
            known_hashes.add(doc.get("content_hash"))
            ingested += 1
            print(
                f"  + {doc['name']} ({doc.get('doc_type', '?')}, {doc['chunks']} chunks)"
            )
        else:
            failed += 1

    stats = store.store.stats()
    print(
        f"\nIngeridos: {ingested} | saltados (ya existían): {skipped} | fallidos: {failed}"
    )
    print(f"Store: {stats['documents']} documentos, {stats['chunks']} chunks")


if __name__ == "__main__":
    main()

"""Ingesta de normativa UNAL (acuerdos y resoluciones del marco estudiantil).

El visor oficial (legal.unal.edu.co/rlunal/home/doc.jsp) esta detras de reCAPTCHA
y el visor viejo (sisjurun/normas/Norma1.jsp) devuelve 404. Los snapshots del
Wayback Machine conservan el documento completo, asi que se ingieren desde ahi.

Uso:
    python normativa.py --dry-run   # valida que cada snapshot tenga la norma
    python normativa.py             # ingiere al store
"""

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from app.core.config import get_settings
from app.services import chunker, embeddings, store
from extract import extract_text
from metadata import classify

from scraper import (
    text_hash,
)

WB = "https://web.archive.org/web"

# (nombre, id de norma, patron que debe aparecer en el texto)
NORMS = [
    (
        "Acuerdo 033 de 2007 CSU - lineamientos formacion",
        "34245",
        r"ACUERDO\s*0?33\s*DE\s*2007",
    ),
    (
        "Acuerdo 044 de 2009 CSU - bienestar y convivencia",
        "35255",
        r"ACUERDO\s*0?44\s*DE\s*2009",
    ),
    (
        "Acuerdo 089 de 2014 Consejo Academico - posgrados",
        "66330",
        r"ACUERDO\s*0?89\s*DE\s*2014",
    ),
    ("Acuerdo 070 de 2009 Consejo Academico", "35443", r"ACUERDO\s*0?70\s*DE\s*2009"),
    ("Acuerdo 155 de 2014 CSU", "69337", r"ACUERDO\s*155\s*DE\s*2014"),
    ("Acuerdo 102 de 2013 CSU", "56987", r"ACUERDO\s*0?102\s*DE\s*2013"),
    ("Acuerdo 036 de 2012 CSU", "46769", r"ACUERDO\s*0?36\s*DE\s*2012"),
    ("Resolucion 037 de 2010 Rectoria", "36920", r"RESOLUCI[ÓO]N\s*0?37\s*DE\s*2010"),
    (
        "Resolucion 13 de 2020 Vicerrectoria Academica",
        "95482",
        r"RESOLUCI[ÓO]N\s*13\s*DE\s*2020",
    ),
    ("Acuerdo 026 de 2012 Consejo Academico", "47025", r"ACUERDO\s*0?26\s*DE\s*2012"),
]

# snapshots verificados en el CDX: id -> (visor, timestamp).
# el sistema cambio de visor con los años: sisjurun/Norma1.jsp (viejo), rlunal/doc.jsp (nuevo)
SNAPSHOTS = {
    "34245": ("norma1", "20120722155124"),
    "66330": ("doc", "20230326065636"),
    "35443": ("doc", "20230927211733"),
    "69337": ("doc", "20191117042505"),
    "56987": ("norma1", "20140913070634"),
    "36920": ("norma1", "20140913055528"),
    "95482": ("doc", "20220320022150"),
    "47025": ("norma1", "20131111051459"),
    "46769": ("doc", "20221129170414"),
}

# el 044 vive como PDF espejo en la sede Medellin
MEDELLIN_044 = (
    "https://bienestaruniversitario.medellin.unal.edu.co"
    "/integral/images/PDF-Seccion/Acuerdo_044_2009_CSU.PDF"
)


def snapshot_url(norm_id: str) -> str:
    if norm_id == "35255":
        return f"{WB}/2020/{MEDELLIN_044}"
    viewer, ts = SNAPSHOTS.get(norm_id, ("doc", "2023"))
    if viewer == "doc":
        target = f"http://www.legal.unal.edu.co/rlunal/home/doc.jsp?d_i={norm_id}"
    else:
        target = f"http://www.legal.unal.edu.co/sisjurun/normas/Norma1.jsp?i={norm_id}"
    return f"{WB}/{ts}/{target}"


def fetch_norm(name: str, norm_id: str, pattern: str, client, known_hashes):
    url = snapshot_url(norm_id)
    # el replay del wayback devuelve paginas a medias de vez en cuando: reintentar
    last = "sin intentos"
    for _ in range(3):
        res = _try_fetch(name, norm_id, pattern, url, client, known_hashes)
        if res["status"] in ("ok", "dup"):
            return res
        last = res
        time.sleep(1.5)
    return last


def _try_fetch(name, norm_id, pattern, url, client, known_hashes):
    try:
        r = client.get(url)
    except Exception as e:  # noqa: BLE001 - wayback puede resetear/timeoutear
        return {"status": "error", "detail": type(e).__name__}
    if r.status_code >= 400:
        return {"status": "error", "detail": f"HTTP {r.status_code}"}

    try:
        text = extract_text(str(r.url), r.headers.get("content-type", ""), r.content)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": f"extract: {type(e).__name__}"}

    if not re.search(pattern, text[:4000], re.IGNORECASE):
        return {
            "status": "mismatch",
            "detail": f"{len(text)} chars sin match de titulo",
        }

    s = get_settings()
    chunks = chunker.chunk_text(text, s.chunk_size, s.chunk_overlap)
    if not chunks:
        return {"status": "error", "detail": "sin chunks"}

    h = text_hash(chunks)
    if h in known_hashes:
        return {"status": "dup", "detail": ""}

    meta = classify(norm_id, name)
    meta["source_url"] = url
    meta["content_hash"] = h
    meta["title"] = name
    meta["doc_type"] = "normativa"

    vectors = embeddings.embed(chunks)
    doc = store.store.add(name, chunks, vectors, metadata=meta)
    known_hashes.add(h)
    return {"status": "ok", "detail": f"{len(chunks)} chunks", "doc": doc}


def main():
    ap = argparse.ArgumentParser(description="Ingesta de normativa UNAL")
    ap.add_argument("--dry-run", action="store_true", help="solo valida los snapshots")
    args = ap.parse_args()

    store.store.load()
    known_hashes = {
        d.get("content_hash") for d in store.store.list_docs() if d.get("content_hash")
    }
    known_urls = {d.get("source_url") for d in store.store.list_docs()}
    known_names = {d.get("name") for d in store.store.list_docs()}

    print(f"Store: {store.store.stats()['documents']} documentos")
    client = httpx.Client(
        follow_redirects=True,
        timeout=60,
        headers={"User-Agent": "ReprebotBot/1.0"},
        verify=False,
    )

    results = {}
    for name, norm_id, pattern in NORMS:
        if name in known_names or snapshot_url(norm_id) in known_urls:
            print(f"  = {name} (ya en store)")
            results[norm_id] = "skip"
            continue
        if args.dry_run:
            url = snapshot_url(norm_id)
            try:
                r = client.get(url)
                t = extract_text(
                    str(r.url), r.headers.get("content-type", ""), r.content
                )
                ok = bool(re.search(pattern, t[:4000], re.IGNORECASE))
                print(f"  {'OK ' if ok else 'NO '} {name} | {len(t)} chars")
            except Exception as e:  # noqa: BLE001
                print(f"  ERR {name} | {type(e).__name__}")
            continue

        res = fetch_norm(name, norm_id, pattern, client, known_hashes)
        mark = {"ok": "+", "dup": "=", "skip": "="}.get(res["status"], "!")
        print(f"  {mark} {name} | {res['status']} {res['detail']}")
        results[norm_id] = res["status"]

    if not args.dry_run:
        print(f"\nStore: {store.store.stats()}")


if __name__ == "__main__":
    main()

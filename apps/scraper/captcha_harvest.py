"""Cosecha de normativa del Regimen Legal UNAL con captcha manual.

El visor oficial (legal.unal.edu.co/rlunal/home/doc.jsp) exige resolver un
reCAPTCHA por sesion. Este script abre un Chromium visible, usted pasa el
captcha a mano una vez, y el script extrae el texto de cada norma y lo
ingiere al store. No burla el captcha: lo resuelve una persona.

Uso:
    python captcha_harvest.py                 # cosecha + ingiere (reemplaza)
    python captcha_harvest.py --keep           # no reemplaza lo ya en el store
    python captcha_harvest.py --harvest-only   # solo guarda los .txt
    python captcha_harvest.py --only 35255,66330
    python captcha_harvest.py --timeout 900    # seg por norma para el captcha

El perfil del navegador queda en .browser-profile/ para que la sesion
verificada sobreviva entre corridas.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import get_settings
from app.services import chunker, embeddings, store

from scraper import text_hash

HERE = Path(__file__).resolve().parent
TEXTS_DIR = HERE / "normativa_texts"
PROFILE_DIR = HERE / ".browser-profile"
DOC_URL = "https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i={}"

# (id en regimen legal, nombre, patron que debe aparecer en el documento)
# ids verificados contra la busqueda avanzada del propio visor (avz-ajx.jsp):
# nroid == parametro d_i de doc.jsp
NORMAS = [
    (
        "34245",
        "Acuerdo 033 de 2007 CSU - lineamientos formacion",
        r"ACUERDO\s*0?33\s*DE\s*2007",
    ),
    (
        "34983",
        "Acuerdo 008 de 2008 CSU - estatuto estudiantil academico",
        r"ACUERDO\s*0?08\s*DE\s*2008",
    ),
    (
        "37192",
        "Acuerdo 044 de 2009 CSU - estatuto bienestar y convivencia",
        r"ACUERDO\s*0?44\s*DE\s*2009",
    ),
    ("35443", "Acuerdo 070 de 2009 Consejo Academico", r"ACUERDO\s*0?70\s*DE\s*2009"),
    ("36920", "Resolucion 037 de 2010 Rectoria", r"RESOLUCI[ÓO]N\s*0?37\s*DE\s*2010"),
    ("46769", "Acuerdo 036 de 2012 CSU", r"ACUERDO\s*0?36\s*DE\s*2012"),
    ("47025", "Acuerdo 026 de 2012 Consejo Academico", r"ACUERDO\s*0?26\s*DE\s*2012"),
    ("56987", "Acuerdo 102 de 2013 CSU", r"ACUERDO\s*0?102\s*DE\s*2013"),
    (
        "66330",
        "Acuerdo 089 de 2014 Consejo Academico - posgrados",
        r"ACUERDO\s*0?89\s*DE\s*2014",
    ),
    ("69337", "Acuerdo 155 de 2014 CSU", r"ACUERDO\s*155\s*DE\s*2014"),
    (
        "95482",
        "Resolucion 13 de 2020 Vicerrectoria Academica",
        r"RESOLUCI[ÓO]N\s*13\s*DE\s*2020",
    ),
]

SLUG = re.compile(r"[^a-z0-9]+")
HEADING = re.compile(r"(ACUERDO|RESOLUCI[ÓO]N)\s+(\d+)\s+DE\s+(\d{4})", re.IGNORECASE)


def slug(text: str) -> str:
    return SLUG.sub("-", text.lower()).strip("-")[:60]


def page_text(page) -> str:
    """Texto del contenedor de la norma; cae al body si viene corto."""
    best = ""
    for sel in ("#info_texto", "main", "body"):
        try:
            t = page.inner_text(sel)
        except Exception:  # noqa: BLE001, S112 - durante la navegacion el DOM se destruye
            continue
        if len(t) > len(best):
            best = t
    return best


def wait_for_norm(page, pattern: str, timeout_s: int, grace_s: int = 25):
    """Espera el documento. Devuelve (estado, detalle).

    - ok:        el patron de la norma aparece
    - mismatch:  hay otra norma en pantalla (el id d_i esta equivocado)
    - captcha:   la pagina sigue gateada (texto corto) tras el timeout
    """
    start = time.monotonic()
    prompted = False
    while True:
        text = page_text(page)
        if re.search(pattern, text, re.IGNORECASE) and len(text) > 1000:
            return "ok", text
        # ya hay una norma renderizada pero no es la esperada
        h = HEADING.search(text)
        if h and len(text) > 1000:
            return "mismatch", f"{h.group(1)} {h.group(2)} de {h.group(3)}"
        elapsed = time.monotonic() - start
        if elapsed > grace_s and not prompted:
            print("     >> el visor pide captcha: resuelvalo en la ventana...")
            prompted = True
        if elapsed > timeout_s:
            return ("captcha" if len(text) < 400 else "timeout"), f"{len(text)} chars"
        page.wait_for_timeout(1500)


def _open_ctx(p):
    ctx = p.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=False,
        locale="es-CO",
        viewport={"width": 1280, "height": 900},
    )
    # reusar la pestaña inicial: si se abre otra, el usuario ve la equivocada
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for extra in ctx.pages[1:]:
        extra.close()
    return ctx, page


def _ensure_page(ctx, page):
    try:
        if page is not None and not page.is_closed():
            return page
    except Exception:  # noqa: BLE001, S110 - si la pestaña murio, se recrea abajo
        pass
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def _goto(page, url: str) -> bool:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return True
    except Exception:  # noqa: BLE001
        return False


def harvest(only: set[str] | None, timeout_s: int) -> list[dict]:
    from playwright.sync_api import sync_playwright

    TEXTS_DIR.mkdir(exist_ok=True)
    manifest = []
    normas = [n for n in NORMAS if not only or n[0] in only]

    with sync_playwright() as p:
        ctx, page = _open_ctx(p)
        for i, (norm_id, name, pattern) in enumerate(normas, 1):
            out = TEXTS_DIR / f"{norm_id}__{slug(name)}.txt"
            if out.exists() and out.stat().st_size > 500:
                print(f"  = [{i}/{len(normas)}] {name} (ya cosechada)")
                manifest.append({"id": norm_id, "name": name, "file": str(out)})
                continue

            print(f"  > [{i}/{len(normas)}] {name}")
            page = _ensure_page(ctx, page)
            if not _goto(page, DOC_URL.format(norm_id)):
                # el navegador pudo morir: relanzar el contexto una vez
                try:
                    ctx.close()
                except Exception:  # noqa: BLE001, S110 - el contexto ya podia estar muerto
                    pass
                ctx, page = _open_ctx(p)
                if not _goto(page, DOC_URL.format(norm_id)):
                    print("     ! no cargo (navegador caido)")
                    continue

            status, payload = wait_for_norm(page, pattern, timeout_s)
            if status == "mismatch":
                print(f"     ! ID {norm_id} trae otra norma: {payload}")
                continue
            if status != "ok":
                print(f"     ! sin contenido ({status}: {payload})")
                continue

            out.write_text(payload, encoding="utf-8")
            print(f"     + guardado {out.name} ({len(payload)} chars)")
            manifest.append({"id": norm_id, "name": name, "file": str(out)})

        ctx.close()

    (TEXTS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1)
    )
    return manifest


def ingest(manifest: list[dict], keep: bool) -> None:
    store.store.load()
    s = get_settings()
    by_name = {d["name"]: d["id"] for d in store.store.list_docs()}

    for item in manifest:
        name = item["name"]
        path = Path(item["file"])
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        chunks = chunker.chunk_text(text, s.chunk_size, s.chunk_overlap)
        if not chunks:
            print(f"  ! {name}: sin chunks")
            continue

        h = text_hash(chunks)
        if name in by_name:
            if keep:
                print(f"  = {name} (ya en store, --keep)")
                continue
            store.store.remove_doc(by_name[name])
            print(f"  ~ {name} (reemplaza version previa)")

        meta = {
            "doc_type": "normativa",
            "source_url": DOC_URL.format(item["id"]),
            "content_hash": h,
            "title": name,
            "year": int(re.search(r"\b(19|20)\d{2}\b", name).group(0)),
        }
        vectors = embeddings.embed(chunks)
        doc = store.store.add(name, chunks, vectors, metadata=meta)
        by_name[name] = doc["id"]
        print(f"  + {name} ({len(chunks)} chunks)")

    print(f"\nStore: {store.store.stats()}")


def main():
    ap = argparse.ArgumentParser(
        description="Cosecha de normativa UNAL con captcha manual"
    )
    ap.add_argument("--only", help="ids separados por coma a cosechar")
    ap.add_argument(
        "--timeout", type=int, default=300, help="seg por norma esperando el captcha"
    )
    ap.add_argument(
        "--harvest-only", action="store_true", help="solo guardar .txt, sin ingerir"
    )
    ap.add_argument(
        "--keep", action="store_true", help="no reemplazar normas ya en el store"
    )
    args = ap.parse_args()

    only = set(args.only.split(",")) if args.only else None
    manifest = harvest(only, args.timeout)
    if not manifest:
        print("Nada cosechado.")
        return
    if args.harvest_only:
        print(f"\n{len(manifest)} normas guardadas en {TEXTS_DIR}")
        return
    print("\nIngiriendo...")
    ingest(manifest, args.keep)


if __name__ == "__main__":
    main()

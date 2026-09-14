"""Diagnostico del visor de normativa: que renderiza realmente tras el captcha."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright

PROFILE = (Path(__file__).resolve().parent / ".browser-profile").resolve()
URL = "https://legal.unal.edu.co/rlunal/home/doc.jsp?d_i={}"


def main():
    norm_id = sys.argv[1] if len(sys.argv) > 1 else "35255"
    headless = "--headed" not in sys.argv
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=headless, locale="es-CO"
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(URL.format(norm_id), wait_until="domcontentloaded", timeout=60000)
        for i in range(6):
            page.wait_for_timeout(2500)
            t = page.inner_text("body")
            match = bool(re.search(r"ACUERDO\s*0?\d+", t, re.IGNORECASE))
            print(
                f"t={i * 2.5 + 2.5:.0f}s | url=...{page.url[-28:]} | "
                f"body={len(t)}ch | match_norma={match}"
            )
        n_ifr = page.locator("iframe").count()
        n_cap = page.locator("#for-captcha").count()
        print(f"iframes={n_ifr} | #for-captcha={n_cap}")
        print("cookies:", [(c["name"], c["domain"]) for c in ctx.cookies()])
        out = f"/tmp/opencode/diag-{norm_id}.png"
        page.screenshot(path=out)
        print("screenshot:", out)
        print("--- texto (300) ---")
        print(page.inner_text("body")[:300])
        ctx.close()


if __name__ == "__main__":
    main()

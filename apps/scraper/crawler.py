"""Descubrimiento BFS de documentos en sitios UNAL.

Respeta robots.txt (urllib.robotparser), limita el ritmo por host y filtra
por dominio y relevancia temática (ingeniería, sistemas, normatividad).
"""

import sys
import time
import urllib.robotparser
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "ReprebotBot/1.0 (scraper de documentos UNAL; contacto: reprebot@unal.edu.co)"
)

# dominios permitidos: match por sufijo
ALLOWED_HOST_SUFFIXES = ("unal.edu.co",)

# si la URL o el título contiene alguna de estas, el documento es candidato
RELEVANT_KEYWORDS = (
    "ingenieria",
    "sistemas",
    "computacion",
    "industrial",
    "normatividad",
    "normativa",
    "reglamento",
    "estatuto",
    "acuerdo",
    "resolucion",
    "plan de estudios",
    "pensum",
    "malla",
    "proyecto educativo",
    "pep",
    "acreditacion",
    "autoevaluacion",
    "mejoramiento",
    "trabajo de grado",
    "pasantia",
    "monitoria",
    "matricula",
    "admision",
    "posgrado",
    "maestria",
    "doctorado",
    "especializacion",
    "curricular",
    "programa",
    "grado",
    "egresado",
    "bienestar",
    "convivencia",
    "disciplinario",
    "traslado",
    "doble titulacion",
    "homologacion",
    "equivalencia",
    "calendario",
    "contenido programatico",
    "syllabus",
    "guia",
    "lineamiento",
    "instructivo",
    "circular",
    "acta",
    "oficio",
    "consejo",
    "comite",
    "beca",
    "estudiante",
    "docente",
    "profesor",
)

# si la URL contiene alguna de estas, se descarta (navegación, media, admin)
SKIP_KEYWORDS = (
    "/noticias",
    "/eventos",
    "/galeria",
    "/fotos",
    "/videos",
    "/boletin",
    "/prensa",
    "/twitter",
    "/facebook",
    "/instagram",
    "/youtube",
    "/login",
    "/registro",
    "/contacto",
    "/mapa",
    "/sitemap",
    "/feed",
    "/rss",
    "/wp-json",
    "/wp-content/plugins",
    "/wp-content/themes",
    "/wp-includes",
    "/administrator",
    "/administracion",
    "/intranet",
    "/correo",
    "/webmail",
    "/campus",
    "/sia",
    "/siga",
    "/hermes",
    "/banner",
    "/carrusel",
    "/slider",
)

SKIP_EXTENSIONS = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
    ".zip",
    ".rar",
    ".7z",
    ".exe",
    ".xml",
)

DOC_EXTENSIONS = (".pdf", ".html", ".htm", ".doc", ".docx", ".txt", ".md")


@dataclass
class Candidate:
    url: str
    title: str = ""
    content_type: str = ""
    size: int = 0
    discovered_from: str = ""
    is_document: bool = False
    depth: int = 0


@dataclass
class Crawler:
    delay: float = 1.0
    max_pages: int = 300
    max_docs: int = 200
    timeout: float = 30.0
    client: httpx.Client = field(
        default_factory=lambda: httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )
    )
    _robots: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)
    _last_hit: dict[str, float] = field(default_factory=dict)

    def _host(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    @staticmethod
    def _no_fragment(url: str) -> str:
        if not urlparse(url).netloc:
            return url
        path = urlparse(url).path.rstrip("/") or "/"
        return urljoin(url, path)

    def _allowed_domain(self, url: str) -> bool:
        host = self._host(url)
        return any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES)

    def _robots_parser(self, host: str) -> urllib.robotparser.RobotFileParser:
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"https://{host}/robots.txt")
            try:
                rp.read()
            except (OSError, urllib.error.URLError) as e:
                print(f"  ! sin robots.txt para {host}: {e!r}", file=sys.stderr)
            self._robots[host] = rp
        return self._robots[host]

    def _robots_allowed(self, url: str) -> bool:
        rp = self._robots_parser(self._host(url))
        return rp.can_fetch(USER_AGENT, url)

    def _throttle(self, url: str):
        host = self._host(url)
        now = time.monotonic()
        wait = self.delay - (now - self._last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _relevant(self, url: str, title: str) -> bool:
        hay = f"{url} {title}".lower()
        if any(k in hay for k in SKIP_KEYWORDS):
            return False
        return any(k in hay for k in RELEVANT_KEYWORDS)

    def _is_doc_url(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return path.endswith(DOC_EXTENSIONS)

    def _fetch(self, url: str) -> httpx.Response | None:
        self._throttle(url)
        try:
            r = self.client.get(url)
            if r.status_code >= 400:
                return None
            return r
        except httpx.HTTPError:
            return None

    def crawl(self, seeds: list[str]) -> list[Candidate]:
        queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
        seen: set[str] = set()
        docs: list[Candidate] = []
        pages = 0

        while queue and pages < self.max_pages and len(docs) < self.max_docs:
            url, depth = queue.popleft()
            url = self._no_fragment(url)
            if url in seen:
                continue
            seen.add(url)

            if not self._allowed_domain(url) or not self._robots_allowed(url):
                continue

            # raíces de idioma y home: ruido para un RAG de normativa
            path = urlparse(url).path.rstrip("/")
            if path in ("", "/es", "/en"):
                continue

            is_doc = self._is_doc_url(url)
            if not is_doc and not self._relevant(url, ""):
                continue

            r = self._fetch(url)
            if r is None:
                continue
            pages += 1

            ctype = r.headers.get("content-type", "").lower()
            size = len(r.content)

            if is_doc or ctype.startswith("application/pdf"):
                docs.append(
                    Candidate(
                        url=url,
                        content_type=ctype,
                        size=size,
                        discovered_from="seed" if depth == 0 else "link",
                        is_document=True,
                        depth=depth,
                    )
                )
                continue

            if not ctype.startswith("text/html"):
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            title = (soup.title.get_text(strip=True) if soup.title else "") or url

            if self._relevant(url, title):
                docs.append(
                    Candidate(
                        url=url,
                        title=title,
                        content_type=ctype,
                        size=size,
                        discovered_from="seed" if depth == 0 else "link",
                        is_document=False,
                        depth=depth,
                    )
                )

            if depth >= 3:
                continue
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                if not self._allowed_domain(href):
                    continue
                if href in seen:
                    continue
                if self._is_doc_url(href) or self._relevant(href, ""):
                    queue.append((href, depth + 1))

        return docs

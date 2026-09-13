"""Extracción de texto plano desde PDF y HTML."""

import io
import re

from bs4 import BeautifulSoup
from pypdf import PdfReader

_WS = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")


def extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages)


def extract_html(content: bytes, url: str = "") -> str:
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n")
    text = _WS.sub(" ", text)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def extract_text(url: str, content_type: str, content: bytes) -> str:
    ctype = content_type.lower()
    if "html" in ctype:
        return extract_html(content, url)
    if "pdf" in ctype:
        return extract_pdf(content)
    if url.lower().endswith(".pdf"):
        return extract_pdf(content)
    if url.lower().endswith((".html", ".htm")):
        return extract_html(content, url)
    if url.lower().endswith((".txt", ".md")):
        return content.decode("utf-8", errors="replace")
    raise ValueError(f"formato no soportado: {content_type or url}")

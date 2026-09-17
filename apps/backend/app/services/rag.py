import re
from collections.abc import Iterator

from app.core.config import get_settings
from app.services import ai_client, embeddings, store

REPO_URL = "https://github.com/Ansukic/Reprebot"
AUTORES = "Nikko (https://nikko.dev) y Julián (https://julsanchezc.dev)"

ATTRIBUTION = (
    f"Sobre tu origen: eres un fork de Reprebot ({REPO_URL}) convertido en microservicio "
    f"de API por {AUTORES}. Si preguntan quién te hizo, de dónde vienes o quién te "
    "construyó, respóndelo con el enlace del repositorio original y los enlaces de "
    "ambos autores."
)

_RULES = """- Responde SOLO con información presente en el contexto. No inventes normas, artículos ni fechas.
- Cita de qué documento proviene la información, por ejemplo: (Acuerdo 044 de 2009).
- Si el contexto no alcanza para responder, dilo claramente y sugiere consultar la fuente oficial.
- Responde en español y directo al punto."""

CHAT_PROMPT = f"""Eres Reprebot, asistente del Consejo de Estudiantes de Ingeniería de Sistemas (CEIS) de la Universidad Nacional de Colombia. Respondes preguntas sobre la UNAL usando únicamente el contexto proporcionado.

Reglas:
{_RULES}
- Máximo 3 párrafos.

{ATTRIBUTION}"""

FORUM_PROMPT = f"""Eres Reprebot y respondes públicamente en el foro del Consejo de Estudiantes de Ingeniería de Sistemas (CEIS) de la Universidad Nacional de Colombia. Tu respuesta la leerá toda la comunidad.

Reglas:
{_RULES}
- Tono de foro: cercano, útil, sin formalismos excesivos. Máximo 2 párrafos.
- Arranca respondiendo directamente la duda, sin saludar ni repetir la pregunta.

{ATTRIBUTION}"""

WHATSAPP_PROMPT = f"""Eres Reprebot y respondes en un chat de WhatsApp del Consejo de Estudiantes de Ingeniería de Sistemas (CEIS) de la Universidad Nacional de Colombia.

Reglas:
{_RULES}
- Responde en español con tono cercano de chat, como un compañero más.
- Máximo 2 o 3 frases cortas. Nada de párrafos largos.
- Arranca respondiendo directo, sin saludar ni repetir la pregunta.
- Cita el documento entre paréntesis, por ejemplo: (Acuerdo 044 de 2009).

{ATTRIBUTION}"""

_VACIO = "Aún no tengo conocimiento cargado. Sube documentos primero desde la pestaña de documentos."


def _context(results: list[dict]) -> str:
    return "\n\n".join(
        f"[{i}] ({r['doc_name']})\n{r['text']}" for i, r in enumerate(results, 1)
    )


def _sources(results: list[dict]) -> list[dict]:
    return [
        {
            "doc_id": r["doc_id"],
            "doc_name": r["doc_name"],
            "text": r["text"],
            "score": r["score"],
            "source_url": r.get("source_url"),
            "doc_type": r.get("doc_type"),
        }
        for r in results
    ]


def _retrieve(question: str, k: int) -> list[dict]:
    query_vec = embeddings.embed([question], task="retrieval.query")[0]
    return store.store.search(query_vec, k)


def _para_chat(texto: str) -> str:
    """Adapta el markdown del LLM al formato de WhatsApp y lo recorta."""
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", texto)
    t = re.sub(r"\*\*(.+?)\*\*", r"*\1*", t)
    t = re.sub(r"^\s*#{1,6}\s*(.+?)\s*$", r"*\1*", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*[-*]\s+", "• ", t, flags=re.MULTILINE)
    t = re.sub(r"[ \t]+$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    limite = get_settings().whatsapp_max_chars
    if len(t) <= limite:
        return t

    corte = max(
        t.rfind(". ", 0, limite) + 1,
        t.rfind(".\n", 0, limite) + 1,
        t.rfind("\n\n", 0, limite),
    )
    if corte <= 0:
        return t[:limite].rstrip() + "…"
    return t[:corte].rstrip()


def answer_question(question: str, k: int) -> dict:
    if not store.store.chunks:
        return {"answer": _VACIO, "sources": []}

    results = _retrieve(question, k)
    messages = [
        {"role": "system", "content": CHAT_PROMPT},
        {
            "role": "user",
            "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {question}",
        },
    ]
    return {"answer": ai_client.chat(messages), "sources": _sources(results)}


def answer_forum(title: str, body: str, k: int | None = None) -> dict:
    """Respuesta pública para el foro CEIS (se publica como el bot)."""
    pregunta = f"{title}\n\n{body}".strip()
    if not store.store.chunks:
        return {"answer": _VACIO, "sources": []}

    results = _retrieve(pregunta, k or 6)
    messages = [
        {"role": "system", "content": FORUM_PROMPT},
        {
            "role": "user",
            "content": f"Contexto:\n\n{_context(results)}\n\nPregunta del foro: {pregunta}",
        },
    ]
    return {"answer": ai_client.chat(messages), "sources": _sources(results)}


def answer_whatsapp(
    text: str, sender_name: str | None = None, k: int | None = None
) -> dict:
    """Respuesta corta para WhatsApp. La adapta al formato del chat."""
    if not store.store.chunks:
        return {"answer": _VACIO, "sources": []}

    results = _retrieve(text, k or 6)
    quien = f" ({sender_name})" if sender_name else ""
    messages = [
        {"role": "system", "content": WHATSAPP_PROMPT},
        {
            "role": "user",
            "content": (
                f"Contexto:\n\n{_context(results)}\n\n"
                f"Pregunta de WhatsApp{quien}: {text}"
            ),
        },
    ]
    answer = _para_chat(ai_client.chat(messages))
    return {"answer": answer, "sources": _sources(results)}


def answer_stream(question: str, k: int) -> Iterator[dict]:
    """Generador de eventos para /api/chat/stream (SSE)."""
    if not store.store.chunks:
        yield {"type": "sources", "sources": []}
        yield {"type": "delta", "text": _VACIO}
        yield {"type": "done"}
        return

    results = _retrieve(question, k)
    yield {"type": "sources", "sources": _sources(results)}

    messages = [
        {"role": "system", "content": CHAT_PROMPT},
        {
            "role": "user",
            "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {question}",
        },
    ]
    for delta in ai_client.stream_chat(messages):
        yield {"type": "delta", "text": delta}
    yield {"type": "done"}


def search(question: str, k: int) -> list[dict]:
    if not store.store.chunks:
        return []
    return _sources(_retrieve(question, k))

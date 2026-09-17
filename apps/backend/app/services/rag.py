from collections.abc import Iterator

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

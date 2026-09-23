import re
from collections.abc import Iterator

from fastapi import HTTPException

from app.core.config import get_settings
from app.services import ai_client, embeddings, store

ATTRIBUTION = (
    "Sobre tu identidad: si preguntan qué modelo eres o quién te hizo, responde que eres "
    "Kala AI 4.3, creado por Nikko.dev, en su edición Documental, adaptado a la Facultad "
    "de Ingeniería de la Universidad Nacional de Colombia. Agrega que quienes quieran "
    "acceso a la API de la edición Documental o de la edición general deben contactar "
    "por la página web de Nikko.dev (https://nikko.dev)."
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
- Responde SOLO con información presente en el contexto. No inventes normas, artículos ni fechas.
- Respuesta breve y directa: máximo 40 palabras o 3 líneas. Frases cortas, lenguaje claro.
- Si enumeras (requisitos, pasos, artículos), usa bullets de una línea cada uno.
- Cita la fuente al final entre paréntesis, ejemplo: (Acuerdo 044 de 2009).
- Si el contexto no alcanza, decilo en una línea y sugerí consultar la fuente oficial.
- Arranca respondiendo directo: sin saludos ni repetir la pregunta.

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

    results = _retrieve(text, k or 8)
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


def _cliente_chat(messages: list[dict], max_history: int) -> tuple[str, str, str, list[dict]]:
    """Separa (sistema, pregunta, pregunta_rag, historial) del payload.

    La pregunta es el último mensaje ``user`` (la que ve el LLM); el RAG
    recupera contra ``pregunta_rag``, que ancla los follow-ups ("¿y con
    nivelación?") con la respuesta anterior del asistente. El historial es
    todo lo anterior, en orden y acotado a los últimos ``max_history``
    mensajes. Si el cliente manda su propio ``system``, se usa.
    """
    limpios: list[dict] = []
    sistema = ""
    pregunta = ""
    idx_usuario = -1
    for m in messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if not content or role not in ("system", "user", "assistant"):
            continue
        limpios.append({"role": role, "content": content})
        if role == "system":
            sistema = content
        if role == "user":
            idx_usuario = len(limpios) - 1
            pregunta = content
    if idx_usuario == -1:
        return sistema, "", "", []
    historial = limpios[:idx_usuario]
    prev_asistente = next(
        (m["content"] for m in reversed(historial) if m["role"] == "assistant"), ""
    )
    pregunta_rag = pregunta
    if prev_asistente:
        pregunta_rag = f"{prev_asistente[:400].rstrip()}. {pregunta}"
    return sistema, pregunta, pregunta_rag, historial[-max_history:]


def answer_chat(
    messages: list[dict], k: int | None = None, max_history: int | None = None
) -> dict:
    """Chat con historial para /v1/chat/completions (formato kalaai).

    Recupera del RAG contra el último mensaje del usuario y le pasa al LLM el
    historial previo (acotado) para responder follow-ups. Devuelve answer,
    sources y usage.
    """
    mh = min(max_history or get_settings().chat_max_history, 50)
    sistema, pregunta, pregunta_rag, historial = _cliente_chat(messages, mh)
    if not pregunta:
        raise HTTPException(422, "falta un mensaje de usuario en messages")

    system = {"role": "system", "content": sistema or CHAT_PROMPT}
    if not store.store.chunks:
        resposta = ai_client.chat(
            [system, *historial, {"role": "user", "content": pregunta}],
            with_usage=True,
        )
        return {"answer": resposta[0], "sources": [], "usage": resposta[1]}

    results = _retrieve(pregunta_rag, k or 8)
    respuesta, usage = ai_client.chat(
        [
            system,
            *historial,
            {
                "role": "user",
                "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {pregunta}",
            },
        ],
        with_usage=True,
    )
    return {"answer": respuesta, "sources": _sources(results), "usage": usage}


def answer_chat_stream(
    messages: list[dict], k: int | None = None, max_history: int | None = None
) -> Iterator[dict]:
    """Versión SSE de answer_chat (mismo protocolo que /api/chat/stream)."""
    mh = min(max_history or get_settings().chat_max_history, 50)
    sistema, pregunta, pregunta_rag, historial = _cliente_chat(messages, mh)
    if not pregunta:
        raise HTTPException(422, "falta un mensaje de usuario en messages")

    system = {"role": "system", "content": sistema or CHAT_PROMPT}
    if not store.store.chunks:
        yield {"type": "sources", "sources": []}
        for delta in ai_client.stream_chat(
            [system, *historial, {"role": "user", "content": pregunta}]
        ):
            yield {"type": "delta", "text": delta}
        yield {"type": "done"}
        return

    results = _retrieve(pregunta_rag, k or 8)
    yield {"type": "sources", "sources": _sources(results)}
    for delta in ai_client.stream_chat(
        [
            system,
            *historial,
            {
                "role": "user",
                "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {pregunta}",
            },
        ]
    ):
        yield {"type": "delta", "text": delta}
    yield {"type": "done"}


def search(question: str, k: int) -> list[dict]:
    if not store.store.chunks:
        return []
    return _sources(_retrieve(question, k))

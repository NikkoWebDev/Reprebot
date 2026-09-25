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
- Si el contexto no alcanza para responder, dilo claramente y sugiere consultar la fuente oficial.
- Responde en español y directo al punto, sin saludos ni muletillas ("Hola, con gusto...", "Es importante mencionar...", "Cabe destacar..."). Arranca con la respuesta."""

SYSTEM_PROMPT_DEFAULT = f"""Eres Reprebot, asistente del Consejo de Estudiantes de Ingeniería de Sistemas (CEIS) de la Universidad Nacional de Colombia. Respondes preguntas sobre la UNAL usando únicamente el contexto proporcionado.

Reglas:
{_RULES}
- Markdown rico y variado: tablas para comparar créditos, materias o fechas; listas numeradas para trámites paso a paso; citas `>` para artículos normativos textuales.
- Cita la fuente en el texto, por ejemplo: (Acuerdo 044 de 2009).
- No agregues sección de "Fuentes" al final: las fuentes viajan en el campo `sources` de la respuesta.
- Máximo 3 párrafos o una estructura equivalente (tabla/lista + cierre).

{ATTRIBUTION}"""

SYSTEM_PROMPT_FORUM = f"""Eres Reprebot y respondes públicamente en el foro del Consejo de Estudiantes de Ingeniería de Sistemas (CEIS) de la Universidad Nacional de Colombia. Tu respuesta la leerá toda la comunidad.

Reglas:
{_RULES}
- Tono formal universitario, cercano y útil. Máximo 2 párrafos.
- Markdown limpio: si el contexto trae URLs oficiales, enlázalas en el texto.
- Arranca respondiendo directamente la duda, sin saludar ni repetir la pregunta.

{ATTRIBUTION}"""

SYSTEM_PROMPT_WHATSAPP = f"""Eres Reprebot y respondes en un chat de WhatsApp del Consejo de Estudiantes de Ingeniería de Sistemas (CEIS) de la Universidad Nacional de Colombia.

Reglas:
{_RULES}
- Respuesta breve: 2 o 3 líneas como máximo. Frases cortas, lenguaje claro.
- Sintaxis nativa de WhatsApp: *negrita* para lo clave. Prohibidos los encabezados (#) y las tablas.
- Si enumeras (requisitos, pasos), usa una línea corta por punto.
- No incluyas sección de fuentes ni URLs: se añaden automáticamente al final.

{ATTRIBUTION}"""

_VACIO = "Aún no tengo conocimiento cargado. Sube documentos primero desde la pestaña de documentos."


def _context(results: list[dict], max_chars: int = 12000) -> str:
    """Contexto para el prompt: dedup de fragmentos redundantes y tope de tamaño."""
    piezas = []
    total = 0
    for r in _dedup(results):
        t = (r["text"] or "").strip()
        if not t:
            continue
        if total + len(t) > max_chars and piezas:
            break
        piezas.append((r["doc_name"], t))
        total += len(t)
    return "\n\n".join(f"[{i}] ({nombre})\n{texto}" for i, (nombre, texto) in enumerate(piezas, 1))


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip().lower()


def _solape(a: str, b: str) -> float:
    """Similitud de Jaccard por tokens (0..1)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _dedup(results: list[dict]) -> list[dict]:
    """Filtra chunks duplicados o casi idénticos, manteniendo el orden por score."""
    vistos: list[str] = []
    unicos: list[dict] = []
    for r in results:
        norm = _normalizar(r.get("text", ""))
        if not norm:
            continue
        if any(norm in t or t in norm for t in vistos):
            continue
        if any(_solape(norm, t) > 0.85 for t in vistos):
            continue
        vistos.append(norm)
        unicos.append(r)
    return unicos


_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_SUPLTO_RE = re.compile(r"</?think>", re.IGNORECASE)


def extract_thinking(respuesta: str) -> tuple[str | None, str]:
    """Separa (razonamiento, respuesta limpia) de un texto con bloque <think>.

    Nunca pierde contenido: si el modelo no cerró la etiqueta, se quitan las
    etiquetas sueltas y se devuelve el texto como respuesta sin razonamiento.
    """
    texto = respuesta or ""
    m = _THINK_RE.search(texto)
    if m:
        thinking = m.group(1).strip() or None
        limpio = _THINK_RE.sub("", texto)
    else:
        thinking = None
        limpio = _THINK_SUPLTO_RE.sub("", texto)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio).strip()
    return thinking, limpio


_ORG_RE = re.compile(
    r"(CSU|consejo superior|consejo acad[eé]mico|consejo de facultad|rector[íi]a)",
    re.IGNORECASE,
)
_NORMA_RE = re.compile(
    r"(acuerdo|resoluci[oó]n)\s+0*(\d+)\s+de\s+(\d{4})", re.IGNORECASE
)
_MALLA_RE = re.compile(r"malla.*?(\d{4})", re.IGNORECASE)


def _etiqueta_fuente(doc_name: str) -> str:
    """Etiqueta ultra-compacta para WhatsApp: 'Ac. 044/2009 CSU', 'Malla 2023'."""
    n = doc_name or ""
    m = _NORMA_RE.search(n)
    if m:
        tipo = "Ac." if m.group(1).lower().startswith("ac") else "Res."
        org = _ORG_RE.search(n)
        sigla = ""
        if org:
            o = org.group(1).lower()
            sigla = (
                " CSU"
                if "csu" in o or "superior" in o
                else " CA"
                if "acad" in o
                else " CF"
                if "facultad" in o
                else " Rectoría"
            )
        return f"{tipo} {m.group(2)}/{m.group(3)}{sigla}"
    m = _MALLA_RE.search(n)
    if m:
        flex = " flexible" if "flexible" in n.lower() else ""
        return f"Malla{flex} {m.group(1)}"
    if "pep" in n.lower():
        return "PEP Sistemas"
    legible = re.sub(r"\.(pdf|txt|md)$", "", n, flags=re.IGNORECASE)
    legible = legible.replace("_", " ").strip()
    return legible[:42].rstrip()


def format_whatsapp_sources(sources: list[dict], max_fuentes: int = 3) -> str:
    """Fuentes en 1-2 líneas para WhatsApp. Vacío si no hay fuentes."""
    etiquetas: list[str] = []
    for s in sources or []:
        e = _etiqueta_fuente(s.get("doc_name", ""))
        if e and e not in etiquetas:
            etiquetas.append(e)
    if not etiquetas:
        return ""
    return "📚 *Fuentes:* " + " • ".join(etiquetas[:max_fuentes])


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
    """Retrieval híbrido: denso top-N + BM25 top-N, fusión RRF y rerank Jina.

    Con ambos flags apagados degrada al denso puro anterior. Si el reranker
    falla, se usa el orden RRF. Nunca devuelve vacío por el reranker.
    """
    from app.services import bm25, rerank

    s = get_settings()
    if not store.store.chunks:
        return []
    query_vec = embeddings.embed([question], task="retrieval.query")[0]
    n_cand = max(s.rag_candidates, k)
    densos = store.store.search(query_vec, n_cand)
    if not densos or (not s.rag_bm25 and not s.rag_rerank):
        return densos[:k]

    id_a_idx = {c["id"]: i for i, c in enumerate(store.store.chunks)}
    listas = [[id_a_idx[d["id"]] for d in densos if d["id"] in id_a_idx]]
    if s.rag_bm25:
        textos = [c.get("text", "") for c in store.store.chunks]
        listas.append([i for i, _ in bm25.top(question, textos, n_cand)])

    fusion = rerank.rrf(listas)[: max(s.rag_rerank_top, k)]
    if s.rag_rerank:
        textos_f = [store.store.chunks[i].get("text", "") for i in fusion]
        rr = rerank.rerank(question, textos_f, k)
        if rr is not None:
            return [_ficha(fusion[i], rel) for i, rel in rr]

    return [_ficha(idx, 1.0 / (1 + r)) for r, idx in enumerate(fusion[:k])]


def _ficha(idx: int, score: float) -> dict:
    c = store.store.chunks[idx]
    return {
        "doc_id": c["doc_id"],
        "doc_name": c["doc_name"],
        "text": c["text"],
        "score": float(score),
        "source_url": c.get("source_url"),
        "doc_type": c.get("doc_type"),
    }


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


def _con_razonamiento(messages: list[dict]) -> tuple[str | None, str]:
    """Llama al LLM y devuelve (reasoning, respuesta limpia).

    El reasoning es el nativo de Groq/gpt-oss; si el modelo emitiera etiquetas
    <think> literales, se extraen por regex como respaldo. La respuesta siempre
    sale sin bloques de razonamiento.
    """
    contenido, _, nativo = ai_client.chat(messages, with_usage=True)
    tag_think, limpio = extract_thinking(contenido)
    return (nativo or tag_think or None), limpio


def answer_question(question: str, k: int) -> dict:
    if not store.store.chunks:
        return {"answer": _VACIO, "sources": [], "reasoning": None}

    results = _retrieve(question, k)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_DEFAULT},
        {
            "role": "user",
            "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {question}",
        },
    ]
    thinking, answer = _con_razonamiento(messages)
    return {"answer": answer, "sources": _sources(results), "reasoning": thinking}


def answer_forum(title: str, body: str, k: int | None = None) -> dict:
    """Respuesta pública para el foro CEIS (se publica como el bot)."""
    pregunta = f"{title}\n\n{body}".strip()
    if not store.store.chunks:
        return {"answer": _VACIO, "sources": []}

    results = _retrieve(pregunta, k or 6)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_FORUM},
        {
            "role": "user",
            "content": f"Contexto:\n\n{_context(results)}\n\nPregunta del foro: {pregunta}",
        },
    ]
    _, answer = _con_razonamiento(messages)
    return {"answer": answer, "sources": _sources(results)}


def answer_whatsapp(
    text: str, sender_name: str | None = None, k: int | None = None
) -> dict:
    """Respuesta corta para WhatsApp: sin <think>, formato nativo y fuentes compactas."""
    if not store.store.chunks:
        return {"answer": _VACIO, "sources": []}

    results = _retrieve(text, k or 8)
    quien = f" ({sender_name})" if sender_name else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_WHATSAPP},
        {
            "role": "user",
            "content": (
                f"Contexto:\n\n{_context(results)}\n\n"
                f"Pregunta de WhatsApp{quien}: {text}"
            ),
        },
    ]
    _, limpio = _con_razonamiento(messages)
    answer = _para_chat(limpio)
    fuentes = format_whatsapp_sources(_sources(results))
    if fuentes:
        answer = f"{answer}\n\n{fuentes}"
    return {"answer": answer, "sources": _sources(results)}


def _repartir(deltas: Iterator[str | tuple[str, str]]) -> Iterator[tuple[str, str]]:
    """Divide un stream en eventos ("thought"|"delta", texto).

    Vía nativa: tuplas ("reasoning"|"content") de Groq van directo a thought/delta.
    Vía legacy: strings con bloque <think>...</think> se separan por regex.
    Si no hay razonamiento o el bloque queda sin cerrar, nada se pierde: todo
    termina como delta.
    """
    buf = ""
    modo = "inicio"  # inicio | think | fuera
    nativo = False
    for item in deltas or []:
        if isinstance(item, tuple):
            kind, texto = item
            if not texto:
                continue
            if kind == "reasoning":
                nativo = True
                if buf and "<think>" not in buf.lower():
                    yield ("delta", buf)
                    buf = ""
                yield ("thought", texto)
                continue
            if nativo:
                if buf:
                    yield ("delta", buf)
                    buf = ""
                yield ("delta", texto)
                continue
            item = texto
        d = item
        if modo == "fuera":
            yield ("delta", d)
            continue
        buf += d
        if modo == "inicio":
            i = buf.lower().find("<think>")
            if i == -1:
                if len(buf) > 400:
                    yield ("delta", buf)
                    buf = ""
                    modo = "fuera"
                continue
            if i > 0:
                yield ("delta", buf[:i])
            buf = buf[i + len("<think>") :]
            modo = "think"
        if modo == "think":
            j = buf.lower().find("</think>")
            if j == -1:
                if len(buf) > 16:
                    yield ("thought", buf[:-16])
                    buf = buf[-16:]
                continue
            yield ("thought", buf[:j])
            resto = buf[j + len("</think>") :]
            buf = ""
            modo = "fuera"
            if resto:
                yield ("delta", resto)
    if buf:
        yield ("delta", buf)


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
        {"role": "system", "content": SYSTEM_PROMPT_DEFAULT},
        {
            "role": "user",
            "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {question}",
        },
    ]
    pensado: list[str] = []
    for tipo, texto in _repartir(ai_client.stream_chat(messages)):
        if tipo == "thought":
            pensado.append(texto)
            yield {"type": "thought", "text": texto}
        else:
            yield {"type": "delta", "text": texto}
    yield {"type": "done", "reasoning": "".join(pensado) or None}


def _cliente_chat(messages: list[dict], max_history: int) -> tuple[str, str, list[dict]]:
    """Separa (sistema, pregunta, historial) del payload.

    La pregunta es el último mensaje ``user``; el historial es todo lo
    anterior, en orden y acotado a los últimos ``max_history`` mensajes. Si el
    cliente manda su propio ``system``, se usa.
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
        return sistema, "", []
    return sistema, pregunta, limpios[:idx_usuario][-max_history:]


_FOLLOWUP_RE = re.compile(
    r"^(y|e|pero|entonces|eso|esto|ese|esa|esos|esas|cu[aá]l|cu[aá]les|c[oó]mo|d[oó]nde|por qu[eé]|qu[eé]|qui[eé]n)",
    re.IGNORECASE,
)


def _es_followup(pregunta: str) -> bool:
    """Heurística barata: mensajes cortos o que arrancan como continuación."""
    p = (pregunta or "").strip()
    return bool(p) and (len(p.split()) <= 12 or bool(_FOLLOWUP_RE.match(p)))


def _ancla(pregunta: str, historial: list[dict]) -> str:
    """Query anclada con la respuesta anterior (sin LLM, ya validada con rank 1)."""
    prev = next(
        (m["content"] for m in reversed(historial) if m["role"] == "assistant"), ""
    )
    prev = prev.strip()
    if prev:
        return f"{prev[:400].rstrip()}. {pregunta}"
    return pregunta


def _reescribir_query(pregunta: str, historial: list[dict]) -> str:
    """Query autónoma y contextualizada para el retrieval.

    Solo usa el LLM cuando la pregunta parece un follow-up; en el resto de
    casos usa el anclaje barato. Ante cualquier fallo, cae al anclaje.
    """
    if not historial or not _es_followup(pregunta):
        return _ancla(pregunta, historial)
    convo = "\n".join(
        f"{m['role']}: {m['content'][:600]}" for m in historial[-6:]
    )
    try:
        q = ai_client.chat(
            [
                {
                    "role": "system",
                    "content": "Reescribe la última pregunta del usuario como una consulta autónoma de búsqueda sobre normativa de la Universidad Nacional de Colombia, incorporando el contexto del historial. Devuelve SOLO la consulta, sin comillas ni explicación.",
                },
                {"role": "user", "content": f"Historial:\n{convo}\n\nPregunta: {pregunta}"},
            ],
            temperature=0.1,
            max_tokens=120,
        )
        q = q.strip().strip("\"'“”‘’").strip()
        return q or _ancla(pregunta, historial)
    except HTTPException:
        return _ancla(pregunta, historial)


def answer_chat(
    messages: list[dict], k: int | None = None, max_history: int | None = None
) -> dict:
    """Chat con historial para /v1/chat/completions (formato kalaai).

    Recupera del RAG contra una query autónoma (reescrita con LLM solo en
    follow-ups, anclaje barato en el resto) y le pasa al LLM el historial
    previo acotado. Devuelve answer, sources, usage y reasoning.
    """
    mh = min(max_history or get_settings().chat_max_history, 50)
    sistema, pregunta, historial = _cliente_chat(messages, mh)
    if not pregunta:
        raise HTTPException(422, "falta un mensaje de usuario en messages")

    system = {"role": "system", "content": sistema or SYSTEM_PROMPT_DEFAULT}
    if not store.store.chunks:
        resposta = ai_client.chat(
            [system, *historial, {"role": "user", "content": pregunta}],
            with_usage=True,
        )
        return {
            "answer": resposta[0],
            "sources": [],
            "usage": resposta[1],
            "reasoning": resposta[2] or None,
        }

    results = _retrieve(_reescribir_query(pregunta, historial), k or 8)
    respuesta, usage, nativo = ai_client.chat(
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
    tag_think, answer = extract_thinking(respuesta)
    return {
        "answer": answer,
        "sources": _sources(results),
        "usage": usage,
        "reasoning": nativo or tag_think or None,
    }


def answer_chat_stream(
    messages: list[dict], k: int | None = None, max_history: int | None = None
) -> Iterator[dict]:
    """Versión SSE de answer_chat (mismo protocolo que /api/chat/stream)."""
    mh = min(max_history or get_settings().chat_max_history, 50)
    sistema, pregunta, historial = _cliente_chat(messages, mh)
    if not pregunta:
        raise HTTPException(422, "falta un mensaje de usuario en messages")

    system = {"role": "system", "content": sistema or SYSTEM_PROMPT_DEFAULT}
    if not store.store.chunks:
        yield {"type": "sources", "sources": []}
        for delta in ai_client.stream_chat(
            [system, *historial, {"role": "user", "content": pregunta}]
        ):
            yield {"type": "delta", "text": delta}
        yield {"type": "done"}
        return

    results = _retrieve(_reescribir_query(pregunta, historial), k or 8)
    yield {"type": "sources", "sources": _sources(results)}
    pensado: list[str] = []
    for tipo, texto in _repartir(
        ai_client.stream_chat(
            [
                system,
                *historial,
                {
                    "role": "user",
                    "content": f"Contexto:\n\n{_context(results)}\n\nPregunta: {pregunta}",
                },
            ]
        )
    ):
        if tipo == "thought":
            pensado.append(texto)
            yield {"type": "thought", "text": texto}
        else:
            yield {"type": "delta", "text": texto}
    yield {"type": "done", "reasoning": "".join(pensado) or None}


def search(question: str, k: int) -> list[dict]:
    if not store.store.chunks:
        return []
    return _sources(_retrieve(question, k))

"""
/api/forum/answer
Genera la respuesta de Reprebot a una pregunta del foro CEIS y la publica
como el usuario bot (Supabase, service role).

Se puede llamar desde un Database Webhook de Supabase (INSERT en questions)
o directamente desde el frontend.
"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.models.chat_message import ForumAnswerRequest, ForumAnswerResponse
from app.services import rag, supabase_admin

router = APIRouter()


def _normalizar(req: ForumAnswerRequest) -> ForumAnswerRequest:
    """Acepta el payload crudo del webhook (record) o el formulario normalizado."""
    if not req.record:
        return req
    r = req.record
    return ForumAnswerRequest(
        question_id=req.question_id or r.get("id"),
        title=req.title or (r.get("title") or ""),
        body=req.body or (r.get("body") or ""),
        tag=req.tag or r.get("tag"),
    )


def _cuerpo_con_fuentes(answer: str, sources: list[dict]) -> str:
    """Respuesta + fuentes enlazadas, como queda guardada en el foro."""
    lineas = [answer.strip(), "", "---", "**Fuentes:**"]
    vistas: set[str] = set()
    for s in sources:
        url = s.get("source_url")
        if url and url not in vistas:
            vistas.add(url)
            lineas.append(f"- [{s.get('doc_name') or 'documento'}]({url})")
    if not vistas:
        lineas = lineas[:1]
    return "\n".join(lineas)


@router.post(
    "/forum/answer",
    response_model=ForumAnswerResponse,
    dependencies=[Depends(rate_limit)],
)
def forum_answer(req: ForumAnswerRequest, x_api_key: str | None = Header(None)):
    s = get_settings()
    if s.forum_api_key and x_api_key != s.forum_api_key:
        raise HTTPException(401, "api key inválida")

    req = _normalizar(req)
    if not (req.title.strip() or req.body.strip()):
        raise HTTPException(422, "falta el título o el cuerpo de la pregunta")

    tags = s.forum_tags_list
    if req.tag and tags and req.tag.strip().lower() not in tags:
        return ForumAnswerResponse(answer="", sources=[], posted=False, skipped="tag")

    if (
        s.forum_enabled
        and req.question_id
        and supabase_admin.has_ai_answer(req.question_id)
    ):
        return ForumAnswerResponse(
            answer="", sources=[], posted=False, skipped="already"
        )

    result = rag.answer_forum(req.title, req.body)

    posted = False
    if s.forum_enabled and req.question_id:
        supabase_admin.insert_answer(
            req.question_id, _cuerpo_con_fuentes(result["answer"], result["sources"])
        )
        posted = True

    return ForumAnswerResponse(
        answer=result["answer"], sources=result["sources"], posted=posted
    )

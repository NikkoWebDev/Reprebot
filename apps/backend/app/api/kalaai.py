"""
/v1/chat/completions — chat con historial para el frontend kalaai.

Formato propio (no OpenAI estricto): el cliente manda ``messages[]`` con el
historial completo y el backend recupera del RAG contra el último mensaje de
usuario. Si ``stream: true`` responde en SSE con el mismo protocolo de eventos
que /api/chat/stream (sources → delta… → done).
"""

import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.ratelimit import rate_limit
from app.models.chat_message import KalaaiChatRequest, KalaaiChatResponse
from app.services import rag

router = APIRouter(prefix="/v1")


def _gate_api_key(x_api_key: str | None) -> None:
    key = get_settings().whatsapp_api_key
    if key and x_api_key != key:
        raise HTTPException(401, "api key inválida")


@router.post(
    "/chat/completions",
    response_model=KalaaiChatResponse,
    dependencies=[Depends(rate_limit)],
)
def kalaai_chat_completions(
    req: KalaaiChatRequest, x_api_key: str | None = Header(None)
):
    _gate_api_key(x_api_key)
    mensajes = [m.model_dump() for m in req.messages]

    if req.stream:
        def eventos():
            try:
                for ev in rag.answer_chat_stream(
                    mensajes, k=req.k, max_history=req.max_history
                ):
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            except HTTPException as e:
                yield f"data: {json.dumps({'type': 'error', 'detail': e.detail}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            eventos(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return rag.answer_chat(mensajes, k=req.k, max_history=req.max_history)
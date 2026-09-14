"""
/api/chat
Pregunta al RAG: recupera contexto y genera respuesta con fuentes.
/api/chat/stream — la misma respuesta en SSE (texto a texto).
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.ratelimit import rate_limit
from app.models.chat_message import ChatRequest, ChatResponse
from app.services import rag

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit)])
def chat(req: ChatRequest):
    return rag.answer_question(req.question, req.k)


@router.post("/chat/stream", dependencies=[Depends(rate_limit)])
def chat_stream(req: ChatRequest):
    def eventos():
        for ev in rag.answer_stream(req.question, req.k):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        eventos(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

"""
/api/whatsapp/answer
Responde una pregunta etiquetada al bot en un grupo de WhatsApp, con el mismo
RAG del chat pero en tono corto de chat. Lo llama el puente de apps/whatsapp,
que no usa el frontend.
"""

from fastapi import APIRouter, Header, HTTPException

from app.core.config import get_settings
from app.models.chat_message import WhatsAppAnswerRequest, WhatsAppAnswerResponse
from app.services import rag

router = APIRouter()


@router.post("/whatsapp/answer", response_model=WhatsAppAnswerResponse)
def whatsapp_answer(req: WhatsAppAnswerRequest, x_api_key: str | None = Header(None)):
    s = get_settings()
    if s.whatsapp_api_key and x_api_key != s.whatsapp_api_key:
        raise HTTPException(401, "api key inválida")

    if not req.text.strip():
        raise HTTPException(422, "falta el texto de la pregunta")

    # Sin rate_limit por IP: el puente de apps/whatsapp ya throttlea por usuario
    # y todo el grupo sale por la misma IP, así que el limiter los mezclaría.
    result = rag.answer_whatsapp(req.text, req.sender_name)
    return WhatsAppAnswerResponse(answer=result["answer"], sources=result["sources"])

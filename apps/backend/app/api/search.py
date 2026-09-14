"""
/api/search
Solo recuperación: devuelve los chunks más relevantes sin generar respuesta.
"""

from fastapi import APIRouter, Depends

from app.core.ratelimit import rate_limit
from app.models.chat_message import SearchRequest, SearchResponse
from app.services import rag

router = APIRouter()


@router.post(
    "/search", response_model=SearchResponse, dependencies=[Depends(rate_limit)]
)
def search(req: SearchRequest):
    return {"sources": rag.search(req.question, req.k)}

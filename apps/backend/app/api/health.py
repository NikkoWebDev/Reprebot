"""
/api/health
Estado del servicio y del conocimiento cargado.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.services import store

router = APIRouter()


@router.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        **store.store.stats(),
        "chat_model": s.groq_chat_model,
        "embeddings_model": s.embeddings_model,
        # solo presencia (nunca valores): si search/chat dan 500, aquí se ve
        # en un GET si falta alguna key en el dashboard.
        "keys": {
            "groq": bool(s.groq_api_key),
            "embeddings_api": bool(s.embeddings_api_url and s.embeddings_api_key),
            "embeddings_mode": (
                "remote"
                if s.embeddings_api_url and s.embeddings_api_key
                else "local"
            ),
        },
    }

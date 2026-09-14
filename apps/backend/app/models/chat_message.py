from pydantic import BaseModel, Field

from app.core.config import get_settings


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default_factory=lambda: get_settings().top_k, ge=1, le=20)


class SourceChunk(BaseModel):
    doc_id: str
    doc_name: str
    text: str
    score: float
    source_url: str | None = None
    doc_type: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]


class SearchRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default_factory=lambda: get_settings().top_k, ge=1, le=20)


class SearchResponse(BaseModel):
    sources: list[SourceChunk]


class DocumentInfo(BaseModel):
    id: str
    name: str
    chunks: int
    added_at: str
    source_url: str | None = None
    doc_type: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class ForumAnswerRequest(BaseModel):
    """Pregunta del foro CEIS. Acepta el payload crudo de un Database Webhook
    de Supabase (con `record`) o el formulario normalizado."""

    question_id: str | None = None
    title: str = ""
    body: str = ""
    tag: str | None = None
    record: dict | None = None


class ForumAnswerResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    posted: bool = False
    skipped: str | None = None

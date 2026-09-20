from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings


class SourceChunk(BaseModel):
    doc_id: str
    doc_name: str
    text: str
    score: float
    source_url: str | None = None
    doc_type: str | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class KalaaiChatRequest(BaseModel):
    """Chat con historial para /v1/chat/completions (formato kalaai)."""

    messages: list[ChatMessage] = Field(min_length=1)
    k: int = Field(default_factory=lambda: get_settings().top_k, ge=1, le=20)
    stream: bool = False
    max_history: int | None = Field(default=None, ge=1, le=50)


class KalaaiChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    usage: dict = Field(default_factory=dict)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default_factory=lambda: get_settings().top_k, ge=1, le=20)


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


class WhatsAppAnswerRequest(BaseModel):
    text: str = ""
    sender_name: str | None = None


class WhatsAppAnswerResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    skipped: str | None = None

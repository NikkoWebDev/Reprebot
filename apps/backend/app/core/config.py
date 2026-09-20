from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    groq_api_key: str
    groq_chat_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    embeddings_model: str = "jinaai/jina-embeddings-v2-base-es"
    embeddings_dim: int = 768

    # Embeddings por API remota (OpenAI/Jina). Si estan seteadas, no se carga
    # fastembed en memoria (~1 GB con un BERT-base) y el proceso queda en ~150 MB.
    embeddings_api_url: str = ""
    embeddings_api_key: str = ""

    data_dir: str = "data"
    cors_origins: str = "*"
    admin_token: str = ""

    top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Integración con el foro CEIS (Supabase, service role)
    supabase_url: str = ""
    supabase_service_key: str = ""
    forum_bot_user_id: str = ""
    forum_api_key: str = ""
    forum_tag_allowlist: str = "Duda académica,Inscripciones y trámites,Bienestar,Otro"
    rate_limit_per_min: int = 20

    # Chat con historial (endpoint /v1/chat/completions)
    chat_max_history: int = 10

    # Puente de WhatsApp (apps/whatsapp)
    whatsapp_api_key: str = ""
    whatsapp_max_chars: int = 700

    @property
    def cors_origins_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def forum_tags_list(self) -> list[str]:
        return [
            t.strip().lower() for t in self.forum_tag_allowlist.split(",") if t.strip()
        ]

    @property
    def forum_enabled(self) -> bool:
        return bool(
            self.supabase_url and self.supabase_service_key and self.forum_bot_user_id
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Cliente mínimo de Supabase (REST/PostgREST) con service role.

Solo se usa desde el endpoint del foro para leer/insertar respuestas. No usa el
SDK: con httpx alcanza y evita una dependencia extra.

La service key salta RLS, por eso vive únicamente en el servidor.
"""

import httpx
from fastapi import HTTPException

from app.core.config import get_settings

MAX_BODY = 8000  # límite del check en la tabla answers


def _rest(path: str) -> str:
    return f"{get_settings().supabase_url.rstrip('/')}/rest/v1/{path}"


def _headers(prefer: str | None = None) -> dict[str, str]:
    key = get_settings().supabase_service_key
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _raise(r: httpx.Response, accion: str) -> None:
    if r.status_code >= 400:
        raise HTTPException(
            502, f"supabase falló al {accion}: {r.status_code} {r.text[:200]}"
        )


def has_ai_answer(question_id: str) -> bool:
    """True si Reprebot ya respondió esa pregunta (idempotencia del webhook)."""
    r = httpx.get(
        _rest("answers"),
        params={
            "question_id": f"eq.{question_id}",
            "ai_generated": "eq.true",
            "select": "id",
            "limit": "1",
        },
        headers=_headers(),
        timeout=20,
    )
    _raise(r, "consultar respuestas")
    return bool(r.json())


def insert_answer(question_id: str, body: str) -> dict:
    """Inserta la respuesta de Reprebot como el usuario bot del foro."""
    s = get_settings()
    payload = {
        "question_id": question_id,
        "author_id": s.forum_bot_user_id,
        "body": body[:MAX_BODY],
        "ai_generated": True,
    }
    r = httpx.post(
        _rest("answers"),
        headers=_headers("return=representation"),
        json=payload,
        timeout=20,
    )
    _raise(r, "insertar respuesta")
    filas = r.json()
    return filas[0] if filas else payload

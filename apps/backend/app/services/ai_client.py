import json
from collections.abc import Iterator

import httpx
from fastapi import HTTPException

from app.core.config import get_settings


def _body(messages: list[dict], model: str | None, temperature: float) -> dict:
    s = get_settings()
    return {
        "model": model or s.groq_chat_model,
        "messages": messages,
        "temperature": temperature,
    }


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().groq_api_key}"}


def chat(
    messages: list[dict], model: str | None = None, temperature: float = 0.2
) -> str:
    s = get_settings()
    try:
        r = httpx.post(
            f"{s.groq_base_url}/chat/completions",
            headers=_headers(),
            json=_body(messages, model, temperature),
            timeout=120,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"no hubo conexión con groq: {e}") from e
    if r.status_code != 200:
        raise HTTPException(502, f"groq respondió {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def stream_chat(
    messages: list[dict], model: str | None = None, temperature: float = 0.2
) -> Iterator[str]:
    """Genera los deltas de texto de Groq en modo streaming."""
    s = get_settings()
    payload = {**_body(messages, model, temperature), "stream": True}
    try:
        with httpx.stream(
            "POST",
            f"{s.groq_base_url}/chat/completions",
            headers=_headers(),
            json=payload,
            timeout=120,
        ) as r:
            if r.status_code != 200:
                r.read()
                raise HTTPException(
                    502, f"groq respondió {r.status_code}: {r.text[:300]}"
                )
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
    except httpx.HTTPError as e:
        raise HTTPException(502, f"no hubo conexión con groq: {e}") from e

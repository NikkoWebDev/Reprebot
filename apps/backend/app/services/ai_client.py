import json
from collections.abc import Iterator

import httpx
from fastapi import HTTPException

from app.core.config import get_settings


def _body(
    messages: list[dict],
    model: str | None,
    temperature: float,
    max_tokens: int | None = None,
) -> dict:
    s = get_settings()
    body: dict = {
        "model": model or s.groq_chat_model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    return body


def _headers() -> dict[str, str]:
    key = get_settings().groq_api_key
    if not key:
        raise HTTPException(500, "GROQ_API_KEY no está configurada en el servidor")
    return {"Authorization": f"Bearer {key}"}


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.2,
    with_usage: bool = False,
    max_tokens: int | None = None,
) -> str | tuple[str, dict, str]:
    """Chat simple. Con with_usage devuelve (contenido, usage, reasoning nativo)."""
    s = get_settings()
    try:
        r = httpx.post(
            f"{s.groq_base_url}/chat/completions",
            headers=_headers(),
            json=_body(messages, model, temperature, max_tokens),
            timeout=120,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"no hubo conexión con groq: {e}") from e
    if r.status_code != 200:
        raise HTTPException(502, f"groq respondió {r.status_code}: {r.text[:300]}")
    data = r.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    if with_usage:
        return content, data.get("usage", {}), msg.get("reasoning") or ""
    return content


def stream_chat(
    messages: list[dict], model: str | None = None, temperature: float = 0.2
) -> Iterator[tuple[str, str]]:
    """Genera tuplas (kind, texto): kind es "reasoning" o "content" (nativo Groq)."""
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
                    delta = json.loads(data)["choices"][0]["delta"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                raz = delta.get("reasoning")
                if raz:
                    yield ("reasoning", raz)
                cont = delta.get("content")
                if cont:
                    yield ("content", cont)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"no hubo conexión con groq: {e}") from e

"""Rate limit simple en memoria (ventana deslizante de 60s por IP).

Suficiente para una sola instancia protegiendo la key de Groq. Si algún día
se escala a varias instancias, mover a Redis.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import get_settings

_hits: dict[str, deque[float]] = defaultdict(deque)
_WINDOW = 60.0


def rate_limit(request: Request) -> None:
    limit = get_settings().rate_limit_per_min
    if limit <= 0:
        return
    key = request.client.host if request.client else "desconocido"
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > _WINDOW:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "demasiadas solicitudes, espera un momento")
    q.append(now)

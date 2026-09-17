# Reprebot API — FastAPI + RAG (Groq).
# Con EMBEDDINGS_API_URL los embeddings van por API remota y el proceso queda
# en ~150 MB; sin ella se usa fastembed local (~1 GB), que no cabe en Render free.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    DATA_DIR=/app/data

# onnxruntime necesita libgomp
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Hornea el modelo local (~600MB) solo si se va a usar fastembed.
# Con EMBEDDINGS_API_URL configurada no hace falta: ahorra build y RAM.
ARG BAKE_EMBEDDINGS=0
RUN if [ "$BAKE_EMBEDDINGS" = "1" ]; then \
      python -c "from fastembed import TextEmbedding; TextEmbedding('jinaai/jina-embeddings-v2-base-es')"; \
    fi

COPY app/ ./app/
COPY data/ ./data/

# Usuario sin privilegios (el store se escribe solo al subir documentos)
RUN mkdir -p /opt/fastembed \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /opt/fastembed
USER appuser

EXPOSE 8000
# Render inyecta PORT: shell form para expandirlo
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

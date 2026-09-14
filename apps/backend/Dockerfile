# Reprebot API — FastAPI + RAG (Groq + fastembed).
# El modelo de embeddings y el store se hornean en la imagen para que el
# arranque en Render no dependa de descargas en el primer request.
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

# Hornea el modelo (~600MB): cold start sin descargas
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('jinaai/jina-embeddings-v2-base-es')"

COPY app/ ./app/
COPY data/ ./data/

# Usuario sin privilegios (el store se escribe solo al subir documentos)
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app /opt/fastembed
USER appuser

EXPOSE 8000
# Render inyecta PORT: shell form para expandirlo
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

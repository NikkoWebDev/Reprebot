# Backend de Reprebot (fork API)

Microservicio FastAPI para consultar documentos de la Universidad Nacional de Colombia con RAG.

> **Atribución.** Este repositorio es un fork de [Reprebot](https://github.com/Ansukic/Reprebot)
> convertido en microservicio de API e implementado por **Nikko** (<https://nikko.dev>) y
> **Julián Sánchez** (<https://julsanchezc.dev>). El bot lo declara en sus respuestas cuando
> le preguntan quién lo hizo.

## Requisitos

- Python 3.11 o superior
- Una API key de Groq

## Configuración

```bash
cd apps/backend
cp .env.example .env
```

Edite `.env`:

```env
GROQ_API_KEY=su-key
GROQ_CHAT_MODEL=openai/gpt-oss-120b
EMBEDDINGS_MODEL=jinaai/jina-embeddings-v2-base-es
CORS_ORIGINS=https://ceis-unal.vercel.app,http://localhost:5173
ADMIN_TOKEN=

# Foro CEIS (Supabase). Si están vacíos, /api/forum/answer solo devuelve la
# respuesta sin publicarla.
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
FORUM_BOT_USER_ID=
FORUM_API_KEY=
FORUM_TAG_ALLOWLIST=Duda académica,Inscripciones y trámites,Bienestar
RATE_LIMIT_PER_MIN=20
```

La key real vive solo en `.env`. Ese archivo está ignorado por Git. `fastembed` descarga el modelo de embeddings localmente en la primera ingesta.

`SUPABASE_SERVICE_KEY` salta RLS: nunca debe salir del servidor.

## Ejecutar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Ejecute los comandos desde `apps/backend/`. La interfaz de prueba queda en http://127.0.0.1:8000/ y la documentación en http://127.0.0.1:8000/docs.

## API

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/api/health` | Estado, modelo y conteo de documentos/chunks |
| `POST` | `/api/chat` | Pregunta RAG; devuelve respuesta y fuentes |
| `POST` | `/api/chat/stream` | La misma respuesta en SSE (texto a texto) |
| `POST` | `/api/search` | Recupera fuentes sin llamar al LLM |
| `POST` | `/api/forum/answer` | Responde una pregunta del foro y la publica como el bot |
| `POST` | `/api/documents` | Ingresa un PDF, TXT o MD mediante `multipart/form-data` |
| `GET` | `/api/documents` | Lista documentos indexados |
| `DELETE` | `/api/documents/{id}` | Borra un documento y sus chunks |

Chat y búsqueda limitan a `RATE_LIMIT_PER_MIN` por IP (ventana de 60s). Ingesta y borrado requieren `X-Admin-Token` si `ADMIN_TOKEN` tiene valor.

### Chat

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"¿Qué dice el Acuerdo 044 de 2009 sobre bienestar?","k":6}'
```

```json
{
  "answer": "…",
  "sources": [
    { "doc_id": "…", "doc_name": "Acuerdo 044 de 2009 CSU - estatuto bienestar y convivencia",
      "text": "…", "score": 0.71, "source_url": "https://…", "doc_type": "normativa" }
  ]
}
```

### Chat en streaming (SSE)

`POST /api/chat/stream` con el mismo body devuelve `text/event-stream`, un evento por línea:

```
data: {"type":"sources","sources":[…]}

data: {"type":"delta","text":"El "}

data: {"type":"delta","text":"Acuerdo "}

data: {"type":"done"}
```

Las fuentes llegan primero, así el cliente puede pintarlas mientras se escribe la respuesta.

### Respuesta de foro

```bash
curl -X POST http://127.0.0.1:8000/api/forum/answer \
  -H 'Content-Type: application/json' \
  -H 'X-Api-Key: <FORUM_API_KEY>' \
  -d '{"question_id":"<uuid>","title":"…","body":"…","tag":"Duda académica"}'
```

- Responde únicamente si `tag` está en `FORUM_TAG_ALLOWLIST`; si no, devuelve `skipped: "tag"`.
- Es idempotente: si ya hay una respuesta con `ai_generated = true` para esa pregunta, devuelve `skipped: "already"`.
- Con Supabase configurado, inserta la fila en `answers` como `FORUM_BOT_USER_ID` con `ai_generated = true`. Devuelve `posted: true`.
- Sin Supabase configurado, devuelve `posted: false` (útil para probar).

Los logs del bot también aceptan el payload crudo de un Database Webhook de Supabase (con `record`).

## Integración con el foro CEIS

1. En Supabase, Authentication → Users: cree el usuario del bot (`reprebot@unal.edu.co`, auto-confirmado). Copie su uuid a `FORUM_BOT_USER_ID`.
2. Ejecute `migration_07.sql` en el proyecto del foro (columna `ai_generated` + apodo del bot).
3. En la API, configure `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FORUM_BOT_USER_ID` y `FORUM_API_KEY`.
4. Para que responda solo: Database Webhooks → tabla `questions`, evento `INSERT`, URL `https://<api>/api/forum/answer`, header `X-Api-Key`. Sin webhook, el front puede llamar al endpoint tras publicar.

El bot responde como un usuario más del foro, marcado con `ai_generated`, con sus fuentes enlazadas.

## Despliegue en Render

`render.yaml` en la raíz del repo describe el servicio (`runtime: docker`, health check en `/api/health`).

Antes de desplegar, revise el plan: **fastembed + onnxruntime con un modelo BERT-base piden ~1 GB de RAM**. El plan `starter` (512 MB) probablemente hace OOM; por eso el blueprint usa `standard`. Si necesita bajar el costo: use un modelo de embeddings más pequeño y reindexe, o un VPS / Railway con 1 GB.

El `Dockerfile` hornea el modelo de embeddings y el `data/` actual, así el contenedor arranca sin descargas. Ojo: al ser disco efímero, los documentos que se suban por `/api/documents` se pierden en cada despliegue.

Variables de entorno: las mismas de `.env` (marque las sensibles como secretas en Render).

## Estructura

```text
app/
├── api/
│   ├── chat.py          # /chat y /chat/stream
│   ├── documents.py
│   ├── forum.py         # /forum/answer
│   ├── health.py
│   └── search.py
├── core/
│   ├── config.py
│   └── ratelimit.py
├── models/chat_message.py
├── services/
│   ├── ai_client.py     # Groq: chat y stream_chat
│   ├── chunker.py
│   ├── embeddings.py
│   ├── ingest.py
│   ├── rag.py           # prompts, chat, foro y streaming
│   ├── store.py
│   └── supabase_admin.py
└── main.py
```

El índice numpy y sus metadatos se guardan en `data/`, que no se versiona.

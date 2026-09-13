# Scraper de documentos UNAL

Descubre, descarga e ingiere al store RAG los documentos informativos y normativos de la Facultad de Ingeniería de la UNAL, sede Bogotá, con foco en Ingeniería de Sistemas y Computación.

## Qué hace

1. **Descubre** candidatos con BFS desde seeds oficiales (`ingenieria.bogota.unal.edu.co`, `pregrado.unal.edu.co`, `posgrados.unal.edu.co`, `diracad.bogota.unal.edu.co`).
2. **Filtra** por dominio (`*.unal.edu.co`), relevancia temática (ingeniería, sistemas, normatividad, reglamento, plan de estudios, acreditación, etc.) y formato (PDF, HTML, TXT/MD).
3. **Respeta normas de scraping**: robots.txt por host, User-Agent identificable, rate limit configurable, límite de páginas/documentos, tamaño máximo 20MB.
4. **Extrae** texto de PDF (pypdf) y HTML (BeautifulSoup), descartando navegación y contenido vacío.
5. **Clasifica** cada documento: tipo (reglamento, acuerdo, resolución, plan de estudios, PEP, acreditación...), programa (sistemas/industrial) y año.
6. **Ingiere** al mismo store del backend (`apps/backend/data`) con metadatos de fuente (`source_url`, `doc_type`), sin duplicar URLs ya cargadas.

## Uso

Corre desde el venv del backend (comparte dependencias):

```bash
cd apps/backend && source .venv/bin/activate
pip install -r ../scraper/requirements.txt

# solo descubrir qué hay
python ../scraper/scraper.py --dry-run

# descubrir + descargar + ingerir
python ../scraper/scraper.py

# con límites ajustados
python ../scraper/scraper.py --max-pages 100 --max-docs 50 --delay 0.5
```

## Opciones

| Flag | Default | Descripción |
|---|---|---|
| `--dry-run` | off | Solo lista candidatos, no descarga ni ingiere |
| `--max-pages` | 300 | Máximo de páginas visitadas |
| `--max-docs` | 200 | Máximo de documentos candidatos |
| `--delay` | 1.0 | Segundos entre requests por host |
| `--limit` | 0 | Máximo de documentos a ingerir (0 = todos) |

## Notas

- La primera corrida descarga el modelo de embeddings (~600MB, cacheado en `~/.cache/fastembed`).
- Los documentos ya presentes en el store (mismo `source_url`) se saltan.
- El store resultante alimenta `/api/chat` y `/api/search` del backend; las fuentes incluyen link al documento original.
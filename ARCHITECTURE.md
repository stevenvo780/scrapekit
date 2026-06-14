# ScrapeKit Colombia - Architecture & Data Migration Plan

## What this is

ScrapeKit Colombia is a generalization of [scrapingLegal](https://github.com/stevenvo780/scrapingLegal),
which was purpose-built for the Camara de Diputados of the Dominican Republic.

This version introduces:
- **Source Adapter pattern**: swap scraping targets without touching the pipeline.
- **Postgres (Neon)** instead of SQLite.
- **API key auth** on write endpoints.
- **Vercel serverless** deployment (FastAPI via Mangum).
- **Colombia adapters** for Camara de Representantes and Senado.

---

## Directory layout

```
scrapekit/
  api/
    index.py          # FastAPI app + Mangum handler (Vercel entrypoint)
  lib/
    adapters.py       # Source adapter registry (colombia_camara, colombia_senado, dominicana_camara)
    database.py       # SQLModel + asyncpg / Neon
    downloader.py     # Async PDF downloader (adapter-aware)
    exceptions.py     # Domain errors
    extractor.py      # pdfplumber -> plain text + headings
    models.py         # Dataclasses (in-memory pipeline models)
    pipeline.py       # download -> extract -> persist
    schemas.py        # Pydantic response schemas
    settings.py       # pydantic-settings from env vars
    utils.py          # sha256, slugify, snippet builder
  scripts/
    index_batch.py    # CLI: index a range/list of IDs (direct or via API)
  templates/          # Jinja2 HTML templates
  public/static/      # CSS + JS (served by Vercel as static files)
  vercel.json
  requirements.txt
  .env.example
  .gitignore
```

---

## Data model (Postgres)

Single table: `scrapekit_documents`

| Column           | Type      | Notes                                      |
|------------------|-----------|--------------------------------------------|
| id               | SERIAL PK |                                            |
| document_id      | TEXT UNIQUE | ID tal como lo reporta la fuente         |
| source_key       | TEXT      | Clave del adaptador (e.g. colombia_camara) |
| filename         | TEXT      |                                            |
| source_url       | TEXT      | URL original del PDF                       |
| checksum_sha256  | TEXT      |                                            |
| content_length   | INT       |                                            |
| downloaded_at    | TIMESTAMP |                                            |
| processed_at     | TIMESTAMP |                                            |
| plain_text       | TEXT      | Texto plano completo (full-text search)    |
| heading_count    | INT       |                                            |
| total_pages      | INT       |                                            |
| country          | TEXT      |                                            |
| institution      | TEXT      |                                            |

Indexes: `document_id` (UNIQUE), `source_key`.
Full-text search: ILIKE en `plain_text` (suficiente para escala inicial).
Upgrade path: agregar columna `ts tsvector GENERATED ALWAYS AS (to_tsvector('spanish', plain_text)) STORED` + GIN index cuando el corpus supere ~50k docs.

Tables are created on startup via `SQLModel.metadata.create_all` (async).
For production schema migrations use Alembic with `SCRAPEKIT_DIRECT_URL` (unpooled).

---

## Migration from SQLite (scrapingLegal original)

If you have a local `data/scraping.db` to migrate:

```bash
# 1. Export from SQLite
sqlite3 data/scraping.db ".mode csv" ".headers on" ".output export.csv" \
  "SELECT document_id, filename, source_url, checksum_sha256, content_length, \
          downloaded_at, processed_at, plain_text, heading_count, total_pages FROM document;"

# 2. Import to Neon via psql (set SCRAPEKIT_DIRECT_URL first)
psql "$SCRAPEKIT_DIRECT_URL" -c "\copy scrapekit_documents \
  (document_id, filename, source_url, checksum_sha256, content_length, \
   downloaded_at, processed_at, plain_text, heading_count, total_pages) \
  FROM 'export.csv' CSV HEADER"

# 3. Backfill new columns (source from Dominican Republic origin)
psql "$SCRAPEKIT_DIRECT_URL" -c "
  UPDATE scrapekit_documents
  SET source_key = 'dominicana_camara',
      country    = 'Republica Dominicana',
      institution = 'Camara de Diputados'
  WHERE source_key IS NULL OR source_key = '';
"
```

---

## Vercel deployment constraints

| Component         | Status on Vercel                                |
|-------------------|-------------------------------------------------|
| FastAPI (API)     | Deployed as Python serverless function          |
| HTML frontend     | Served by the same function via Jinja2          |
| Static files      | Served from /public/static by Vercel CDN        |
| Postgres (Neon)   | External managed DB — fully compatible          |
| Auto-indexer loop | NOT deployable on Vercel (no persistent process)|

**Auto-indexing workaround options:**
1. GitHub Actions cron: call `POST /api/documents` with X-API-Key for each new ID.
2. `scripts/index_batch.py --mode direct` from any machine/VPS with Neon access.
3. Railway/Render free tier running `scripts/index_batch.py` on a schedule.

---

## Source adapters

| Key                | Country              | Institution                     | URL pattern                                  |
|--------------------|----------------------|---------------------------------|----------------------------------------------|
| colombia_camara    | Colombia             | Camara de Representantes        | camara.gov.co/documentos/descarga?id=X       |
| colombia_senado    | Colombia             | Senado de la Republica          | senado.gov.co/.../search?docId=X             |
| dominicana_camara  | Republica Dominicana | Camara de Diputados             | s-sil.camaradediputados.gob.do/...?documentoId=X |

New adapters: add an entry to `lib/adapters.py:ADAPTERS`. No other files change.

---

## API reference (brief)

```
GET  /api/sources                         -> list adapters
GET  /api/documents?source=&limit=&offset= -> list documents
GET  /api/documents/{id}                  -> get document
POST /api/documents  {document_id, source_key}  [X-API-Key] -> process & index
GET  /api/search?q=&source=&limit=        -> full-text search
GET  /health                              -> {"status":"ok"}
```

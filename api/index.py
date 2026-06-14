"""
ScrapeKit Colombia - Vercel serverless entrypoint.

Rutas:
  GET  /                          -> UI buscador (HTML)
  GET  /document/{id}             -> Detalle documento (HTML)
  GET  /api/sources               -> Lista de adaptadores disponibles
  GET  /api/documents             -> Lista documentos (JSON)
  GET  /api/documents/{id}        -> Detalle documento (JSON)
  POST /api/documents             -> Procesar documento [requiere X-API-Key]
  GET  /api/search                -> Busqueda full-text (JSON)
  GET  /health                    -> Healthcheck

NOTA sobre indexacion autonoma:
  El background task de auto-discovery/indexing NO puede correr en Vercel (funciones
  serverless efimeras). Para indexacion batch usa el script scripts/index_batch.py
  ejecutado desde cualquier maquina con acceso a Neon, o configura un cron en Railway/
  Render/GitHub Actions que llame POST /api/documents con la API key.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Agrega el directorio raiz al path para importar lib/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from mangum import Mangum

from lib.adapters import list_adapters, get_adapter, ADAPTERS
from lib.database import Database, Document, init_db
from lib.exceptions import DocumentNotFoundError, DownloadError, EmptyDocumentError, ParsingError
from lib.pipeline import ProcessingPipeline
from lib.schemas import DocumentRead, ProcessRequest, SearchHit, SourceInfo
from lib.settings import get_settings

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
settings = get_settings()
_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _ROOT / "templates"
_STATIC_DIR = _ROOT / "public" / "static"

env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


# ---------------------------------------------------------------------------
# Helpers auth
# ---------------------------------------------------------------------------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="X-API-Key invalida o ausente")
    return api_key


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ScrapeKit Colombia",
    description="API para descargar e indexar documentos PDF legislativos de Colombia y otros paises.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estaticos (CSS/JS/favicon) en dev local; en Vercel se sirven desde /public
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Startup: crear tablas si no existen.
# En Vercel (serverless) el startup corre en cada cold-start pero la conexion
# falla si hay error de URL, asi que usamos un flag para evitar repeticion.
# ---------------------------------------------------------------------------
_db_initialized = False


@app.on_event("startup")
async def startup_event() -> None:
    global _db_initialized
    if not _db_initialized:
        try:
            await init_db(settings)
            _db_initialized = True
        except Exception as exc:
            # Log but don't crash startup — read-only endpoints may still work
            import logging
            logging.getLogger("scrapekit").warning("DB init skipped: %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _doc_to_schema(doc: Document) -> DocumentRead:
    return DocumentRead.model_validate(doc)


def _render(template_name: str, **ctx) -> str:
    tmpl = env.get_template(template_name)
    return tmpl.render(year=datetime.utcnow().year, **ctx)


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------
@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    from fastapi.responses import FileResponse
    favicon_path = _ROOT / "public" / "favicon.svg"
    return FileResponse(str(favicon_path), media_type="image/svg+xml")


@app.get("/health", tags=["meta"])
async def healthcheck() -> dict:
    return {"status": "ok", "service": "scrapekit-colombia"}




# ---------------------------------------------------------------------------
# API: sources
# ---------------------------------------------------------------------------
@app.get("/api/sources", response_model=List[SourceInfo], tags=["sources"])
async def get_sources() -> List[SourceInfo]:
    return [SourceInfo(**s) for s in list_adapters()]


# ---------------------------------------------------------------------------
# API: documents
# ---------------------------------------------------------------------------
@app.get("/api/documents", response_model=List[DocumentRead], tags=["documents"])
async def list_documents(
    source: Optional[str] = Query(None, description="Filtrar por clave de fuente"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[DocumentRead]:
    db = Database(settings)
    docs = await db.list_documents(source_key=source, limit=limit, offset=offset)
    return [_doc_to_schema(d) for d in docs]


@app.get("/api/documents/{document_id}", response_model=DocumentRead, tags=["documents"])
async def get_document(document_id: str) -> DocumentRead:
    db = Database(settings)
    doc = await db.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return _doc_to_schema(doc)


@app.post("/api/documents", response_model=DocumentRead, tags=["documents"])
async def process_document(
    body: ProcessRequest,
    _key: str = Depends(require_api_key),
) -> DocumentRead:
    """
    Descarga y procesa un documento PDF.
    Requiere cabecera X-API-Key con el valor configurado en SCRAPEKIT_API_KEY.
    """
    source_key = body.source_key or settings.default_source
    try:
        get_adapter(source_key)  # valida antes de descargar
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pipeline = ProcessingPipeline()
    try:
        report = await pipeline.process(body.document_id, source_key)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (EmptyDocumentError, DownloadError, ParsingError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db = Database(settings)
    doc = await db.get_document(body.document_id)
    if doc is None:
        raise HTTPException(status_code=500, detail="Error al recuperar documento tras procesar")
    return _doc_to_schema(doc)


# ---------------------------------------------------------------------------
# API: search
# ---------------------------------------------------------------------------
@app.get("/api/search", response_model=List[SearchHit], tags=["search"])
async def search_documents(
    q: str = Query(..., min_length=1, description="Texto a buscar"),
    source: Optional[str] = Query(None, description="Filtrar por clave de fuente"),
    limit: int = Query(20, ge=1, le=50),
) -> List[SearchHit]:
    db = Database(settings)
    results = await db.search_documents(q, source_key=source, limit=limit)
    return [
        SearchHit(
            document_id=r.document.document_id,
            source_key=r.document.source_key,
            filename=r.document.filename,
            source_url=r.document.source_url,
            processed_at=r.document.processed_at,
            total_pages=r.document.total_pages,
            heading_count=r.document.heading_count,
            matches=r.matches,
            snippet=r.snippet,
            country=r.document.country,
            institution=r.document.institution,
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# UI: HTML frontend
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def homepage(request: Request) -> HTMLResponse:
    db = Database(settings)
    documents = await db.list_documents(limit=50)
    sources = list_adapters()
    html = _render("index.html", documents=documents, sources=sources)
    return HTMLResponse(html)


@app.get("/document/{document_id}", response_class=HTMLResponse, tags=["ui"])
async def document_detail(document_id: str, request: Request) -> HTMLResponse:
    db = Database(settings)
    doc = await db.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    html = _render("detail.html", document=doc)
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Vercel handler
# ---------------------------------------------------------------------------
handler = Mangum(app, lifespan="off")

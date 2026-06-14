from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, List, Optional

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import Field, SQLModel, select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import ExtractionReport
from .settings import Settings, get_settings
from .utils import build_snippet


class Document(SQLModel, table=True):
    """Tabla principal: un registro por documento procesado."""

    __tablename__ = "scrapekit_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: str = Field(index=True, unique=True)
    source_key: str = Field(index=True, description="Clave del adaptador fuente")
    filename: str
    source_url: str
    checksum_sha256: str
    content_length: int
    downloaded_at: datetime
    processed_at: datetime
    plain_text: str
    heading_count: int
    total_pages: int
    country: str = Field(default="")
    institution: str = Field(default="")


class DocumentSearchResult:
    def __init__(self, document: Document, snippet: str, matches: int) -> None:
        self.document = document
        self.snippet = snippet
        self.matches = matches


_engine_cache: dict = {}


def _normalize_db_url(db_url: str) -> str:
    """
    Convierte cadenas de conexion Neon/Postgres a formato asyncpg.

    asyncpg (via SQLAlchemy) no acepta query params estandar de libpq como
    sslmode= o channel_binding=. Las conexiones SSL se pasan via connect_args.
    Esta funcion limpia el URL y devuelve (url_limpio, connect_args).
    """
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

    url = db_url
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    # Quitar parametros que asyncpg no acepta como query string
    parsed = urlparse(url)
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        params.pop("channel_binding", None)
        params.pop("sslmode", None)      # asyncpg usa ssl= en connect_args
        params.pop("sslcert", None)
        params.pop("sslkey", None)
        params.pop("sslrootcert", None)
        new_query = urlencode({k: v[0] for k, v in params.items()})
        url = urlunparse(parsed._replace(query=new_query))

    return url


def _get_connect_args(db_url: str) -> dict:
    """Extrae SSL mode del URL original y lo convierte a connect_args de asyncpg.

    sslmode=require -> ssl context con verificacion completa (Neon tiene cert valido).
    sslmode=disable -> sin SSL.
    Todo lo demas -> verificacion completa por defecto (ssl.create_default_context()).
    """
    from urllib.parse import urlparse, parse_qs
    import ssl

    parsed = urlparse(db_url)
    params = parse_qs(parsed.query)
    sslmode = params.get("sslmode", [None])[0]

    if sslmode == "disable":
        return {}

    # require / verify-ca / verify-full / None -> SSL con verificacion del CA
    ctx = ssl.create_default_context()
    return {"ssl": ctx}


def _get_engine(db_url: str):
    if db_url not in _engine_cache:
        url = _normalize_db_url(db_url)
        connect_args = _get_connect_args(db_url)

        # --- Serverless (Vercel + Mangum) friendly engine -------------------
        # 1. NullPool: abrir/cerrar la conexion por uso. Las funciones serverless
        #    son efimeras y un pool de larga vida termina con conexiones atadas a
        #    un event loop ya cerrado entre invocaciones del mismo Lambda caliente,
        #    lo que produce errores de greenlet/await_only de SQLAlchemy async.
        # 2. statement_cache_size=0 / prepared_statement_cache_size=0: asyncpg usa
        #    prepared statements con nombre; con la URL pooled de Neon (pgbouncer en
        #    modo transaction) esto puede colisionar. Desactivar el cache es la
        #    configuracion segura y recomendada para pgbouncer.
        connect_args = {**connect_args, "statement_cache_size": 0}
        _engine_cache[db_url] = create_async_engine(
            url,
            echo=False,
            future=True,
            poolclass=NullPool,
            connect_args=connect_args,
        )
    return _engine_cache[db_url]


async def init_db(settings: Optional[Settings] = None) -> None:
    """Crea las tablas si no existen. Llamar en startup."""
    s = settings or get_settings()
    engine = _get_engine(s.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


_schema_ready: set = set()


async def ensure_schema(settings: Optional[Settings] = None) -> None:
    """Crea las tablas de forma perezosa e idempotente.

    En Vercel con Mangum(lifespan="off") el evento startup NO se ejecuta, asi que
    la creacion de tablas debe dispararse desde el primer request de escritura.
    Solo corre una vez por proceso caliente.
    """
    s = settings or get_settings()
    if s.database_url in _schema_ready:
        return
    await init_db(s)
    _schema_ready.add(s.database_url)


class Database:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._engine = _get_engine(self.settings.database_url)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        # expire_on_commit=False: tras commit/cierre los objetos ORM conservan sus
        # atributos cargados. Sin esto, leer un atributo despues de cerrar la sesion
        # dispara IO perezosa que bajo SQLAlchemy-async + Mangum falla con
        # "greenlet_spawn has not been called; can't call await_only()".
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            yield session

    async def upsert_report(self, report: ExtractionReport, source_key: str) -> Document:
        from .adapters import get_adapter
        adapter = get_adapter(source_key)
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            stmt = select(Document).where(Document.document_id == report.downloaded.document_id)
            result = await session.exec(stmt)
            doc = result.one_or_none()
            if doc is None:
                doc = Document(document_id=report.downloaded.document_id, source_key=source_key)
            doc.filename = report.downloaded.filename
            doc.source_url = report.downloaded.source_url
            doc.checksum_sha256 = report.downloaded.checksum_sha256
            doc.content_length = report.downloaded.content_length
            doc.downloaded_at = report.downloaded.downloaded_at
            doc.processed_at = report.extraction.processed_at
            doc.plain_text = report.extraction.plain_text
            doc.heading_count = len(report.extraction.headings)
            doc.total_pages = int(report.extraction.metadata.get("total_pages", "0"))
            doc.country = adapter.country
            doc.institution = adapter.institution
            session.add(doc)
            await session.commit()
            # Con expire_on_commit=False los atributos siguen disponibles tras commit;
            # un refresh explicito recarga la fila (incluye id autogenerado) de forma
            # segura mientras la sesion aun esta abierta.
            await session.refresh(doc)
            return doc

    async def get_document(self, document_id: str) -> Optional[Document]:
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            stmt = select(Document).where(Document.document_id == document_id)
            result = await session.exec(stmt)
            return result.one_or_none()

    async def list_documents(
        self,
        source_key: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Document]:
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            stmt = select(Document)
            if source_key:
                stmt = stmt.where(Document.source_key == source_key)
            stmt = stmt.order_by(Document.processed_at.desc()).limit(limit).offset(offset)
            result = await session.exec(stmt)
            return list(result.all())

    async def search_documents(
        self,
        query: str,
        source_key: Optional[str] = None,
        limit: int = 20,
    ) -> List[DocumentSearchResult]:
        cleaned = query.strip()
        if not cleaned:
            return []
        pattern = f"%{cleaned.lower()}%"
        out: List[DocumentSearchResult] = []
        async with AsyncSession(self._engine, expire_on_commit=False) as session:
            stmt = (
                select(Document)
                .where(func.lower(Document.plain_text).like(pattern))
            )
            if source_key:
                stmt = stmt.where(Document.source_key == source_key)
            stmt = stmt.order_by(Document.processed_at.desc()).limit(limit)
            result = await session.exec(stmt)
            documents = list(result.all())

            # Leer atributos DENTRO del contexto de sesion: evita IO perezosa sobre
            # objetos detached/expired (causa del error greenlet_spawn/await_only).
            for doc in documents:
                plain = doc.plain_text or ""
                snippet = build_snippet(plain, cleaned)
                matches = plain.lower().count(cleaned.lower())
                out.append(DocumentSearchResult(document=doc, snippet=snippet, matches=matches))
        return out

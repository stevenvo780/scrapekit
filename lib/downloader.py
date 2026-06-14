from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import httpx

from .adapters import SourceAdapter, get_adapter
from .exceptions import DocumentNotFoundError, DownloadError, InvalidContentTypeError
from .models import DownloadedDocument
from .utils import compute_sha256, ensure_pdf_extension, slugify

PDF_MIME = "application/pdf"
USER_AGENT = "ScrapeKit-Colombia/1.0 (+https://github.com/stevenvo780)"


class DocumentDownloader:
    """Descarga un PDF de la fuente indicada por el adaptador."""

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def download(self, document_id: str, adapter: SourceAdapter) -> DownloadedDocument:
        url = adapter.build_url(document_id)
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            try:
                response = await client.get(url)
            except httpx.RequestError as exc:
                raise DownloadError(f"Error de red al descargar {document_id}: {exc}") from exc

        if response.status_code == 404:
            raise DocumentNotFoundError(f"Documento {document_id} no encontrado en {adapter.label}")
        if response.status_code >= 400:
            raise DownloadError(
                f"Respuesta {response.status_code} al descargar {document_id} desde {adapter.label}"
            )

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != PDF_MIME:
            raise InvalidContentTypeError(
                f"Se esperaba PDF para {document_id}, se recibio '{content_type or 'desconocido'}'"
            )

        raw = response.content
        checksum = compute_sha256(raw)

        disposition = response.headers.get("Content-Disposition", "")
        suggested: Optional[str] = None
        if "filename=" in disposition:
            suggested = disposition.split("filename=")[-1].strip().strip('"')
        filename = slugify(suggested, allow_dot=True) if suggested else f"{adapter.key}-{slugify(document_id)}.pdf"
        filename = ensure_pdf_extension(filename)

        content_length = int(response.headers.get("Content-Length", len(raw)))
        downloaded_at = datetime.utcnow()
        header_date = response.headers.get("Date")
        if header_date:
            try:
                parsed = parsedate_to_datetime(header_date)
                if parsed:
                    # El header HTTP Date es timezone-aware; la columna es
                    # TIMESTAMP WITHOUT TIME ZONE, y asyncpg rechaza mezclar
                    # datetimes naive/aware ("can't subtract offset-naive and
                    # offset-aware datetimes"). Convertir a UTC naive.
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    downloaded_at = parsed
            except (TypeError, ValueError):
                pass

        return DownloadedDocument(
            document_id=document_id,
            source_url=url,
            filename=filename,
            content_length=content_length,
            content_type=content_type,
            checksum_sha256=checksum,
            raw_bytes=raw,
            downloaded_at=downloaded_at,
        )

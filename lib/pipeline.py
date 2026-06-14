from __future__ import annotations

from .adapters import SourceAdapter, get_adapter
from .database import Database
from .downloader import DocumentDownloader
from .exceptions import DocumentNotFoundError, DownloadError, EmptyDocumentError, ParsingError
from .extractor import PdfExtractor
from .models import ExtractionReport


class ProcessingPipeline:
    """Orquesta descarga -> extraccion -> persistencia para un documento."""

    def __init__(
        self,
        downloader: DocumentDownloader | None = None,
        extractor: PdfExtractor | None = None,
        database: Database | None = None,
    ) -> None:
        self.downloader = downloader or DocumentDownloader()
        self.extractor = extractor or PdfExtractor()
        self.database = database or Database()

    async def process(self, document_id: str, source_key: str) -> ExtractionReport:
        adapter = get_adapter(source_key)
        downloaded = await self.downloader.download(document_id, adapter)
        extraction = self.extractor.extract(downloaded.raw_bytes, document_id)
        report = ExtractionReport(downloaded=downloaded, extraction=extraction)
        await self.database.upsert_report(report, source_key)
        return report


__all__ = [
    "ProcessingPipeline",
    "DocumentNotFoundError",
    "DownloadError",
    "EmptyDocumentError",
    "ParsingError",
]

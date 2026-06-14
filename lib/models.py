from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(slots=True)
class DownloadedDocument:
    document_id: str
    source_url: str
    filename: str
    content_length: int
    content_type: str
    checksum_sha256: str
    raw_bytes: bytes
    downloaded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Heading:
    level: int
    text: str
    page_number: int


@dataclass(slots=True)
class ExtractionResult:
    document_id: str
    markdown: str
    plain_text: str
    headings: List[Heading]
    metadata: Dict[str, str]
    processed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class ExtractionReport:
    downloaded: DownloadedDocument
    extraction: ExtractionResult

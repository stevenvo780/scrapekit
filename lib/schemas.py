from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    document_id: str
    source_key: str
    filename: str
    source_url: str
    checksum_sha256: str
    content_length: int
    downloaded_at: datetime
    processed_at: datetime
    plain_text: Optional[str] = None
    heading_count: int
    total_pages: int
    country: str
    institution: str

    model_config = ConfigDict(from_attributes=True)


class SearchHit(BaseModel):
    document_id: str
    source_key: str
    filename: str
    source_url: str
    processed_at: datetime
    total_pages: int
    heading_count: int
    matches: int
    snippet: str
    country: str
    institution: str


class SourceInfo(BaseModel):
    key: str
    label: str
    country: str
    institution: str


class ProcessRequest(BaseModel):
    document_id: str
    source_key: Optional[str] = None

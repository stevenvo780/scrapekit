from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import pdfplumber

from .exceptions import EmptyDocumentError, ParsingError
from .models import ExtractionResult, Heading


@dataclass(slots=True)
class PageText:
    page_number: int
    text: str


class PdfExtractor:
    """Convierte PDF a texto estructurado; preserva encabezados por tamano de fuente."""

    def __init__(self, min_heading_multiplier: float = 1.3) -> None:
        self.min_heading_multiplier = min_heading_multiplier

    def extract(self, pdf_bytes: bytes, document_id: str) -> ExtractionResult:
        try:
            pages = self._read_pages(pdf_bytes)
            if not pages:
                raise EmptyDocumentError("El PDF no contiene texto interpretable")
            headings = self._detect_headings(pdf_bytes)
            markdown, plain_text = self._build_formats(pages, headings)
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise ParsingError(f"Fallo al procesar PDF {document_id}: {exc}") from exc

        metadata: Dict[str, str] = {
            "total_pages": str(len(pages)),
            "heading_count": str(len(headings)),
        }
        return ExtractionResult(
            document_id=document_id,
            markdown=markdown,
            plain_text=plain_text,
            headings=headings,
            metadata=metadata,
        )

    def _read_pages(self, pdf_bytes: bytes) -> List[PageText]:
        pages: List[PageText] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(PageText(page_number=idx, text=text))
        return pages

    def _detect_headings(self, pdf_bytes: bytes) -> List[Heading]:
        headings: List[Heading] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                chars = page.chars
                if not chars:
                    continue
                font_sizes = [float(ch.get("size", 0)) for ch in chars if ch.get("text", "").strip()]
                if not font_sizes:
                    continue
                avg_size = sum(font_sizes) / len(font_sizes)
                threshold = avg_size * self.min_heading_multiplier
                grouped: Dict[Tuple[str, float], List[str]] = defaultdict(list)
                for char in chars:
                    text = char.get("text", "")
                    size = float(char.get("size", 0))
                    fontname = char.get("fontname", "")
                    if not text.strip():
                        grouped[(fontname, size)].append(" ")
                    else:
                        grouped[(fontname, size)].append(text)
                for (fontname, size), tokens in grouped.items():
                    if size >= threshold:
                        content = "".join(tokens).strip()
                        cleaned = " ".join(content.split())
                        if cleaned:
                            level = 1 if size >= threshold * 1.4 else 2
                            headings.append(Heading(level=level, text=cleaned, page_number=idx))
        return headings

    def _build_formats(self, pages: Iterable[PageText], headings: List[Heading]) -> Tuple[str, str]:
        page_headings: Dict[int, List[Heading]] = defaultdict(list)
        for heading in headings:
            page_headings[heading.page_number].append(heading)
        markdown_lines: List[str] = []
        plain_lines: List[str] = []
        for page in pages:
            plain_lines.append(page.text)
            markdown_lines.append(f"<!-- Pagina {page.page_number} -->")
            for line in page.text.splitlines():
                stripped = line.strip()
                if not stripped:
                    markdown_lines.append("")
                    continue
                candidates = page_headings.get(page.page_number, [])
                heading = next(
                    (h for h in candidates if h.text.lower() in stripped.lower()),
                    None,
                )
                if heading:
                    prefix = "#" * min(6, heading.level + 1)
                    markdown_lines.append(f"{prefix} {stripped}")
                else:
                    markdown_lines.append(stripped)
        return "\n".join(markdown_lines), "\n".join(plain_lines)

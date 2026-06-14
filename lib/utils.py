from __future__ import annotations

import hashlib
import re
import unicodedata


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def slugify(value: str, allow_dot: bool = False) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    if allow_dot:
        value = re.sub(r"[^\w.\-]", "-", value)
    else:
        value = re.sub(r"[^\w\-]", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def ensure_pdf_extension(filename: str) -> str:
    if not filename.lower().endswith(".pdf"):
        return f"{filename}.pdf"
    return filename


def build_snippet(text: str, query: str, window: int = 120) -> str:
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx == -1:
        return text[:window].strip()
    start = max(0, idx - window // 2)
    end = min(len(text), idx + len(query) + window // 2)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet

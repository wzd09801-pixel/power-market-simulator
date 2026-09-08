from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
from io import BytesIO
from pathlib import Path

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
CHUNK_TARGET_CHARACTERS = 1000
CHUNK_OVERLAP_CHARACTERS = 200


class DocumentParsingError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedChunk:
    ordinal: int
    content: str
    content_sha256: str


def parse_document(*, filename: str, media_type: str, content: bytes) -> tuple[str, str]:
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentParsingError("Document body must contain between 1 byte and 20 MB.")
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return content.decode("utf-8"), f"text:{suffix[1:]}"
    if suffix in {".html", ".htm"}:
        module = import_module("bs4")
        return module.BeautifulSoup(content, "html.parser").get_text("\n"), "html:beautifulsoup"
    if suffix == ".pdf":
        module = import_module("pypdf")
        pages = module.PdfReader(BytesIO(content)).pages
        return "\n".join(page.extract_text() or "" for page in pages), "pdf:pypdf"
    if suffix == ".docx":
        module = import_module("docx")
        document = module.Document(BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs), "docx:python-docx"
    raise DocumentParsingError(
        "Only PDF, DOCX, HTML, TXT, and Markdown research documents are accepted."
    )


def chunk_text(text: str) -> list[ParsedChunk]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        raise DocumentParsingError("The document contains no extractable text.")
    chunks: list[ParsedChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_TARGET_CHARACTERS, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind("\n", start + 800, end)
            if boundary > start:
                end = boundary
        content = normalized[start:end].strip()
        chunks.append(
            ParsedChunk(
                ordinal=len(chunks),
                content=content,
                content_sha256=sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP_CHARACTERS, start + 1)
    return chunks

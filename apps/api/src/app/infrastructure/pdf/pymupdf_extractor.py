"""PyMuPDF-based PDF extractor adapter.

PyMuPDF (not pdfplumber) because a 300-page book has to be parsed in seconds,
and because one call gives us the text, the outline and the per-span font sizes
that section detection needs.
"""

from pathlib import Path
from typing import Any

import pymupdf

from app.domain.ports.storage import (
    CoverImage,
    ExtractedPdf,
    OutlineEntry,
    PageText,
    PdfExtractor,
    TextLine,
)

# A PDF with less text than this is almost certainly a scan: no text layer,
# and OCR is out of scope for v1.
MIN_TOTAL_CHARS = 200
MIN_PAGES_WITH_TEXT_RATIO = 0.1


class ExtractionError(Exception):
    """Base class for anything that makes a PDF unusable."""


class CorruptPdfError(ExtractionError):
    """The file could not be opened or paged through as a PDF."""


class EmptyDocumentError(ExtractionError):
    """The PDF opened fine but carries no extractable text layer."""


def _read_page(page: Any, page_number: int) -> tuple[str, list[TextLine]]:
    """Text and line metrics from a single dict-mode parse of the page."""
    blocks: list[str] = []
    lines: list[TextLine] = []

    for block in page.get_text("dict")["blocks"]:
        # Image blocks have no "lines" key.
        block_lines: list[str] = []
        for line in block.get("lines", []):
            spans = line["spans"]
            text = "".join(span["text"] for span in spans).strip()
            if not text:
                continue
            block_lines.append(text)
            lines.append(
                TextLine(
                    page_number=page_number,
                    text=text,
                    font_size=max(span["size"] for span in spans),
                    span_count=len(spans),
                )
            )
        if block_lines:
            blocks.append("\n".join(block_lines))

    return "\n".join(blocks), lines


def _read_outline(document: Any, page_count: int) -> list[OutlineEntry]:
    entries: list[OutlineEntry] = []
    for level, title, page_number in document.get_toc():
        if not 1 <= page_number <= page_count:
            continue
        clean = title.strip()
        if clean:
            entries.append(OutlineEntry(level=level, title=clean, page_number=page_number))
    return entries


class PyMuPdfExtractor(PdfExtractor):
    """PyMuPDF implementation of PDF extraction."""

    def extract(self, file_path: str, fallback_title: str | None = None) -> ExtractedPdf:
        """Parse a PDF into pages, line metrics and its outline.

        `fallback_title` names the document when the PDF carries no metadata
        title; callers pass the original upload name, since `file_path` is the
        stored `{uuid}.pdf` and its stem would read as a random id.

        Raises `CorruptPdfError` if the file cannot be read as a PDF, and
        `EmptyDocumentError` if it has no usable text layer (a scan).
        """
        path = Path(file_path)
        try:
            document = pymupdf.open(path)
        except Exception as exc:
            raise CorruptPdfError(f"could not open PDF: {exc}") from exc

        try:
            page_count = document.page_count
            pages: list[PageText] = []
            lines: list[TextLine] = []
            for index in range(page_count):
                page_number = index + 1
                try:
                    text, page_lines = _read_page(document[index], page_number)
                except Exception as exc:
                    raise CorruptPdfError(f"could not read page {page_number}: {exc}") from exc
                pages.append(PageText(page_number=page_number, text=text))
                lines.extend(page_lines)

            metadata = document.metadata or {}
            metadata_title = metadata.get("title") or ""
            metadata_author = metadata.get("author") or ""
            title = metadata_title.strip() or (fallback_title or "").strip() or path.stem
            author = metadata_author.strip() or None
            outline = _read_outline(document, page_count)
        finally:
            document.close()

        total_chars = sum(len(page.text) for page in pages)
        pages_with_text = sum(1 for page in pages if page.text.strip())
        if total_chars < MIN_TOTAL_CHARS or (
            page_count and pages_with_text / page_count < MIN_PAGES_WITH_TEXT_RATIO
        ):
            raise EmptyDocumentError(
                "no extractable text layer "
                f"({total_chars} chars across {pages_with_text}/{page_count} pages) — "
                "this looks like a scanned PDF, and OCR is not supported"
            )

        return ExtractedPdf(
            page_count=page_count,
            title=title,
            pages=pages,
            lines=lines,
            outline=outline,
            author=author,
        )

    def render_cover(self, file_path: str, width_px: int) -> CoverImage | None:
        """Render first page as JPEG. Returns None if page is corrupt/blank."""
        path = Path(file_path)
        try:
            document = pymupdf.open(path)
        except Exception:
            return None

        try:
            if document.page_count < 1:
                return None
            page = document[0]
            # Scale so the page width is width_px; height scales proportionally
            scale = width_px / page.rect.width
            matrix = pymupdf.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix)
            jpeg_bytes = pixmap.tobytes("jpeg", jpg_quality=80)
            return CoverImage(data=jpeg_bytes, mime_type="image/jpeg")
        except Exception:
            return None
        finally:
            document.close()

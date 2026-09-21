"""PyMuPdfExtractor.render_cover / author against synthetic PDFs (no infrastructure)."""

import struct
from pathlib import Path

import pytest

from app.infrastructure.pdf.pymupdf_extractor import PyMuPdfExtractor
from factories import book_pdf, corrupt_pdf, plain_pdf

pytestmark = pytest.mark.unit


def jpeg_width(data: bytes) -> int:
    """Read the width from the first SOF marker."""
    i = 2
    while i < len(data):
        marker = data[i + 1]
        (length,) = struct.unpack(">H", data[i + 2 : i + 4])
        if marker in (0xC0, 0xC1, 0xC2):
            return struct.unpack(">H", data[i + 7 : i + 9])[0]
        i += 2 + length
    raise AssertionError("no SOF marker")


def test_renders_first_page_as_jpeg_of_requested_width(tmp_path: Path) -> None:
    cover = PyMuPdfExtractor().render_cover(str(book_pdf(tmp_path / "b.pdf")), width_px=400)

    assert cover is not None
    assert cover.mime_type == "image/jpeg"
    assert cover.data[:2] == b"\xff\xd8"
    assert abs(jpeg_width(cover.data) - 400) <= 2
    assert len(cover.data) < 100_000


def test_corrupt_pdf_returns_none(tmp_path: Path) -> None:
    assert PyMuPdfExtractor().render_cover(str(corrupt_pdf(tmp_path / "c.pdf")), 400) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert PyMuPdfExtractor().render_cover(str(tmp_path / "nope.pdf"), 400) is None


def test_extract_reads_author_from_metadata(tmp_path: Path) -> None:
    import pymupdf

    path = plain_pdf(tmp_path / "p.pdf")
    document = pymupdf.open(path)
    document.set_metadata({"author": "  Jane Author  "})
    document.saveIncr()
    document.close()

    assert PyMuPdfExtractor().extract(str(path)).author == "Jane Author"


def test_extract_without_author_is_none(tmp_path: Path) -> None:
    assert PyMuPdfExtractor().extract(str(plain_pdf(tmp_path / "p.pdf"))).author is None

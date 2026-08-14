from pathlib import Path

import pytest

import factories
from app.ingestion.extract import CorruptPdfError, EmptyDocumentError, extract_pdf


def test_extracts_pages_title_and_outline(tmp_path: Path) -> None:
    extracted = extract_pdf(factories.book_pdf(tmp_path / "book.pdf", chapters=3, pages_per=2))

    assert extracted.page_count == 6
    assert extracted.title == "The Test Book"
    assert [page.page_number for page in extracted.pages] == [1, 2, 3, 4, 5, 6]
    assert "page-3" in extracted.pages[2].text
    assert [(entry.level, entry.title, entry.page_number) for entry in extracted.outline] == [
        (1, "Chapter 1", 1),
        (1, "Chapter 2", 3),
        (1, "Chapter 3", 5),
    ]


def test_title_falls_back_to_filename_stem(tmp_path: Path) -> None:
    extracted = extract_pdf(factories.plain_pdf(tmp_path / "no-metadata.pdf"))

    assert extracted.title == "no-metadata"


def test_lines_carry_font_metrics(tmp_path: Path) -> None:
    extracted = extract_pdf(factories.headings_pdf(tmp_path / "headings.pdf"))

    headings = [line for line in extracted.lines if line.text == "Chapter 1"]
    assert len(headings) == 1
    assert headings[0].font_size > max(
        line.font_size for line in extracted.lines if line.text.startswith("page-")
    )


def test_image_only_pdf_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(EmptyDocumentError, match="scanned"):
        extract_pdf(factories.scanned_pdf(tmp_path / "scan.pdf"))


def test_truncated_pdf_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorruptPdfError):
        extract_pdf(factories.corrupt_pdf(tmp_path / "broken.pdf"))

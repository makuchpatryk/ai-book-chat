"""Synthetic PDFs, built with the same library that reads them back.

Each page carries a `page-N` marker so tests can assert page attribution, and
enough words that chunking produces several chunks per page.
"""

from pathlib import Path

import pymupdf

BODY_FONT_SIZE = 8.0
HEADING_FONT_SIZE = 20.0
WORDS_PER_PAGE = 600
MARGIN = 40


def _body_text(page_number: int) -> str:
    # Every word carries its page, so no two pages (and therefore no two chunks)
    # share text — otherwise identical chunks embed identically and any
    # nearest-neighbour assertion is a coin flip between ties.
    words = [f"page-{page_number}"] + [
        f"p{page_number:02d}w{index:04d}" for index in range(WORDS_PER_PAGE)
    ]
    return " ".join(words)


def _fill_page(page: pymupdf.Page, page_number: int, top: float = MARGIN) -> None:
    box = pymupdf.Rect(MARGIN, top, page.rect.width - MARGIN, page.rect.height - MARGIN)
    overflow = page.insert_textbox(box, _body_text(page_number), fontsize=BODY_FONT_SIZE)
    if overflow < 0:
        raise AssertionError("body text does not fit the page — lower WORDS_PER_PAGE")


def _write(document: pymupdf.Document, path: Path) -> Path:
    document.save(path)
    document.close()
    return path


def book_pdf(
    path: Path, title: str = "The Test Book", chapters: int = 3, pages_per: int = 2
) -> Path:
    """A book with PDF metadata and a real outline — the `outline` strategy."""
    document = pymupdf.open()
    document.set_metadata({"title": title})

    toc: list[list[object]] = []
    page_number = 1
    for chapter in range(1, chapters + 1):
        toc.append([1, f"Chapter {chapter}", page_number])
        for _ in range(pages_per):
            _fill_page(document.new_page(), page_number)
            page_number += 1

    document.set_toc(toc)
    return _write(document, path)


def headings_pdf(path: Path, chapters: int = 3, pages_per: int = 2) -> Path:
    """No outline, but chapter titles set in a visibly larger font."""
    document = pymupdf.open()
    page_number = 1
    for chapter in range(1, chapters + 1):
        for offset in range(pages_per):
            page = document.new_page()
            if offset == 0:
                page.insert_text(
                    (MARGIN, MARGIN + HEADING_FONT_SIZE),
                    f"Chapter {chapter}",
                    fontsize=HEADING_FONT_SIZE,
                )
                _fill_page(page, page_number, top=MARGIN + 2 * HEADING_FONT_SIZE)
            else:
                _fill_page(page, page_number)
            page_number += 1
    return _write(document, path)


def plain_pdf(path: Path, pages: int = 3) -> Path:
    """Uniform body text, no outline and no headings — the `flat` strategy."""
    document = pymupdf.open()
    for page_number in range(1, pages + 1):
        _fill_page(document.new_page(), page_number)
    return _write(document, path)


def scanned_pdf(path: Path, pages: int = 2) -> Path:
    """Image-only pages: opens fine, carries no text layer."""
    document = pymupdf.open()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pixmap.set_rect(pixmap.irect, (128, 128, 128))
    for _ in range(pages):
        page = document.new_page()
        page.insert_image(pymupdf.Rect(MARGIN, MARGIN, 400, 400), pixmap=pixmap)
    return _write(document, path)


def corrupt_pdf(path: Path) -> Path:
    """A truncated PDF: the %PDF- header survives, nothing else does."""
    document = pymupdf.open()
    _fill_page(document.new_page(), 1)
    data: bytes = document.tobytes()
    document.close()
    path.write_bytes(data[:200])
    return path

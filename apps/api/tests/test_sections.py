from pathlib import Path

import factories
from app.ingestion.extract import ExtractedPdf, PageText, TextLine, extract_pdf
from app.ingestion.sections import FRONT_MATTER_TITLE, Strategy, detect_sections


def test_outline_wins_and_chains_page_ranges(tmp_path: Path) -> None:
    extracted = extract_pdf(factories.book_pdf(tmp_path / "book.pdf", chapters=3, pages_per=2))

    sections, strategy = detect_sections(extracted)

    assert strategy is Strategy.OUTLINE
    assert [(s.title, s.start_page, s.end_page) for s in sections] == [
        ("Chapter 1", 1, 2),
        ("Chapter 2", 3, 4),
        ("Chapter 3", 5, 6),
    ]
    assert [s.order_index for s in sections] == [0, 1, 2]


def test_headings_are_used_when_there_is_no_outline(tmp_path: Path) -> None:
    extracted = extract_pdf(factories.headings_pdf(tmp_path / "headings.pdf"))

    sections, strategy = detect_sections(extracted)

    assert strategy is Strategy.HEADINGS
    assert [(s.title, s.start_page, s.end_page) for s in sections] == [
        ("Chapter 1", 1, 2),
        ("Chapter 2", 3, 4),
        ("Chapter 3", 5, 6),
    ]


def test_uniform_text_falls_back_to_one_flat_section(tmp_path: Path) -> None:
    extracted = extract_pdf(factories.plain_pdf(tmp_path / "plain.pdf", pages=3))

    sections, strategy = detect_sections(extracted)

    assert strategy is Strategy.FLAT
    assert len(sections) == 1
    assert (sections[0].start_page, sections[0].end_page) == (1, 3)
    assert sections[0].title == extracted.title


def _extracted_with_running_header(page_count: int) -> ExtractedPdf:
    """Every page opens with the same large-font book title — a running header."""
    lines: list[TextLine] = []
    for page_number in range(1, page_count + 1):
        lines.append(TextLine(page_number, "A Book About Things", 18.0, 1))
        if page_number in (1, 5, 9):
            lines.append(TextLine(page_number, f"Chapter {page_number}", 18.0, 1))
        lines.append(TextLine(page_number, f"body text on page {page_number}", 10.0, 1))

    return ExtractedPdf(
        page_count=page_count,
        title="A Book About Things",
        pages=[
            PageText(number, f"body text on page {number}") for number in range(1, page_count + 1)
        ],
        lines=lines,
        outline=[],
    )


def test_running_headers_do_not_become_sections() -> None:
    sections, strategy = detect_sections(_extracted_with_running_header(page_count=12))

    assert strategy is Strategy.HEADINGS
    assert [(s.title, s.start_page) for s in sections] == [
        ("Chapter 1", 1),
        ("Chapter 5", 5),
        ("Chapter 9", 9),
    ]


def test_content_before_the_first_heading_is_kept() -> None:
    extracted = ExtractedPdf(
        page_count=6,
        title="Book",
        pages=[PageText(number, f"page {number}") for number in range(1, 7)],
        lines=[
            TextLine(3, "Chapter 1", 18.0, 1),
            TextLine(4, "Chapter 2", 18.0, 1),
            TextLine(5, "Chapter 3", 18.0, 1),
            *[TextLine(number, f"page {number}", 10.0, 1) for number in range(1, 7)],
        ],
        outline=[],
    )

    sections, _ = detect_sections(extracted)

    assert sections[0].title == FRONT_MATTER_TITLE
    assert (sections[0].start_page, sections[0].end_page) == (1, 2)

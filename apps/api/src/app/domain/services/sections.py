"""Chapter/section detection.

Three strategies, tried in order of how much we trust them: the PDF's own
outline, then font/numbering heuristics over rendered lines, then a single flat
section. Whichever wins is recorded on the document so bad output is
diagnosable.
"""

import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple


class OutlineEntry(NamedTuple):
    """PDF outline entry."""
    level: int
    title: str
    page_number: int


class TextLine(NamedTuple):
    """Text line extracted from PDF."""
    text: str
    page_number: int
    font_size: float
    span_count: int


# A heading heuristic that fires once or twice is noise, and one that fires on
# every page is a running header — both fall through to the next strategy.
MIN_HEADING_DETECTIONS = 3
MAX_SECTIONS = 200
MAX_HEADING_CHARS = 80
HEADING_SIZE_RATIO = 1.25
RUNNING_HEADER_PAGE_RATIO = 0.5

_HEADING_PATTERNS = (
    re.compile(r"^(chapter|part|section)\s+[\dIVXLC]+", re.IGNORECASE),
    re.compile(r"^\d+(\.\d+)?\s+\S"),
)

FRONT_MATTER_TITLE = "Front matter"


class Strategy(StrEnum):
    OUTLINE = "outline"
    HEADINGS = "headings"
    FLAT = "flat"


@dataclass(frozen=True)
class SectionSpec:
    title: str
    order_index: int
    start_page: int
    end_page: int


def detect_sections(
    outline: list[OutlineEntry], lines: list[TextLine], title: str, page_count: int
) -> tuple[list[SectionSpec], Strategy]:
    """Detect sections using outline, headings, or flat layout."""
    outline_sections = _from_outline(outline, page_count)
    if outline_sections:
        return outline_sections, Strategy.OUTLINE

    heading_sections = _from_headings(lines, page_count)
    if heading_sections:
        return heading_sections, Strategy.HEADINGS

    return _flat(title, page_count), Strategy.FLAT


def _from_outline(outline: list[OutlineEntry], page_count: int) -> list[SectionSpec]:
    if not outline:
        return []

    top_level = [entry for entry in outline if entry.level == 1]
    if len(top_level) < MIN_HEADING_DETECTIONS:
        deeper = [entry for entry in outline if entry.level <= 2]
        if len(deeper) >= MIN_HEADING_DETECTIONS:
            top_level = deeper

    if not top_level:
        return []

    starts = [(entry.page_number, entry.title) for entry in top_level]
    return _sections_from_starts(starts, page_count)


def _from_headings(lines: list[TextLine], page_count: int) -> list[SectionSpec]:
    if not lines:
        return []

    body_size = _modal_font_size(lines)
    running_headers = _running_headers(lines, page_count)

    starts: list[tuple[int, str]] = []
    seen_pages: set[int] = set()
    for line in lines:
        if line.page_number in seen_pages or line.text in running_headers:
            continue
        if not _is_heading(line, body_size):
            continue
        starts.append((line.page_number, line.text))
        seen_pages.add(line.page_number)

    if not MIN_HEADING_DETECTIONS <= len(starts) <= MAX_SECTIONS:
        return []

    return _sections_from_starts(starts, page_count)


def _is_heading(line: TextLine, body_size: float) -> bool:
    if len(line.text) > MAX_HEADING_CHARS or line.span_count != 1:
        return False
    if line.font_size >= body_size * HEADING_SIZE_RATIO:
        return True
    return any(pattern.match(line.text) for pattern in _HEADING_PATTERNS)


def _modal_font_size(lines: list[TextLine]) -> float:
    """Most common rounded size — body text, since there is far more of it."""
    sizes = Counter(round(line.font_size * 2) / 2 for line in lines)
    return sizes.most_common(1)[0][0]


def _running_headers(lines: list[TextLine], page_count: int) -> set[str]:
    """Lines repeated across most pages: page headers/footers, never headings."""
    pages_per_text: dict[str, set[int]] = {}
    for line in lines:
        pages_per_text.setdefault(line.text, set()).add(line.page_number)
    threshold = page_count * RUNNING_HEADER_PAGE_RATIO
    return {text for text, pages in pages_per_text.items() if len(pages) > threshold}


def _sections_from_starts(starts: list[tuple[int, str]], page_count: int) -> list[SectionSpec]:
    """Turn (page, title) starts into contiguous, non-overlapping page ranges."""
    ordered = sorted(starts, key=lambda start: start[0])

    # Collapse starts that share a page — a section cannot be finer than a page.
    unique: list[tuple[int, str]] = []
    for page, title in ordered:
        if not unique or unique[-1][0] != page:
            unique.append((page, title))

    # Anything before the first heading (cover, TOC, preface) would otherwise be
    # dropped from the index entirely.
    if unique[0][0] > 1:
        unique.insert(0, (1, FRONT_MATTER_TITLE))

    sections: list[SectionSpec] = []
    for index, (page, title) in enumerate(unique):
        next_start = unique[index + 1][0] if index + 1 < len(unique) else page_count + 1
        sections.append(
            SectionSpec(
                title=title,
                order_index=index,
                start_page=page,
                end_page=max(page, next_start - 1),
            )
        )
    return sections


def _flat(title: str, page_count: int) -> list[SectionSpec]:
    return [SectionSpec(title=title, order_index=0, start_page=1, end_page=max(page_count, 1))]

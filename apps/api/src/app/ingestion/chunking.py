"""Token-window chunking, bounded by section.

Each section is chunked independently, so no chunk ever spans two sections.
Within a section, pages are flattened into one token stream with a
token-index -> page map, which is what gives every chunk its page citation.
"""

from dataclasses import dataclass

from app.ingestion.extract import PageText
from app.ingestion.sections import SectionSpec
from app.ingestion.tokenizer import decode, encode

# A leftover shorter than this is merged into the previous chunk rather than
# standing alone as a near-contextless fragment.
MIN_TAIL_TOKENS = 150


@dataclass(frozen=True)
class ChunkSpec:
    section_order_index: int
    order_index: int
    content: str
    page_start: int
    page_end: int
    token_count: int


def chunk_document(
    pages: list[PageText],
    sections: list[SectionSpec],
    size: int = 600,
    overlap_ratio: float = 0.15,
) -> list[ChunkSpec]:
    overlap = round(size * overlap_ratio)
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError(f"invalid chunk window: size={size}, overlap={overlap}")

    pages_by_number = {page.page_number: page for page in pages}
    chunks: list[ChunkSpec] = []

    for section in sections:
        tokens, token_pages = _section_tokens(pages_by_number, section)
        for start, end in _windows(len(tokens), size, overlap):
            chunks.append(
                ChunkSpec(
                    section_order_index=section.order_index,
                    order_index=len(chunks),
                    content=decode(tokens[start:end]),
                    page_start=token_pages[start],
                    page_end=token_pages[end - 1],
                    token_count=end - start,
                )
            )

    return chunks


def _section_tokens(
    pages_by_number: dict[int, PageText], section: SectionSpec
) -> tuple[list[int], list[int]]:
    tokens: list[int] = []
    token_pages: list[int] = []
    for page_number in range(section.start_page, section.end_page + 1):
        page = pages_by_number.get(page_number)
        if page is None or not page.text.strip():
            continue
        # The trailing newline keeps the last word of a page from being glued to
        # the first word of the next.
        page_tokens = encode(page.text + "\n")
        tokens.extend(page_tokens)
        token_pages.extend([page_number] * len(page_tokens))
    return tokens, token_pages


def _windows(total: int, size: int, overlap: int) -> list[tuple[int, int]]:
    if total == 0:
        return []

    windows: list[tuple[int, int]] = []
    start = 0
    while True:
        end = min(start + size, total)
        windows.append((start, end))
        if end == total:
            break
        start = end - overlap

    last_start, last_end = windows[-1]
    if len(windows) > 1 and last_end - last_start < MIN_TAIL_TOKENS:
        previous_start, _ = windows[-2]
        windows[-2:] = [(previous_start, last_end)]

    return windows

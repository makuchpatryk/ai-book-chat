from app.ingestion.chunking import MIN_TAIL_TOKENS, chunk_document
from app.ingestion.extract import PageText
from app.ingestion.sections import SectionSpec
from app.ingestion.tokenizer import count_tokens, encode

SIZE = 600
OVERLAP_RATIO = 0.15
OVERLAP = round(SIZE * OVERLAP_RATIO)


def _pages(count: int, words_per_page: int = 800) -> list[PageText]:
    return [
        PageText(number, " ".join(f"p{number}w{index}" for index in range(words_per_page)))
        for number in range(1, count + 1)
    ]


def _sections(*ranges: tuple[int, int]) -> list[SectionSpec]:
    return [
        SectionSpec(title=f"Section {index}", order_index=index, start_page=start, end_page=end)
        for index, (start, end) in enumerate(ranges)
    ]


def test_chunk_sizes_and_ordering() -> None:
    chunks = chunk_document(_pages(4), _sections((1, 2), (3, 4)), SIZE, OVERLAP_RATIO)

    assert [chunk.order_index for chunk in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert chunk.token_count <= SIZE + MIN_TAIL_TOKENS
        assert chunk.token_count == count_tokens(chunk.content)
    # A lone final chunk may be short; every other chunk carries real context.
    assert all(chunk.token_count >= MIN_TAIL_TOKENS for chunk in chunks[:-1])


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_document(_pages(2), _sections((1, 2)), SIZE, OVERLAP_RATIO)

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        tail = encode(previous.content)[-OVERLAP:]
        assert encode(current.content)[:OVERLAP] == tail


def test_pages_stay_inside_the_section() -> None:
    sections = _sections((1, 2), (3, 4))
    chunks = chunk_document(_pages(4), sections, SIZE, OVERLAP_RATIO)

    by_index = {section.order_index: section for section in sections}
    for chunk in chunks:
        section = by_index[chunk.section_order_index]
        assert section.start_page <= chunk.page_start <= chunk.page_end <= section.end_page


def test_chunks_never_span_two_sections() -> None:
    chunks = chunk_document(_pages(4), _sections((1, 2), (3, 4)), SIZE, OVERLAP_RATIO)

    first = [chunk for chunk in chunks if chunk.section_order_index == 0]
    second = [chunk for chunk in chunks if chunk.section_order_index == 1]
    assert max(chunk.page_end for chunk in first) < min(chunk.page_start for chunk in second)


def test_short_tail_is_merged_into_the_previous_chunk() -> None:
    # ~610 tokens: a plain window walk would leave a ~10-token orphan.
    words = " ".join(f"w{index}" for index in range(305))
    pages = [PageText(1, words)]
    total = count_tokens(words + "\n")
    assert SIZE < total < SIZE + MIN_TAIL_TOKENS

    chunks = chunk_document(pages, _sections((1, 1)), SIZE, OVERLAP_RATIO)

    assert len(chunks) == 1
    assert chunks[0].token_count == total


def test_empty_pages_produce_no_chunks() -> None:
    assert chunk_document([PageText(1, "   ")], _sections((1, 1)), SIZE, OVERLAP_RATIO) == []

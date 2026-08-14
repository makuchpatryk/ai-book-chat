"""Tokenization helpers.

`cl100k_base` is the encoding `text-embedding-3-small` uses, so counting with it
is what actually bounds the embedding request — not an approximation.
"""

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """Loading the BPE file costs ~100 ms, so it happens once per process."""
    return tiktoken.get_encoding("cl100k_base")


def encode(text: str) -> list[int]:
    # Book text can legitimately contain "<|endoftext|>"-looking strings; treat
    # every special token as ordinary text instead of raising.
    return _encoding().encode(text, disallowed_special=())


def decode(tokens: list[int]) -> str:
    return _encoding().decode(tokens)


def count_tokens(text: str) -> int:
    return len(encode(text))

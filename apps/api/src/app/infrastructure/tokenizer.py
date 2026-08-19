"""Tokenizer adapter using tiktoken."""

from functools import lru_cache

import tiktoken

from app.domain.ports.storage import TokenCounter


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """Load BPE encoding once per process."""
    return tiktoken.get_encoding("cl100k_base")


class TiktokenCounter(TokenCounter):
    """Tiktoken-based token counter."""

    def encode(self, text: str) -> list[int]:
        """Encode text to tokens."""
        # Book text can legitimately contain "<|endoftext|>"-looking strings;
        # treat every special token as ordinary text instead of raising.
        return _encoding().encode(text, disallowed_special=())

    def decode(self, tokens: list[int]) -> str:
        """Decode tokens back to text."""
        return _encoding().decode(tokens)

    def count(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encode(text))

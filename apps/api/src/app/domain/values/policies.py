"""Configuration policies as value objects."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RetrievalPolicy:
    """Policy governing document retrieval behavior."""

    top_k: int
    min_score: int
    max_distance: float
    top_n: int  # Results are cut to this many after filtering

    def override(self, top_k: int | None = None, min_score: int | None = None) -> "RetrievalPolicy":
        """Return a new policy with overridden values."""
        return replace(
            self,
            top_k=top_k if top_k is not None else self.top_k,
            min_score=min_score if min_score is not None else self.min_score,
        )


@dataclass(frozen=True)
class ChatPolicy:
    """Policy governing chat behavior."""

    max_tokens: int
    history_turns: int
    rerank_top_n: int

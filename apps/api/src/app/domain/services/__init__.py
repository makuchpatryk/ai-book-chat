"""Domain services — pure business logic."""

from app.domain.services.relevance import RetrievalOutcome, guard_and_cut

__all__ = ["RetrievalOutcome", "guard_and_cut"]

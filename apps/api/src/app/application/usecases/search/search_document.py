"""Search a document for relevant passages."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.errors import DocumentNotFound, DocumentNotReady
from app.domain.ports.llm import Embedder, Reranker
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.policies import RetrievalPolicy
from app.domain.values.retrieval import Citation, ScoredChunk
from app.domain.values.status import DocumentStatus
from app.application.usecases.chat.retrieve_context import RetrieveContext


@dataclass
class SearchOutcome:
    """Result of a search."""

    scored_chunks: list[ScoredChunk]
    grounded: bool
    reason: str


class SearchDocument:
    """Use case: search a document for relevant passages."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        embedder: Embedder,
        reranker: Reranker,
        base_policy: RetrievalPolicy,
    ):
        self.uow_factory = uow_factory
        self.embedder = embedder
        self.reranker = reranker
        self.base_policy = base_policy

    async def execute(
        self, document_id: UUID, query: str, top_k: int | None = None, min_score: int | None = None
    ) -> SearchOutcome:
        """Search document with optional policy overrides."""
        async with self.uow_factory() as uow:
            # Verify document exists and is READY
            document = await uow.documents.get(document_id)
            if document is None:
                raise DocumentNotFound()

            if document.status != DocumentStatus.READY:
                raise DocumentNotReady(activity="search")

            # Build retrieval policy with overrides
            policy = self.base_policy.override(top_k=top_k, min_score=min_score)

            # Retrieve context (this handles embed → search → rerank → guard)
            retrieve = RetrieveContext(uow, self.embedder, self.reranker, policy)
            result = await retrieve.retrieve(document_id, query)

            return SearchOutcome(
                scored_chunks=result.scored_chunks,
                grounded=result.grounded,
                reason=result.reason,
            )

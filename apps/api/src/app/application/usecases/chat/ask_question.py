"""Ask a question and stream the answer."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from app.domain.entities import Message
from app.domain.events import AnswerEvent, AnswerCompleted, AnswerFailed, SourcesFound, TokenProduced
from app.domain.ports.llm import AnswerGenerator, Embedder, QueryRewriter, Reranker
from app.domain.ports.unit_of_work import UnitOfWorkFactory
from app.domain.values.messages import Turn
from app.domain.values.policies import ChatPolicy, RetrievalPolicy
from app.domain.values.status import MessageRole
from app.application.usecases.chat.retrieve_context import RetrieveContext

ANSWER_PROMPT = """You answer questions about one book. Ground the answer in the passages
provided and cite the page for every claim drawn from them, inline, as [p.N] — use the page
range given with each passage. Where the passages only partly answer the question, say which
part the book covers, then add what you know from outside it, clearly marked as not from the
book (e.g. "Not in the book: ..."). Never present outside knowledge as if it came from the
passages, and never invent a page number for it. Write an analytical answer: explain the
reasoning the text supports, not just a one-line lookup. Answer in the language of the question."""

OUTSIDE_KNOWLEDGE_PROMPT = """You answer questions about one book, but retrieval found nothing
relevant in it for this question. Open by stating plainly that the book does not cover this,
then answer from your own general knowledge. Never cite pages and never attribute any claim to
the book. Say when you are unsure rather than guessing. Answer in the language of the question."""


class AskQuestion:
    """Use case: ask a question in a conversation and stream the answer."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        rewriter: QueryRewriter,
        embedder: Embedder,
        reranker: Reranker,
        generator: AnswerGenerator,
        retrieval_policy: RetrievalPolicy,
        chat_policy: ChatPolicy,
    ):
        self.uow_factory = uow_factory
        self.rewriter = rewriter
        self.embedder = embedder
        self.reranker = reranker
        self.generator = generator
        self.retrieval_policy = retrieval_policy
        self.chat_policy = chat_policy

    async def execute(
        self, conversation_id: UUID, question: str
    ) -> AsyncIterator[AnswerEvent]:
        """Execute the use case: rewrite → retrieve → generate → persist."""
        async with self.uow_factory() as uow:
            # Load conversation
            conversation = await uow.conversations.get(conversation_id)
            if conversation is None:
                yield AnswerFailed(detail="conversation not found")
                return

            # Load document
            document = await uow.documents.get(conversation.document_id)
            if document is None or document.status.value != "READY":
                yield AnswerFailed(detail="document not ready for chat")
                return

            # Persist the user's message now, in its own transaction, so it
            # survives a failed generation and is in the history of later turns.
            # History is read first so the new question is not sent twice.
            history = await uow.messages.recent_turns(
                conversation_id, limit=self.chat_policy.history_turns
            )
            user_msg = Message(
                id=uuid4(),
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=question,
                order_index=await uow.messages.next_order_index(conversation_id),
            )
            await uow.messages.add(user_msg)
            await uow.commit()

            # Rewrite question (best-effort; failure returns original)
            try:
                rewritten = await self.rewriter.rewrite(question, history)
            except Exception:
                rewritten = question

            # Retrieve context
            retrieve_context = RetrieveContext(
                uow, self.embedder, self.reranker, self.retrieval_policy
            )
            retrieval = await retrieve_context.retrieve(
                conversation.document_id, rewritten
            )

            # Build citations as domain values
            citations = retrieval.citations
            pages = sorted(
                set(
                    page for citation in citations
                    for page in range(citation.page_start, citation.page_end + 1)
                )
            )

            # Emit sources event
            yield SourcesFound(citations=citations, pages=pages)

            # Build chat history for generator
            chat_turns = [
                Turn(role=turn.role, content=turn.content)
                for turn in history
            ]
            chat_turns.append(Turn(role=MessageRole.USER, content=question))

            # Build system prompt
            if retrieval.grounded:
                context_text = "\n\n".join(
                    f"[Page {sc.chunk.page_start}-{sc.chunk.page_end}] {sc.chunk.content}"
                    for sc in retrieval.scored_chunks
                )
                system_prompt = f"{ANSWER_PROMPT}\n\nContext from the document:\n{context_text}"
            else:
                system_prompt = OUTSIDE_KNOWLEDGE_PROMPT

            # Stream generation
            answer_text = ""
            async for token in self.generator.stream(system_prompt, chat_turns):
                answer_text += token
                yield TokenProduced(text=token)

            # Persist message in a new transaction
            async with self.uow_factory() as persist_uow:
                try:
                    # Get next order index
                    order_index = await persist_uow.messages.next_order_index(
                        conversation_id
                    )

                    # Create assistant message with generated ID
                    assistant_msg = Message(
                        id=uuid4(),
                        conversation_id=conversation_id,
                        role=MessageRole.ASSISTANT,
                        content=answer_text,
                        order_index=order_index,
                        grounded=retrieval.grounded,
                        truncated=False,
                    )

                    await persist_uow.messages.add(assistant_msg)

                    await persist_uow.commit()
                    yield AnswerCompleted(
                        message_id=assistant_msg.id,
                        grounded=retrieval.grounded,
                        truncated=False,
                    )
                except Exception as exc:
                    await persist_uow.rollback()
                    yield AnswerFailed(detail=f"failed to save the answer: {str(exc)}")

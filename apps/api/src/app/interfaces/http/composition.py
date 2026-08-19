"""HTTP interface composition — DI factory functions for use cases."""

from typing import Union

from fastapi import Depends
from openai import AsyncOpenAI

from app.application.usecases.chat.ask_question import AskQuestion
from app.application.usecases.chat.create_conversation import CreateConversation
from app.application.usecases.chat.delete_conversation import DeleteConversation
from app.application.usecases.chat.get_messages import GetMessages
from app.application.usecases.chat.list_conversations import ListConversations
from app.domain.ports.llm import AnswerGenerator, Embedder, Reranker, QueryRewriter
from app.domain.values.policies import ChatPolicy, RetrievalPolicy
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWorkFactory
from app.infrastructure.embeddings.adapters import build_embedder
from app.infrastructure.llm.adapters import (
    FakeGenerator,
    FakeReranker,
    FakeRewriter,
    OpenAIGenerator,
    OpenAIReranker,
    OpenAIRewriter,
)
from app.infrastructure.db.session import AsyncSessionLocal


def build_adapters(settings: Settings) -> tuple[AnswerGenerator, QueryRewriter, Reranker, Embedder]:
    """Build LLM adapters based on settings."""
    if settings.llm_token:
        client = AsyncOpenAI(
            api_key=settings.llm_token,
            base_url=settings.llm_base_url,
        )
        generator: AnswerGenerator = OpenAIGenerator(client, settings.chat_model, settings.chat_max_tokens)
        rewriter: QueryRewriter = OpenAIRewriter(client, settings.chat_rewrite_model)
        reranker: Reranker = OpenAIReranker(client, settings.rerank_model)
    else:
        generator = FakeGenerator()
        rewriter = FakeRewriter()
        reranker = FakeReranker()

    embedder = build_embedder(settings)
    return generator, rewriter, reranker, embedder


async def get_ask_question(settings: Settings = Depends(get_settings)) -> AskQuestion:
    """FastAPI dependency for AskQuestion use case."""
    uow_factory = SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal)
    generator, rewriter, reranker, embedder = build_adapters(settings)

    retrieval_policy = RetrievalPolicy(
        top_k=settings.retrieval_top_k,
        min_score=settings.rerank_min_score,
        max_distance=settings.retrieval_max_distance,
        top_n=settings.rerank_top_n,
    )

    chat_policy = ChatPolicy(
        max_tokens=settings.chat_max_tokens,
        history_turns=settings.chat_history_turns,
        rerank_top_n=settings.rerank_top_n,
    )

    return AskQuestion(
        uow_factory=uow_factory,
        rewriter=rewriter,
        embedder=embedder,
        reranker=reranker,
        generator=generator,
        retrieval_policy=retrieval_policy,
        chat_policy=chat_policy,
    )


async def get_create_conversation(settings: Settings = Depends(get_settings)) -> CreateConversation:
    """FastAPI dependency for CreateConversation use case."""
    uow_factory = SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal)
    return CreateConversation(uow_factory)


async def get_list_conversations(settings: Settings = Depends(get_settings)) -> ListConversations:
    """FastAPI dependency for ListConversations use case."""
    uow_factory = SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal)
    return ListConversations(uow_factory)


async def get_get_messages(settings: Settings = Depends(get_settings)) -> GetMessages:
    """FastAPI dependency for GetMessages use case."""
    uow_factory = SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal)
    return GetMessages(uow_factory)


async def get_delete_conversation(settings: Settings = Depends(get_settings)) -> DeleteConversation:
    """FastAPI dependency for DeleteConversation use case."""
    uow_factory = SqlAlchemyUnitOfWorkFactory(AsyncSessionLocal)
    return DeleteConversation(uow_factory)

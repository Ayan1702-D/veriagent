"""FastAPI application factory and production application instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from veriagent.api import corpus_router, runs_router
from veriagent.api.errors import install_error_handlers
from veriagent.api.rate_limit import InMemoryRateLimitMiddleware
from veriagent.api.service import FetchFunction, RunService
from veriagent.config import Settings, get_settings
from veriagent.db import (
    RunRepository,
    create_database_engine,
    create_schema,
    create_session_factory,
)
from veriagent.demo import seed_demo_runs
from veriagent.llm.cache import CassetteCache
from veriagent.llm.client import LLMClient, LLMProtocol
from veriagent.llm.router import ModelRouter
from veriagent.rag import CorpusIndex, CorpusSearchProvider
from veriagent.tools.fetch import fetch_url
from veriagent.tools.search import (
    DuckDuckGoSearchProvider,
    OpenAlexSearchProvider,
    SearchProvider,
    TavilySearchProvider,
    WikipediaSearchProvider,
)


def _default_llm(settings: Settings) -> LLMClient:
    return LLMClient(ModelRouter(settings), cache=CassetteCache(mode="record"))


def _default_search_providers(
    settings: Settings, corpus_index: CorpusIndex
) -> list[SearchProvider]:
    providers: list[SearchProvider] = []
    if settings.corpus_enabled:
        providers.append(CorpusSearchProvider(corpus_index, top_k=settings.corpus_top_k))
    providers.extend(
        [
            DuckDuckGoSearchProvider(),
            WikipediaSearchProvider(),
            OpenAlexSearchProvider(mailto=settings.openalex_mailto),
        ]
    )
    if settings.tavily_api_key:
        providers.append(TavilySearchProvider(settings.tavily_api_key))
    return providers


def create_app(
    *,
    settings: Settings | None = None,
    llm: LLMProtocol | None = None,
    search_providers: list[SearchProvider] | None = None,
    fetch_fn: FetchFunction | None = None,
    engine: Engine | None = None,
) -> FastAPI:
    """Build an application with injectable runtime dependencies for tests."""
    active_settings = settings or get_settings()
    active_engine = engine or create_database_engine(active_settings.database_url)
    session_factory = create_session_factory(active_engine)
    repository = RunRepository(session_factory)
    corpus_index = CorpusIndex(
        persist_path=Path(active_settings.chroma_path),
        collection_name=active_settings.corpus_collection,
        embedding_model_name=active_settings.corpus_embedding_model,
        chunk_size=active_settings.corpus_chunk_size,
        chunk_overlap=active_settings.corpus_chunk_overlap,
    )
    service = RunService(
        repository=repository,
        llm=llm or _default_llm(active_settings),
        search_providers=(
            search_providers
            if search_providers is not None
            else _default_search_providers(active_settings, corpus_index)
        ),
        fetch_fn=fetch_fn or fetch_url,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        create_schema(active_engine)
        if active_settings.demo_replay_enabled:
            seed_demo_runs(repository, active_settings.default_budget())
        yield
        active_engine.dispose()

    app = FastAPI(title="VeriAgent API", version="0.1.0", lifespan=lifespan)
    app.state.settings = active_settings
    app.state.run_service = service
    app.state.engine = active_engine
    app.state.corpus_index = corpus_index

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(
        InMemoryRateLimitMiddleware,
        limit=active_settings.rate_limit_requests,
        window_seconds=active_settings.rate_limit_window_seconds,
    )
    install_error_handlers(app)
    app.include_router(runs_router)
    app.include_router(corpus_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

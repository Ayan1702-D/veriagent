"""Researcher node: executes queries, fetches, parses, ranks, and dedupes sources."""

import hashlib
from typing import Any

from veriagent.core.errors import BudgetExceededError
from veriagent.graph.state import GraphState
from veriagent.ranking.dedupe import deduplicate_sources
from veriagent.ranking.scorer import SourceScorer
from veriagent.schemas import Source, SourceType
from veriagent.tools.fetch import fetch_url
from veriagent.tools.parse import parse_html_to_snapshot


async def run_researcher_node(state: GraphState) -> dict[str, Any]:
    """Execute search queries across providers, fetch pages, parse snapshots, rank, and dedupe."""
    subquestions = state["subquestions"]
    providers = state["search_providers"]
    budget = state["budget"]
    recorder = state.get("recorder")
    fetch_fn = state.get("fetch_fn") or fetch_url

    scorer = SourceScorer()
    existing_sources = {s.url: s for s in state.get("sources", [])}
    snapshots = dict(state.get("snapshots", {}))

    fetched_candidates: list[tuple[Source, str]] = []
    attempted_urls: set[str] = set()
    # Leave a bounded share of the remaining run for extraction and verification.
    research_time_reserve = min(30.0, float(budget.remaining()["seconds"]) / 2)

    def research_time_available() -> bool:
        """Return whether another retrieval can start without spending the reserve."""
        return float(budget.remaining()["seconds"]) > research_time_reserve

    # Share fetch attempts across planned queries so the first query cannot
    # consume every slot before later subquestions are searched.
    queries = [query for sq in subquestions for query in sq.search_queries]
    for query_index, q in enumerate(queries):
        remaining = budget.remaining()
        if not research_time_available() or any(
            remaining[kind] <= 0 for kind in ("searches", "fetches", "seconds")
        ):
            break
        fetches_at_start = int(budget.usage()["fetches"])
        remaining_queries = len(queries) - query_index
        remaining_fetches = int(budget.remaining()["fetches"])
        fetch_limit = (remaining_fetches + remaining_queries - 1) // remaining_queries

        selected = providers[query_index % len(providers)] if providers else None
        for provider in [selected] if selected is not None else []:
            if (
                not research_time_available()
                or any(budget.remaining()[kind] <= 0 for kind in ("searches", "fetches"))
                or int(budget.usage()["fetches"]) - fetches_at_start >= fetch_limit
            ):
                break
            try:
                hits = await provider.search(
                    query=q,
                    limit=3,
                    budget=budget,
                    recorder=recorder,
                )
            except BudgetExceededError:
                break

            for hit in hits:
                if (
                    not research_time_available()
                    or int(budget.usage()["fetches"]) - fetches_at_start >= fetch_limit
                ):
                    break
                remaining = budget.remaining()
                if (
                    hit.url in attempted_urls
                    or hit.url in existing_sources
                    or remaining["fetches"] <= 0
                    or remaining["seconds"] <= 0
                ):
                    continue
                attempted_urls.add(hit.url)
                try:
                    if hit.source_type == SourceType.CURATED and hit.snapshot_text:
                        budget.consume("fetches", 1)
                        snapshot_text = hit.snapshot_text.strip()
                        if not snapshot_text:
                            continue
                        digest = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
                        source_obj = Source(
                            url=hit.url,
                            title=hit.title,
                            domain="curated",
                            snapshot_hash=f"sha256:{digest}",
                            rank_score=hit.rank_score if hit.rank_score is not None else 0.8,
                            source_type=SourceType.CURATED,
                        )
                        fetched_candidates.append((source_obj, snapshot_text))
                        snapshots[source_obj.id] = snapshot_text
                        existing_sources[source_obj.url] = source_obj
                        if recorder is not None:
                            recorder.record(
                                node="researcher",
                                type="curated_chunk_loaded",
                                payload={"url": hit.url, "title": hit.title},
                            )
                        continue

                    doc = await fetch_fn(
                        url=hit.url,
                        budget=budget,
                        recorder=recorder,
                    )
                    snapshot = parse_html_to_snapshot(doc.content, hit.url)
                    if not snapshot.clean_text:
                        continue

                    score, _, stype = scorer.score(snapshot.url, snapshot.date)
                    source_obj = snapshot.to_source(rank_score=score, source_type=stype)
                    source_obj = source_obj.model_copy(
                        update={"title": hit.title or source_obj.title}
                    )

                    fetched_candidates.append((source_obj, snapshot.clean_text))
                    snapshots[source_obj.id] = snapshot.clean_text
                    existing_sources[source_obj.url] = source_obj
                except Exception as exc:
                    if recorder is not None:
                        recorder.record(
                            node="researcher",
                            type="source_fetch_failed",
                            payload={"url": hit.url, "reason": type(exc).__name__},
                        )
                    continue

    # Deduplicate candidates across syndication / mirrors
    clusters = deduplicate_sources(fetched_candidates)
    canonical_sources = [c.canonical_source for c in clusters]

    all_sources = list(
        {s.id: s for s in list(existing_sources.values()) + canonical_sources}.values()
    )
    all_sources.sort(key=lambda x: x.rank_score, reverse=True)

    if recorder is not None:
        recorder.record(
            node="researcher",
            type="research_completed",
            payload={
                "total_sources": len(all_sources),
                "snapshots_stored": len(snapshots),
            },
        )

    return {
        "sources": all_sources,
        "snapshots": snapshots,
    }

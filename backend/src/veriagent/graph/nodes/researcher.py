"""Researcher node: executes queries, fetches, parses, ranks, and dedupes sources."""

from typing import Any

from veriagent.core.errors import BudgetExceededError
from veriagent.graph.state import GraphState
from veriagent.ranking.dedupe import deduplicate_sources
from veriagent.ranking.scorer import SourceScorer
from veriagent.schemas import Source
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

    # Iterate over subquestions and issue searches until budget limit or query set completes
    for sq in subquestions:
        for q in sq.search_queries:
            if budget.exhausted():
                break

            for provider in providers:
                if budget.exhausted():
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
                    if hit.url in existing_sources or budget.exhausted():
                        continue
                    try:
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
                    except Exception:
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

"""Unit tests for L3 tools (search, fetch, parse, SSRF guard) and ranking/dedupe."""

import socket

import httpx
import pytest

from veriagent.core.errors import SecurityViolationError, VeriAgentError
from veriagent.core.security import validate_and_resolve_url
from veriagent.ranking.dedupe import deduplicate_sources
from veriagent.ranking.scorer import SourceScorer
from veriagent.schemas import Source, SourceType
from veriagent.tools.fetch import fetch_url
from veriagent.tools.parse import parse_html_to_snapshot
from veriagent.tools.search import OpenAlexSearchProvider, WikipediaSearchProvider


def test_ssrf_rejects_loopback_and_metadata_addresses() -> None:
    """Verify SSRF guard rejects loopback 127.0.0.1 and AWS metadata 169.254.169.254."""
    # Direct loopback IP
    with pytest.raises(SecurityViolationError, match="SSRF violation"):
        validate_and_resolve_url("http://127.0.0.1/admin")

    # AWS/Cloud link-local metadata IP
    with pytest.raises(SecurityViolationError, match="SSRF violation"):
        validate_and_resolve_url("http://169.254.169.254/latest/meta-data/")

    # Prohibited scheme
    with pytest.raises(SecurityViolationError, match="Prohibited URL scheme"):
        validate_and_resolve_url("file:///etc/passwd")


def test_ssrf_resolves_dns_and_blocks_private_targets() -> None:
    """Verify SSRF guard inspects DNS responses and blocks names resolving to internal IPs."""

    def fake_dns_resolver(host: str, *args: object, **kwargs: object) -> list[tuple[object, ...]]:
        if host == "malicious.internal.local":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

    with pytest.raises(SecurityViolationError, match="restricted IP"):
        validate_and_resolve_url("http://malicious.internal.local/leak", resolver=fake_dns_resolver)

    assert (
        validate_and_resolve_url("http://example.com/ok", resolver=fake_dns_resolver)
        == "http://example.com/ok"
    )


@pytest.mark.asyncio
async def test_fetch_url_respects_mocked_http_and_type_check() -> None:
    """Verify fetch_url accepts text/html, blocks unsupported MIME types and handles redirects."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "http://example.com/redirect":
            return httpx.Response(302, headers={"Location": "http://example.com/target"})
        if url == "http://example.com/target":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                text="<html><body>Hello</body></html>",
            )
        if url == "http://example.com/binary":
            return httpx.Response(
                200, headers={"Content-Type": "application/octet-stream"}, content=b"\x00\x01\x02"
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # Successful fetch via redirect
        doc = await fetch_url("http://example.com/redirect", client=client)
        assert doc.status_code == 200
        assert "Hello" in doc.content

        # Unsupported content-type rejection
        with pytest.raises(VeriAgentError, match="Unsupported content-type"):
            await fetch_url("http://example.com/binary", client=client)


def test_parse_html_to_snapshot() -> None:
    """Verify trafilatura parser produces clean text and deterministic sha256 hash."""
    html = """
    <html>
      <head><title>Electric Vehicles Climate Impact</title></head>
      <body>
        <article>
          <h1>Electric Vehicles Climate Impact</h1>
        <p>
            Electric cars generate significantly fewer emissions over 
            their lifetime compared to gas cars.
        </p>
        </article>
      </body>
    </html>
    """
    snapshot = parse_html_to_snapshot(html, url="https://example.org/ev")
    assert snapshot.url == "https://example.org/ev"
    assert "Electric Vehicles Climate Impact" in snapshot.title
    assert "fewer emissions over their lifetime" in snapshot.clean_text
    assert snapshot.snapshot_hash.startswith("sha256:")

    source = snapshot.to_source(rank_score=0.8, source_type=SourceType.SECONDARY)
    assert source.domain == "example.org"
    assert source.rank_score == 0.8


def test_ranking_scorer_and_domain_tiers() -> None:
    """Verify SourceScorer assigns high authority to .gov/.edu and computes recency bonus."""
    scorer = SourceScorer()

    score_gov, reason_gov, type_gov = scorer.score(
        "https://epa.gov/clean-vehicles", date_str="2025-01-15"
    )
    assert score_gov >= 0.85
    assert type_gov == SourceType.PRIMARY
    assert "high_trust" in reason_gov

    score_blog, reason_blog, type_blog = scorer.score("https://myrandomblog.blogspot.com/post-1")
    assert score_blog <= 0.40
    assert type_blog == SourceType.BLOG
    assert "low_trust" in reason_blog


def test_deduplicate_sources_groups_syndicated_copies() -> None:
    """Verify near-duplicate articles are grouped into one cluster, keeping highest rank."""
    s1 = Source(
        url="https://reuters.com/wire-1", domain="reuters.com", snapshot_hash="h1", rank_score=0.85
    )
    s2 = Source(
        url="https://syndicate-partner.com/wire-1",
        domain="syndicate-partner.com",
        snapshot_hash="h1",
        rank_score=0.60,
    )
    s3 = Source(
        url="https://different.org/study",
        domain="different.org",
        snapshot_hash="h2",
        rank_score=0.90,
    )

    text_reuters = (
        "Electric vehicles reduce emissions in 95% of the world according to a study by Cambridge."
    )
    text_syndicate = (
        "Electric vehicles reduce emissions in 95% of the world according to a Cambridge study."
    )
    text_different = (
        "Battery manufacturing requires intensive mining of lithium and cobalt materials."
    )

    clusters = deduplicate_sources(
        [
            (s1, text_reuters),
            (s2, text_syndicate),
            (s3, text_different),
        ],
        similarity_threshold=80.0,
    )

    assert len(clusters) == 2
    # First cluster contains s1 (canonical) and s2 (duplicate)
    reuters_cluster = next(c for c in clusters if c.canonical_source.id == s1.id)
    assert len(reuters_cluster.duplicate_sources) == 1
    assert reuters_cluster.duplicate_sources[0].id == s2.id


@pytest.mark.asyncio
async def test_search_providers_mocked_http() -> None:
    """Verify Wikipedia and OpenAlex search providers handle API responses cleanly."""

    def wiki_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": {
                    "search": [
                        {
                            "title": "Electric vehicle",
                            "pageid": 12345,
                            "snippet": "An <b>electric vehicle</b> uses motors",
                        }
                    ]
                }
            },
        )

    wiki_transport = httpx.MockTransport(wiki_handler)
    async with httpx.AsyncClient(transport=wiki_transport) as client:
        wiki = WikipediaSearchProvider(client=client)
        hits = await wiki.search("electric vehicle")
        assert len(hits) == 1
        assert hits[0].title == "Electric vehicle"
        assert hits[0].provider == "wikipedia"

    def openalex_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Lifecycle emissions of EVs",
                        "doi": "https://doi.org/10.1038/example",
                        "publication_year": 2024,
                        "cited_by_count": 88,
                    }
                ]
            },
        )

    alex_transport = httpx.MockTransport(openalex_handler)
    async with httpx.AsyncClient(transport=alex_transport) as client:
        alex = OpenAlexSearchProvider(mailto="test@example.org", client=client)
        alex_hits = await alex.search("ev emissions")
        assert len(alex_hits) == 1
        assert alex_hits[0].title == "Lifecycle emissions of EVs"
        assert "2024" in alex_hits[0].snippet

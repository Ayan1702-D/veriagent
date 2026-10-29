"""Async safe web fetcher with SSRF defense, redirect re-validation, and size limits."""

import logging
from urllib.parse import urljoin

import httpx

from veriagent.audit.recorder import AuditRecorder
from veriagent.core.budget import BudgetGovernor
from veriagent.core.errors import SecurityViolationError, VeriAgentError
from veriagent.core.security import validate_and_resolve_url

logger = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_CONTENT_PREFIXES = ("text/html", "text/plain", "application/xhtml+xml")


class FetchedDocument:
    """Raw payload of an HTTP fetch before text extraction."""

    def __init__(self, url: str, content: str, status_code: int, content_type: str) -> None:
        self.url = url
        self.content = content
        self.status_code = status_code
        self.content_type = content_type


async def fetch_url(
    url: str,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    timeout: float = 10.0,
    max_redirects: int = 3,
    budget: BudgetGovernor | None = None,
    recorder: AuditRecorder | None = None,
    client: httpx.AsyncClient | None = None,
) -> FetchedDocument:
    """Fetch URL safely: re-validates SSRF on every hop, verifies content-type, enforces size."""
    if budget is not None:
        budget.consume("fetches", 1)

    target_url = validate_and_resolve_url(url)
    redirects_left = max_redirects

    headers = {
        "User-Agent": "VeriAgent/0.1.0 (Mozilla/5.0 compatible; Research bot)",
        "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
    }

    local_client = client is not None
    active_client = client or httpx.AsyncClient(
        follow_redirects=False,
        verify=True,
        timeout=timeout,
    )

    try:
        while True:
            resp = await active_client.get(target_url, headers=headers)

            if resp.is_redirect:
                if redirects_left <= 0:
                    raise SecurityViolationError("Max redirects exceeded")
                redirects_left -= 1
                location = resp.headers.get("location")
                if not location:
                    raise SecurityViolationError("Redirect header missing location")
                next_url = urljoin(target_url, location)
                target_url = validate_and_resolve_url(next_url)
                continue

            content_type = resp.headers.get("content-type", "").lower()
            if not any(content_type.startswith(p) for p in _ALLOWED_CONTENT_PREFIXES):
                raise VeriAgentError(f"Unsupported content-type: {content_type}")

            body_bytes = resp.content
            if len(body_bytes) > max_bytes:
                raise VeriAgentError(
                    f"Fetched size {len(body_bytes)} exceeds limit {max_bytes} bytes"
                )

            text_content = resp.text

            if recorder is not None:
                recorder.record(
                    node="researcher",
                    type="url_fetched",
                    payload={
                        "url": target_url,
                        "status": resp.status_code,
                        "bytes": len(body_bytes),
                    },
                )

            return FetchedDocument(
                url=target_url,
                content=text_content,
                status_code=resp.status_code,
                content_type=content_type,
            )
    finally:
        if not local_client:
            await active_client.aclose()

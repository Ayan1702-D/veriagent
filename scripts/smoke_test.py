"""Smoke-test a deployed API using only the Python standard library."""

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEMO_RUN_ID = "demo-ev-grid"


def request_json(base_url: str, path: str, method: str = "GET") -> dict[str, Any]:
    """Make one JSON request and return its object response."""
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=b"" if method == "POST" else None,
        method=method,
        headers={"Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected a JSON object from {path}")
    return payload


def smoke_test(base_url: str, timeout_seconds: float = 90.0) -> str:
    """Check health, start a seeded replay, and wait for its completed report."""
    health = request_json(base_url, "/health")
    if health != {"status": "ok"}:
        raise RuntimeError(f"Unexpected health response: {health}")

    accepted = request_json(base_url, f"/api/runs/{DEMO_RUN_ID}/replay", "POST")
    replay_id = accepted.get("run_id")
    if not isinstance(replay_id, str) or not replay_id:
        raise RuntimeError(f"Replay was not accepted: {accepted}")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        run = request_json(base_url, f"/api/runs/{replay_id}")
        status = run.get("status")
        if status == "completed":
            report = run.get("report")
            if not isinstance(report, dict) or not report.get("verdict"):
                raise RuntimeError("Completed replay did not include a verdict")
            return replay_id
        if status == "failed":
            raise RuntimeError(f"Replay failed: {run.get('error')}")
        time.sleep(0.5)
    raise TimeoutError(f"Replay {replay_id} did not complete within {timeout_seconds}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    try:
        replay_id = smoke_test(args.base_url, args.timeout)
    except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
        print(f"SMOKE TEST FAILED: {exc}")
        return 1
    print(f"SMOKE TEST PASSED: health ok; replay {replay_id} completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

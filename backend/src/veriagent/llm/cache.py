"""Deterministic record/replay cassette cache for LLM responses."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from veriagent.core.errors import VeriAgentError

CacheMode = Literal["live", "record", "replay"]
_DEFAULT_CASSETTE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "cassettes"


class CassetteMissError(VeriAgentError):
    """Raised in replay mode when a requested cassette key does not exist on disk."""

    def __init__(self, key: str, path: Path) -> None:
        self.key = key
        self.path = path
        super().__init__(f"Cassette miss in replay mode for key={key} at {path}")


@dataclass(frozen=True)
class CachedLLMResponse:
    """Serialized LLM completion stored inside a cassette file."""

    key: str
    node: str
    model: str
    content: str
    tokens: int


class CassetteCache:
    """Stores and retrieves keyed LLM completions as JSON files."""

    def __init__(
        self,
        mode: CacheMode = "live",
        cassette_dir: Path | None = None,
    ) -> None:
        """Initialize cache with mode ('live', 'record', 'replay') and directory."""
        if mode not in ("live", "record", "replay"):
            raise ValueError(f"Invalid cache mode: {mode!r}")
        self._mode: CacheMode = mode
        self._dir = cassette_dir if cassette_dir is not None else _DEFAULT_CASSETTE_DIR

    @property
    def mode(self) -> CacheMode:
        """Return the active cache mode."""
        return self._mode

    @property
    def cassette_dir(self) -> Path:
        """Return the directory where cassette JSON files are stored."""
        return self._dir

    @staticmethod
    def compute_key(node: str, model: str, messages: list[dict[str, str]]) -> str:
        """Compute a deterministic SHA-256 hex digest over node, model, and messages."""
        canonical = json.dumps(
            {"node": node, "model": model, "messages": messages},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _path_for(self, key: str) -> Path:
        """Return the JSON file path for a cassette key."""
        return self._dir / f"{key}.json"

    def get(
        self,
        node: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> CachedLLMResponse | None:
        """Return cached response in replay mode, or None in live/record modes."""
        if self._mode != "replay":
            return None

        key = self.compute_key(node, model, messages)
        path = self._path_for(key)
        if not path.is_file():
            raise CassetteMissError(key, path)

        raw = json.loads(path.read_text(encoding="utf-8"))
        return CachedLLMResponse(
            key=str(raw["key"]),
            node=str(raw["node"]),
            model=str(raw["model"]),
            content=str(raw["content"]),
            tokens=int(raw.get("tokens", 0)),
        )

    def put(
        self,
        node: str,
        model: str,
        messages: list[dict[str, str]],
        content: str,
        tokens: int,
    ) -> CachedLLMResponse | None:
        """Write response to disk when in record mode; no-op otherwise."""
        if self._mode != "record":
            return None

        self._dir.mkdir(parents=True, exist_ok=True)
        key = self.compute_key(node, model, messages)
        entry = CachedLLMResponse(
            key=key,
            node=node,
            model=model,
            content=content,
            tokens=tokens,
        )
        payload = {
            "key": entry.key,
            "node": entry.node,
            "model": entry.model,
            "messages": messages,
            "content": entry.content,
            "tokens": entry.tokens,
        }
        self._path_for(key).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return entry

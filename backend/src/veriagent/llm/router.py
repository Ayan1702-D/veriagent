"""Model router mapping graph nodes to configured cheap or strong LLM models."""

from veriagent.config import Settings

_STRONG_NODES: frozenset[str] = frozenset({"contradiction", "reporter"})
_CHEAP_NODES: frozenset[str] = frozenset({"planner", "extractor", "verifier"})


class ModelRouter:
    """Routes each workflow node to either the cheap or strong model from Settings."""

    def __init__(self, settings: Settings) -> None:
        """Initialize router with environment-backed Settings."""
        self._settings = settings

    def model_for(self, node: str) -> str:
        """Return the configured LiteLLM model identifier for `node`."""
        normalized = node.strip().lower()
        if normalized in _STRONG_NODES:
            return self._settings.strong_model
        if normalized in _CHEAP_NODES:
            return self._settings.cheap_model
        raise ValueError(f"Unknown LLM node for routing: {node!r}")
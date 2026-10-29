"""Search provider implementations."""

from veriagent.tools.search.base import SearchProvider, SearchResult
from veriagent.tools.search.ddg import DuckDuckGoSearchProvider
from veriagent.tools.search.openalex import OpenAlexSearchProvider
from veriagent.tools.search.tavily import TavilySearchProvider
from veriagent.tools.search.wikipedia import WikipediaSearchProvider

__all__ = [
    "DuckDuckGoSearchProvider",
    "OpenAlexSearchProvider",
    "SearchProvider",
    "SearchResult",
    "TavilySearchProvider",
    "WikipediaSearchProvider",
]

from typing import Literal
from clients.tavily_client import TavilyClient


def web_search(client: TavilyClient, query: str, k: int = 5) -> str:
    """Search the web and return the top k results as LLM-ready text.

    Args:
        client: Tavily client instance.
        query: The search query string.
        k: Number of results to return.
    """
    results = client.search(query, max_results=k)
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.get('title', 'No title')}")
        lines.append(f"    URL: {r.get('url', '')}")
        lines.append(f"    {r.get('content', '')}")
    return "\n".join(lines)


def make_web_search_tool(client: TavilyClient, k: int = 5):
    """Bind a Tavily client to web_search, returning a LangChain-compatible tool."""
    def _tool(query: str, effort: Literal["low", "high"] = "low") -> str:
        """Search the web and return the top k results as LLM-ready text.

        Args:
            query: The search query string.
            effort: The search effort level.
        """
        if effort == "high":
            return web_search(client, query, 20)
        else:
            return web_search(client, query, k)
    return _tool

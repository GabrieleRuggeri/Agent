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

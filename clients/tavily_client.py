import os
from tavily import TavilyClient as _TavilyClient


class TavilyClient:
    def __init__(self, api_key: str | None = None):
        self._client = _TavilyClient(api_key=api_key or os.environ["TAVILY_API_KEY"])

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        response = self._client.search(query, max_results=max_results)
        return response.get("results", [])

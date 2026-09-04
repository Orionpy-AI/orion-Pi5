# search.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # reads .env in the current working directory

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"


def tavily_search(query: str, max_results: int = 3) -> str:
    """Query the Tavily search API and return a short text summary of results."""
    if not TAVILY_API_KEY:
        return "Search error: TAVILY_API_KEY is not set (check your .env file)."

    try:
        resp = requests.post(
            TAVILY_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        return f"Search error: {e}"

    results = data.get("results", [])
    if not results:
        return f"No search results found for '{query}'."

    lines = [f"Search results for '{query}':"]
    answer = data.get("answer")
    if answer:
        lines.append(f"Quick answer: {answer}")
    for r in results[:max_results]:
        title = r.get("title", "Untitled")
        content = (r.get("content", "") or "")[:300]
        url = r.get("url", "")
        lines.append(f"- {title}: {content} ({url})")

    return "\n".join(lines)

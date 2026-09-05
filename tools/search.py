# search.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # reads .env in the current working directory

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"


def tavily_search(query: str, max_results: int = 3) -> str:
    """Query the Tavily search API or fall back to DuckDuckGo web search."""
    if TAVILY_API_KEY:
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
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
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
        except Exception:
            pass

    # Free DuckDuckGo Search Fallback
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            import re
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', res.text, re.DOTALL)
            titles = re.findall(r'<a class="result__url[^>]*>(.*?)</a>', res.text, re.DOTALL)
            if snippets:
                lines = [f"Web search results for '{query}':"]
                for i in range(min(max_results, len(snippets))):
                    clean_snip = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                    clean_title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else "Result"
                    lines.append(f"- {clean_title}: {clean_snip}")
                return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"

    return f"No search results found for '{query}'."

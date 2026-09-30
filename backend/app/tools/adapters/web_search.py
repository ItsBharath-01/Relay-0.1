import re
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
import httpx

from app.tools.registry.base import BaseTool

class WebSearchTool(BaseTool):
    id = "web_search_engine"
    name = "Public Web Search"
    tool_type = "api"
    provides = ["web_search"]
    requires_connection = None
    required_permissions = []

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get("https://html.duckduckgo.com/html/?q=ping")
                if res.status_code < 400:
                    return True, "Web search service is online"
                return False, f"HTTP {res.status_code}"
        except Exception as e:
            return False, str(e)

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Dict[str, Any]:
        query = params.get("query", "").strip()
        if not query:
            raise ValueError("Parameter 'query' is required for web search.")

        max_results = int(params.get("max_results", 5))

        # Perform live web search via DuckDuckGo HTML endpoint
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        data = {"q": query}

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.post(url, data=data, headers=headers)
            if res.status_code != 200:
                raise RuntimeError(f"Web search engine returned HTTP {res.status_code}")

            html = res.text
            results = []

            # Extract search snippets and links from DuckDuckGo HTML
            # Pattern matches <a class="result__snippet" ...> or <a class="result__url" ...>
            raw_results = re.findall(
                r'<h2 class="result__title">[\s\S]*?<a class="result__url" href="([^"]+)">([\s\S]*?)</a>[\s\S]*?<a class="result__snippet[^"]*"[^>]*>([\s\S]*?)</a>',
                html
            )

            for link, title, snippet in raw_results[:max_results]:
                # Clean duckduckgo redirect link: //duckduckgo.com/l/?uddg=URL
                clean_link = link
                if "uddg=" in link:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                    if "uddg" in parsed:
                        clean_link = parsed["uddg"][0]

                # Strip HTML tags
                clean_title = re.sub(r"<[^>]+>", "", title).strip()
                clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()

                if clean_link and clean_title:
                    results.append({
                        "title": clean_title,
                        "url": clean_link,
                        "snippet": clean_snippet
                    })

            # Fallback regex if DuckDuckGo altered class names
            if not results:
                links = re.findall(r'<a[^>]*class="result__snippet"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', html)
                for lk, snip in links[:max_results]:
                    results.append({
                        "title": "Search Result",
                        "url": lk,
                        "snippet": re.sub(r"<[^>]+>", "", snip).strip()
                    })

            return {
                "query": query,
                "result_count": len(results),
                "results": results
            }

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        results = result.get("results", [])
        passed = len(results) > 0
        evidence = {
            "query": params.get("query"),
            "items_returned": len(results),
            "top_url": results[0].get("url") if results else None
        }
        return passed, evidence

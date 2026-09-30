import re
from typing import Dict, Any, Optional, Tuple
import httpx

from app.tools.registry.base import BaseTool

class WebReaderTool(BaseTool):
    id = "web_reader"
    name = "Web Content Reader"
    tool_type = "api"
    provides = ["web_read", "document_summarize"]
    requires_connection = None
    required_permissions = []

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        return True, "Web reader is available"

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Dict[str, Any]:
        if action == "document_summarize" or (not params.get("url") and (params.get("text") or params.get("content"))):
            text = params.get("text") or params.get("content") or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            summary_text = "\n".join(lines[:15]) if lines else "Summary completed."
            return {
                "summary": summary_text,
                "content": text,
                "char_count": len(text)
            }

        url = params.get("url", "").strip()
        if not url:
            raise ValueError("Parameter 'url' or 'text' is required.")

        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,text/plain"
        }

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            if res.status_code >= 400:
                raise RuntimeError(f"Target URL returned HTTP error {res.status_code}")

            html = res.text

            # Extract title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else url

            # Strip non-content tags
            cleaned = re.sub(r"<(script|style|nav|footer|header|noscript)[^>]*>[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
            
            # Convert breaks/paragraphs to newlines
            cleaned = re.sub(r"<(br|p|div|h[1-6]|li)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
            
            # Strip all remaining tags
            text = re.sub(r"<[^>]+>", " ", cleaned)
            
            # Normalize whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            main_text = "\n".join(lines[:100]) # First 100 meaningful paragraphs
            
            max_chars = int(params.get("max_chars", 4000))
            if len(main_text) > max_chars:
                main_text = main_text[:max_chars] + "\n...[truncated]"

            return {
                "url": str(res.url),
                "title": title,
                "status_code": res.status_code,
                "content": main_text,
                "char_count": len(main_text)
            }

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        if action == "document_summarize":
            has_summary = bool(result.get("summary") or result.get("content"))
            char_count = result.get("char_count", 0)
            passed = has_summary and char_count > 0
            evidence = {
                "has_summary": has_summary,
                "summary_length": len(result.get("summary", "")),
                "char_count": char_count
            }
            return passed, evidence

        char_count = result.get("char_count", 0)
        passed = char_count > 50 and result.get("status_code") == 200
        evidence = {
            "url": result.get("url"),
            "status_code": result.get("status_code"),
            "extracted_length": char_count,
            "has_title": bool(result.get("title"))
        }
        return passed, evidence

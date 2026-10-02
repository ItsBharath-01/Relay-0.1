import re
from typing import Dict, Any, Optional, Tuple, List, Union
import httpx

from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)


class WebReaderTool(BaseTool):
    id = "web_reader"
    name = "Web Content Reader"
    tool_type = "api"
    provides = ["web_read", "document_summarize"]
    requires_connection = None
    required_permissions = []

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="web_read",
                capability_id="web_read",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="url",
                required_permission=None,
                param_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target webpage URL to read"},
                        "max_chars": {"type": "integer", "description": "Maximum characters to extract", "default": 4000}
                    },
                    "required": ["url"]
                },
                supports_idempotency_key=False
            ),
            ActionSpec(
                action="document_summarize",
                capability_id="document_summarize",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="text",
                required_permission=None,
                param_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text content to summarize"},
                        "content": {"type": "string", "description": "Alternative text content to summarize"}
                    }
                },
                supports_idempotency_key=False
            )
        ]

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        return True, "Web reader is available"

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        if action == "document_summarize" or (not params.get("url") and (params.get("text") or params.get("content"))):
            text = params.get("text") or params.get("content") or ""
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            summary_text = "\n".join(lines[:15]) if lines else "Summary completed."
            return ToolResult(
                status="success",
                data={
                    "summary": summary_text,
                    "content": text,
                    "char_count": len(text)
                },
                side_effect_state="CONFIRMED"
            )

        url = params.get("url", "").strip()
        if not url:
            raise ValueError("Parameter 'url' or 'text' is required.")

        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,text/plain"
        }
        from app.security.ssrf import SafeHTTPClient, SSRFError
        try:
            res = await SafeHTTPClient.get(url, headers=headers, timeout=20.0)
        except SSRFError as se:
            raise ValueError(f"URL blocked due to SSRF policy: {se}")

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
        main_text = "\n".join(lines[:100])

        max_chars = int(params.get("max_chars", 4000))
        if len(main_text) > max_chars:
            main_text = main_text[:max_chars] + "\n...[truncated]"

        return ToolResult(
            status="success",
            data={
                "url": str(res.url),
                "title": title,
                "status_code": res.status_code,
                "content": main_text,
                "char_count": len(main_text)
            },
            side_effect_state="CONFIRMED"
        )

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Union[ToolResult, Dict[str, Any]],
        ctx: ExecutionContext
    ) -> VerificationOutcome:
        if action == "document_summarize":
            has_summary = bool(result.get("summary") or result.get("content"))
            char_count = result.get("char_count", 0)
            passed = has_summary and char_count > 0
            evidence = {
                "has_summary": has_summary,
                "summary_length": len(result.get("summary", "") or ""),
                "char_count": char_count
            }
            return VerificationOutcome(
                result="passed" if passed else "failed",
                evidence=evidence,
                reason="Summary text verified" if passed else "Missing summary"
            )

        char_count = result.get("char_count", 0)
        status_code = result.get("status_code")
        passed = char_count > 50 and status_code == 200
        evidence = {
            "url": result.get("url"),
            "status_code": status_code,
            "extracted_length": char_count,
            "has_title": bool(result.get("title"))
        }
        return VerificationOutcome(
            result="passed" if passed else "failed",
            evidence=evidence,
            reason="Webpage content successfully extracted" if passed else "Content too short or non-200 status"
        )

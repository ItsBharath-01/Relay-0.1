from typing import Dict, Any, Optional, Tuple, List, Union
from app.tools.registry.base import (
    BaseTool,
    ActionSpec,
    EffectClass,
    ExecutionContext,
    ToolResult,
    VerificationOutcome,
)


class PlaywrightBrowserTool(BaseTool):
    id = "playwright_browser"
    name = "Playwright Headless Browser"
    tool_type = "browser"
    provides = ["browser_navigate", "web_read"]
    requires_connection = "browser"
    required_permissions = ["navigate", "extract"]

    def describe_actions(self) -> List[ActionSpec]:
        return [
            ActionSpec(
                action="browser_navigate",
                capability_id="browser_navigate",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="url",
                required_permission="navigate",
                param_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target webpage URL to navigate to"},
                        "selector": {"type": "string", "description": "Optional CSS selector to extract"},
                        "max_chars": {"type": "integer", "description": "Maximum characters to extract", "default": 4000}
                    },
                    "required": ["url"]
                },
                supports_idempotency_key=False
            ),
            ActionSpec(
                action="web_read",
                capability_id="web_read",
                effect_class=EffectClass.READ_ONLY,
                reversible=False,
                target_param="url",
                required_permission="extract",
                param_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target webpage URL to read"},
                        "selector": {"type": "string", "description": "Optional CSS selector to extract"},
                        "max_chars": {"type": "integer", "description": "Maximum characters to extract", "default": 4000}
                    },
                    "required": ["url"]
                },
                supports_idempotency_key=False
            )
        ]

    async def _launch_browser(self, p):
        """Launches headless Chromium using installed Chrome, Edge, or bundled chromium."""
        for channel in ["chrome", "msedge", None]:
            try:
                if channel:
                    return await p.chromium.launch(headless=True, channel=channel)
                else:
                    return await p.chromium.launch(headless=True)
            except Exception:
                continue
        raise RuntimeError("No supported Chromium/Chrome/Edge browser executable found on system.")

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                b = await self._launch_browser(p)
                await b.close()
            return True, "Playwright browser automation is ready"
        except Exception as e:
            return False, f"Playwright not initialized: {str(e)}"

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        ctx: ExecutionContext
    ) -> ToolResult:
        url = params.get("url", "").strip()
        if not url:
            raise ValueError("Parameter 'url' is required for browser navigation.")

        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        from app.security.ssrf import validate_and_resolve_url, SSRFError
        try:
            validate_and_resolve_url(url)
        except SSRFError as se:
            raise ValueError(f"Browser navigation blocked due to SSRF policy: {se}")

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await self._launch_browser(p)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                status_code = response.status if response else 200

                title = await page.title()
                
                selector = params.get("selector")
                if selector:
                    element = await page.query_selector(selector)
                    text_content = await element.inner_text() if element else ""
                else:
                    text_content = await page.evaluate("() => document.body.innerText")

                max_chars = int(params.get("max_chars", 4000))
                clean_text = text_content[:max_chars] if text_content else ""

                return ToolResult(
                    status="success",
                    data={
                        "action": action,
                        "url": page.url,
                        "title": title,
                        "status_code": status_code,
                        "content": clean_text,
                        "char_count": len(clean_text)
                    },
                    side_effect_state="CONFIRMED"
                )
            finally:
                await browser.close()

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Union[ToolResult, Dict[str, Any]],
        ctx: ExecutionContext
    ) -> VerificationOutcome:
        status = result.get("status_code", 0)
        char_count = result.get("char_count", 0)
        has_content = char_count > 0
        passed = (status < 400 and has_content)
        evidence = {
            "final_url": result.get("url"),
            "status_code": status,
            "title": result.get("title"),
            "char_count": char_count
        }
        return VerificationOutcome(
            result="passed" if passed else "failed",
            evidence=evidence,
            reason="Browser navigated and page content extracted" if passed else f"Failed with status {status}"
        )

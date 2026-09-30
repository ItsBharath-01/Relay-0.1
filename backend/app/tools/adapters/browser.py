from typing import Dict, Any, Optional, Tuple
from app.tools.registry.base import BaseTool

class PlaywrightBrowserTool(BaseTool):
    id = "playwright_browser"
    name = "Playwright Headless Browser"
    tool_type = "browser"
    provides = ["browser_navigate", "web_read"]
    requires_connection = "browser"
    required_permissions = ["navigate", "extract"]

    async def health_check(self, credentials: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        try:
            from playwright.async_api import async_playwright
            return True, "Playwright browser automation is ready"
        except Exception as e:
            return False, f"Playwright not initialized: {str(e)}"

    async def execute(
        self,
        action: str,
        params: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Dict[str, Any]:
        url = params.get("url", "").strip()
        if not url:
            raise ValueError("Parameter 'url' is required for browser navigation.")

        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Launch headless chromium
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # Navigate to target page
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                status_code = response.status if response else 200

                # Extract title and text
                title = await page.title()
                
                # If specific selector requested, extract text from it
                selector = params.get("selector")
                if selector:
                    element = await page.query_selector(selector)
                    text_content = await element.inner_text() if element else ""
                else:
                    # Get body text
                    text_content = await page.evaluate("() => document.body.innerText")

                max_chars = int(params.get("max_chars", 4000))
                clean_text = text_content[:max_chars] if text_content else ""

                return {
                    "action": action,
                    "url": page.url,
                    "title": title,
                    "status_code": status_code,
                    "content": clean_text,
                    "char_count": len(clean_text)
                }
            finally:
                await browser.close()

    async def verify(
        self,
        action: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
        credentials: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        status = result.get("status_code", 0)
        has_content = result.get("char_count", 0) > 0
        passed = status < 400 and has_content
        evidence = {
            "final_url": result.get("url"),
            "status_code": status,
            "title": result.get("title"),
            "char_count": result.get("char_count")
        }
        return passed, evidence

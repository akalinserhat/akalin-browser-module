"""
akalin-browser-module - Playwright Headless Chromium Sürücüsü (playwright_driver.py)
Tam JavaScript yürütme, tıklama, form doldurma ve DOM ref etiketleme motoru.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("playwright_driver")

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""

DOM_REF_LABEL_SCRIPT = """
(() => {
    let currentRef = 1;
    const elements = [];
    const interactiveSelectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [onclick]';
    const nodes = document.querySelectorAll(interactiveSelectors);

    for (const node of nodes) {
        // Görünürlük denetimi
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            continue;
        }
        if (rect.width === 0 && rect.height === 0) {
            continue;
        }

        const ref = currentRef++;
        node.setAttribute('data-tp-ref', String(ref));

        const tag = node.tagName.toLowerCase();
        const role = node.getAttribute('role') || tag;
        const type = node.getAttribute('type') || '';
        const placeholder = node.getAttribute('placeholder') || '';
        const ariaLabel = node.getAttribute('aria-label') || '';
        const textContent = (node.innerText || node.textContent || '').trim().replace(/\\s+/g, ' ');
        const label = textContent || placeholder || ariaLabel || node.value || tag;

        elements.push({
            ref: ref,
            tag: tag,
            role: role,
            type: type,
            text: label.substring(0, 100)
        });
    }

    // Basit görünür metin çıkarma
    const bodyClone = document.body.cloneNode(true);
    // script ve style'ları temizle
    const badNodes = bodyClone.querySelectorAll('script, style, noscript, svg');
    badNodes.forEach(n => n.remove());

    const pageText = (bodyClone.innerText || bodyClone.textContent || '').replace(/\\s+/g, ' ').trim();

    return {
        title: document.title || '',
        elements: elements,
        pageText: pageText
    };
})();
"""


class PlaywrightSession:
    def __init__(self, context: Any, page: Any, proxy_endpoint: Optional[str] = None) -> None:
        self.context = context
        self.page = page
        self.proxy_endpoint = proxy_endpoint
        self.last_active_at = time.time()


class PlaywrightDriver:
    """Docker konteyneri içinde çalışan başsız Playwright Chromium yöneticisi."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._sessions: Dict[str, PlaywrightSession] = {}
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> None:
        if self._browser:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-gpu",
            ],
        )
        logger.info("Playwright Chromium başlatıldı.")

    async def get_or_create_page(
        self,
        conversation_id: str,
        proxy_url: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Any:
        async with self._lock:
            await self._ensure_browser()
            if conversation_id in self._sessions:
                sess = self._sessions[conversation_id]
                sess.last_active_at = time.time()
                return sess.page

            context_opts: Dict[str, Any] = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            }
            if proxy_url:
                context_opts["proxy"] = {"server": proxy_url}

            context = await self._browser.new_context(**context_opts)
            await context.add_init_script(STEALTH_SCRIPT)
            page = await context.new_page()

            session = PlaywrightSession(context, page, proxy_endpoint=proxy_url)
            self._sessions[conversation_id] = session
            return page

    async def navigate(
        self,
        conversation_id: str,
        url: str,
        proxy_url: Optional[str] = None,
        timeout_ms: int = 25000,
    ) -> Dict[str, Any]:
        page = await self.get_or_create_page(conversation_id, proxy_url=proxy_url)
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass

        return await self.take_snapshot(conversation_id)

    async def take_snapshot(self, conversation_id: str) -> Dict[str, Any]:
        if conversation_id not in self._sessions:
            raise RuntimeError(f"Aktif oturum bulunamadı: {conversation_id}")
        page = self._sessions[conversation_id].page

        data = await page.evaluate(DOM_REF_LABEL_SCRIPT)
        elements = data.get("elements") or []
        page_text = data.get("pageText") or ""
        title = data.get("title") or ""

        # Numaralı etkileşimli öğeler özeti
        elements_summary = []
        for el in elements[:100]:
            type_str = f"[{el.get('type')}]" if el.get("type") else ""
            elements_summary.append(f"[{el['ref']}] {el['tag']}{type_str} \"{el['text']}\"")

        combined = "ETKİLEŞİMLİ ÖĞELER:\n" + "\n".join(elements_summary) + "\n\nSAYFA METNİ:\n" + page_text

        return {
            "url": page.url,
            "title": title,
            "snapshot_text": combined,
            "interactive_elements": elements,
        }

    async def click(self, conversation_id: str, ref: int) -> Dict[str, Any]:
        if conversation_id not in self._sessions:
            raise RuntimeError(f"Aktif oturum bulunamadı: {conversation_id}")
        page = self._sessions[conversation_id].page

        selector = f'[data-tp-ref="{ref}"]'
        locator = page.locator(selector).first
        await locator.click(timeout=8000)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:
            pass

        return await self.take_snapshot(conversation_id)

    async def type_text(self, conversation_id: str, ref: int, text: str, press_enter: bool = False) -> Dict[str, Any]:
        if conversation_id not in self._sessions:
            raise RuntimeError(f"Aktif oturum bulunamadı: {conversation_id}")
        page = self._sessions[conversation_id].page

        selector = f'[data-tp-ref="{ref}"]'
        locator = page.locator(selector).first
        await locator.fill(text, timeout=8000)
        if press_enter:
            await locator.press("Enter")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass

        return await self.take_snapshot(conversation_id)

    async def scroll(self, conversation_id: str, direction: str = "down") -> Dict[str, Any]:
        if conversation_id not in self._sessions:
            raise RuntimeError(f"Aktif oturum bulunamadı: {conversation_id}")
        page = self._sessions[conversation_id].page
        delta = 600 if direction == "down" else -600
        await page.evaluate(f"window.scrollBy(0, {delta});")
        await asyncio.sleep(0.3)
        return await self.take_snapshot(conversation_id)

    async def go_back(self, conversation_id: str) -> Dict[str, Any]:
        if conversation_id not in self._sessions:
            raise RuntimeError(f"Aktif oturum bulunamadı: {conversation_id}")
        page = self._sessions[conversation_id].page
        await page.go_back(wait_until="domcontentloaded", timeout=8000)
        return await self.take_snapshot(conversation_id)

    async def close_session(self, conversation_id: str) -> bool:
        async with self._lock:
            if conversation_id in self._sessions:
                sess = self._sessions.pop(conversation_id)
                try:
                    await sess.context.close()
                except Exception:
                    pass
                return True
            return False

    async def shutdown(self) -> None:
        async with self._lock:
            for sess in list(self._sessions.values()):
                try:
                    await sess.context.close()
                except Exception:
                    pass
            self._sessions.clear()
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None


playwright_driver = PlaywrightDriver()

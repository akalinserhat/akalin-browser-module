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
        self.captured_requests: List[Dict[str, Any]] = []
        self.captured_responses: List[Dict[str, Any]] = []


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

            async def _on_request(req: Any) -> None:
                try:
                    url = req.url
                    res_type = req.resource_type
                    if res_type in ("fetch", "xhr", "eventsource", "websocket") or any(
                        k in url for k in ("/_/", "/api/", "googleapis.com", "batchexecute", "StreamGenerate", "conversation", "backend-api")
                    ):
                        session.captured_requests.append({
                            "url": url,
                            "method": req.method,
                            "resource_type": res_type,
                            "headers": {
                                k: v for k, v in req.headers.items()
                                if k.lower() in ("content-type", "authorization", "x-goog-api-key", "x-same-domain", "accept")
                            },
                            "timestamp": time.time(),
                        })
                        if len(session.captured_requests) > 200:
                            session.captured_requests = session.captured_requests[-100:]
                except Exception:
                    pass

            async def _on_response(resp: Any) -> None:
                try:
                    url = resp.url
                    ip_addr = ""
                    port = None
                    try:
                        addr = await resp.server_addr()
                        if addr:
                            ip_addr = addr.get("ipAddress", "")
                            port = addr.get("port")
                    except Exception:
                        pass

                    content_type = resp.headers.get("content-type", "")
                    if (
                        any(k in url for k in ("/_/", "/api/", "googleapis.com", "batchexecute", "StreamGenerate", "conversation", "backend-api"))
                        or "json" in content_type
                        or "text/event-stream" in content_type
                    ):
                        session.captured_responses.append({
                            "url": url,
                            "status": resp.status,
                            "content_type": content_type,
                            "ip_address": ip_addr,
                            "port": port,
                            "timestamp": time.time(),
                        })
                        if len(session.captured_responses) > 200:
                            session.captured_responses = session.captured_responses[-100:]
                except Exception:
                    pass

            page.on("request", _on_request)
            page.on("response", _on_response)

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
            page = await self.get_or_create_page(conversation_id)
        else:
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

    async def inspect_page_apis_and_controls(self, conversation_id: str) -> Dict[str, Any]:
        """Sayfanın iletişim kurduğu API uç noktalarını, sunucu IP'lerini ve dinamik tarayıcı kontrollerini tespit eder."""
        if conversation_id not in self._sessions:
            raise RuntimeError(f"Aktif oturum bulunamadı: {conversation_id}")
        sess = self._sessions[conversation_id]
        page = sess.page
        context = sess.context

        js_script = """
        (() => {
            const result = {
                wiz_global_data: {},
                chat_inputs: [],
                title: document.title || '',
                url: window.location.href,
            };

            // Google WIZ_global_data (SNlM0e, FdrFJe vb.)
            if (window.WIZ_global_data && typeof window.WIZ_global_data === 'object') {
                const wiz = window.WIZ_global_data;
                const keys = ['SNlM0e', 'FdrFJe', 'oocL2f', 'cfb2h', 'qAS0ub', 'S06Grb', 'Wfd2x'];
                for (const k of keys) {
                    if (wiz[k]) {
                        result.wiz_global_data[k] = String(wiz[k]);
                    }
                }
            }

            // Aktif sohbet giriş kontrolleri
            const candidateSelectors = [
                'rich-textarea div[contenteditable="true"]',
                'div[contenteditable="true"]',
                'textarea#chat-input',
                '#prompt-textarea',
                'textarea[aria-label*="prompt" i]',
                'textarea[placeholder*="prompt" i]',
                'textarea',
                'div[role="textbox"]'
            ];
            for (const sel of candidateSelectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    for (const el of Array.from(els).slice(0, 3)) {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        const isVisible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                        result.chat_inputs.push({
                            selector: sel,
                            tagName: el.tagName.toLowerCase(),
                            isContentEditable: el.isContentEditable,
                            placeholder: el.getAttribute('placeholder') || el.getAttribute('aria-label') || '',
                            visible: isVisible,
                            ref: el.getAttribute('data-tp-ref') || null
                        });
                    }
                    break;
                }
            }

            return result;
        })();
        """
        js_data = await page.evaluate(js_script)

        # Çerezler (Cookies)
        cookies = await context.cookies()
        cookie_summary = [
            {"name": c.get("name"), "domain": c.get("domain"), "secure": c.get("secure"), "httpOnly": c.get("httpOnly")}
            for c in cookies
        ]

        # Yakalanan API Uç Noktaları ve IP Adresleri
        api_endpoints = []
        seen_urls = set()
        for resp in reversed(sess.captured_responses):
            u = resp.get("url", "")
            base_u = u.split("?")[0]
            if base_u not in seen_urls:
                seen_urls.add(base_u)
                api_endpoints.append({
                    "url": u,
                    "base_url": base_u,
                    "status": resp.get("status"),
                    "content_type": resp.get("content_type"),
                    "ip_address": resp.get("ip_address"),
                    "port": resp.get("port"),
                })

        title = js_data.get("title", "")
        current_url = page.url or js_data.get("url", "")
        is_auth_required = any(
            x in title.lower() or x in current_url.lower()
            for x in ["sign in", "login", "giriş yap", "oturum aç", "accounts.google.com"]
        )

        return {
            "url": current_url,
            "title": title,
            "is_auth_required": is_auth_required,
            "wiz_global_data": js_data.get("wiz_global_data", {}),
            "chat_inputs": js_data.get("chat_inputs", []),
            "api_endpoints": api_endpoints[:25],
            "total_captured_apis": len(api_endpoints),
            "cookies_count": len(cookies),
            "cookie_summary": cookie_summary[:10],
        }

    async def execute_prompt_and_capture_response(
        self,
        conversation_id: str,
        prompt_text: str,
        target_url: str = "https://gemini.google.com/app",
        proxy_url: Optional[str] = None,
        timeout_ms: int = 25000,
    ) -> Dict[str, Any]:
        """
        LLM web sayfasına hızlı biçimde prompt gönderir ve dönen cevabı yakalar.
        Dinamik kontrolleri (WIZ_global_data, input seçicileri, API endpoints) inceler.
        """
        page = await self.get_or_create_page(conversation_id, proxy_url=proxy_url)
        sess = self._sessions[conversation_id]

        # Sayfa henüz yüklenmediyse git
        if not page.url or page.url == "about:blank" or not page.url.startswith("http"):
            await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass

        # Sayfa kontrollerini ve API uç noktalarını incele
        inspection = await self.inspect_page_apis_and_controls(conversation_id)

        title = inspection.get("title", "")
        current_url = inspection.get("url", "")
        is_auth_required = inspection.get("is_auth_required", False)

        # Eğer oturum açma engeli varsa, tespit edilen API'ler ve dinamik verilerle birlikte bildir
        if is_auth_required:
            return {
                "success": False,
                "error": f"Sanal tarayıcı hedefinde ({target_url}) oturum açma veya kimlik doğrulama ekranı tespit edildi: '{title}'.",
                "requires_auth": True,
                "url": current_url,
                "title": title,
                "inspection": inspection,
            }

        # Aktif giriş alanını bul
        input_selector = None
        candidate_selectors = [
            "rich-textarea div[contenteditable='true']",
            "div.ql-editor[contenteditable='true']",
            "textarea#chat-input",
            "#prompt-textarea",
            "textarea[aria-label*='prompt' i]",
            "textarea[placeholder*='prompt' i]",
            "textarea",
            "div[role='textbox']",
        ]
        for sel in candidate_selectors:
            if await page.locator(sel).count() > 0:
                input_selector = sel
                break

        if not input_selector:
            snap = await self.take_snapshot(conversation_id)
            return {
                "success": False,
                "error": f"Sayfada aktif sohbet metin kutusu bulunamadı ({target_url}). Başlık: '{title}'",
                "inspection": inspection,
                "snapshot": snap.get("snapshot_text", "")[:400],
            }

        # Gönderim öncesinde mevcut asistan mesajlarının durumunu kaydet (Multi-turn izolasyonu)
        msg_candidates = [
            "message-content",
            ".model-response-text",
            ".ds-markdown",
            ".font-claude-message",
            'div[data-message-author-role="assistant"]',
            ".response-container",
        ]

        initial_counts: Dict[str, int] = {}
        initial_last_texts: Dict[str, str] = {}
        for sel in msg_candidates:
            loc = page.locator(sel)
            cnt = await loc.count()
            initial_counts[sel] = cnt
            if cnt > 0:
                try:
                    initial_last_texts[sel] = (await loc.last.inner_text()).strip()
                except Exception:
                    initial_last_texts[sel] = ""
            else:
                initial_last_texts[sel] = ""

        inp = page.locator(input_selector).first
        await inp.click()
        await asyncio.sleep(0.1)

        # Metni gir: contenteditable veya textarea
        is_content_editable = await inp.evaluate("el => el.isContentEditable")
        if is_content_editable:
            await page.evaluate(
                """([sel, text]) => {
                    const el = document.querySelector(sel);
                    if (el) {
                        el.focus();
                        el.textContent = '';
                        const p = document.createElement('p');
                        p.textContent = text;
                        el.appendChild(p);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""",
                [input_selector, prompt_text],
            )
        else:
            await inp.fill("")
            await inp.fill(prompt_text)

        await asyncio.sleep(0.2)

        # Gönder tetikle (Enter veya Gönder Butonu)
        send_btn_candidates = [
            "button[aria-label*='Send' i]",
            "button[aria-label*='Gönder' i]",
            "button.send-button",
            "div[role='button'][aria-label*='Send' i]",
            "div[role='button'][aria-label*='Gönder' i]",
        ]
        clicked_send = False
        for btn_sel in send_btn_candidates:
            btn = page.locator(btn_sel).first
            if await btn.count() > 0 and await btn.is_visible():
                is_disabled = await btn.get_attribute("disabled")
                aria_disabled = await btn.get_attribute("aria-disabled")
                if not is_disabled and aria_disabled != "true":
                    try:
                        await btn.click(timeout=3000)
                        clicked_send = True
                        break
                    except Exception:
                        pass

        if not clicked_send:
            await page.keyboard.press("Enter")

        # Yeni cevabın üretilmesini bekle (en fazla 35 saniye)
        response_text = ""
        start_wait = time.time()
        max_wait_sec = 35.0
        new_message_detected = False
        active_selector = None
        last_observed_text = ""
        stable_count = 0

        while time.time() - start_wait < max_wait_sec:
            await asyncio.sleep(0.8)

            # 1. Yeni yanıtın başlayıp başlamadığını denetle
            if not new_message_detected:
                for sel in msg_candidates:
                    loc = page.locator(sel)
                    cnt = await loc.count()
                    init_cnt = initial_counts.get(sel, 0)
                    init_text = initial_last_texts.get(sel, "")

                    if cnt > init_cnt:
                        new_message_detected = True
                        active_selector = sel
                        break
                    elif cnt > 0:
                        try:
                            cur_text = (await loc.last.inner_text()).strip()
                            if (init_cnt == 0 and len(cur_text) > 5) or (init_cnt > 0 and cur_text != init_text and len(cur_text) > 5):
                                new_message_detected = True
                                active_selector = sel
                                break
                        except Exception:
                            pass

            # 2. Yeni yanıt tespit edildiyse akışın tamamlanmasını bekle
            if new_message_detected and active_selector:
                loc = page.locator(active_selector)
                try:
                    current_text = (await loc.last.inner_text()).strip()
                except Exception:
                    current_text = ""

                if current_text and len(current_text) > 5:
                    if current_text == last_observed_text:
                        stable_count += 1
                        # Durdur butonu var mı kontrol et
                        stop_btn = page.locator("button[aria-label*='Stop' i], button[aria-label*='Durdur' i]")
                        is_still_generating = (await stop_btn.count() > 0 and await stop_btn.first.is_visible())

                        # En az 2 tur metin sabit kaldıysa ve durdur butonu kaybolduysa tamamlandı
                        if stable_count >= 2 and not is_still_generating:
                            response_text = current_text
                            break
                    else:
                        stable_count = 0
                        last_observed_text = current_text

            # Eğer 6. ve 12. saniyelerde henüz yeni mesaj başlamadıysa Enter'ı tekrar dene
            if not new_message_detected and int(time.time() - start_wait) in (6, 12):
                try:
                    await page.keyboard.press("Enter")
                except Exception:
                    pass

        if not response_text and new_message_detected and last_observed_text:
            response_text = last_observed_text

        # Tekrar en güncel API ve IP durumunu al
        post_inspection = await self.inspect_page_apis_and_controls(conversation_id)

        if not response_text:
            snap = await self.take_snapshot(conversation_id)
            response_text = snap.get("snapshot_text", "")

        return {
            "success": True,
            "text": response_text,
            "url": page.url,
            "title": title,
            "inspection": post_inspection,
        }

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

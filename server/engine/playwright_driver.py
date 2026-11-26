"""
akalin-browser-module - Playwright Headless Chromium Sürücüsü (playwright_driver.py)
Tam JavaScript yürütme, tıklama, form doldurma ve DOM ref etiketleme motoru.
"""

from __future__ import annotations
import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("playwright_driver")

BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_URL_FRAGMENTS = (
    "googletagmanager.com",
    "google-analytics.com",
    "doubleclick.net",
    "datadoghq.com",
    "sentry.io",
    "segment.io",
    "facebook.net",
    "hotjar.com",
)

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


DOM_TO_MARKDOWN_JS = """
(rootEl) => {
    if (!rootEl) return '';
    const SKIP_TAGS = new Set(['BUTTON', 'SVG', 'SCRIPT', 'STYLE', 'NOSCRIPT', 'NAV', 'ASIDE', 'FORM', 'TEXTAREA', 'INPUT']);
    const UI_LINE_PATTERNS = [
        /^worked\\s+for\\s+\\d+\\s*[smh]/i,
        /^copy(\\s+response)?$/i,
        /^share$/i,
        /^log\\s*in$/i,
        /^sign\\s*up/i,
        /^chatgpt\\s+(is\\s+ai\\s+and\\s+)?can\\s+make\\s+mistakes/i,
    ];

    function cleanCell(str) {
        return (str || '').replace(/\\s+/g, ' ').replace(/\\|/g, '/').trim();
    }

    function serializeTable(tbl) {
        const rows = Array.from(tbl.querySelectorAll('tr'));
        if (!rows.length) return '';
        const matrix = rows.map(tr =>
            Array.from(tr.querySelectorAll('th, td')).map(cell => cleanCell(cell.innerText || cell.textContent))
        ).filter(r => r.length > 0 && r.some(Boolean));
        if (!matrix.length) return '';
        const colCount = Math.max(...matrix.map(r => r.length));
        const norm = matrix.map(r => {
            const copy = r.slice();
            while (copy.length < colCount) copy.push('');
            return copy;
        });
        const header = '| ' + norm[0].join(' | ') + ' |';
        const sep = '| ' + norm[0].map(() => '---').join(' | ') + ' |';
        const body = norm.slice(1).map(r => '| ' + r.join(' | ') + ' |');
        return '\\n\\n' + [header, sep, ...body].join('\\n') + '\\n\\n';
    }

    function walk(node, listDepth) {
        if (!node) return '';
        if (node.nodeType === Node.TEXT_NODE) {
            return (node.nodeValue || '').replace(/\\r/g, '');
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return '';
        const tag = node.tagName;
        if (SKIP_TAGS.has(tag)) return '';
        if (node.getAttribute && (node.getAttribute('aria-hidden') === 'true' || node.getAttribute('role') === 'navigation')) {
            return '';
        }

        if (tag === 'TABLE') return serializeTable(node);
        if (tag === 'BR') return '\\n';
        if (tag === 'HR') return '\\n\\n---\\n\\n';

        if (tag === 'PRE') {
            const codeEl = node.querySelector('code');
            const langMatch = codeEl && (codeEl.className || '').match(/language-([\\w+-]+)/);
            const lang = langMatch ? langMatch[1] : '';
            const rawCode = (codeEl ? codeEl.textContent : node.textContent) || '';
            return '\\n\\n```' + lang + '\\n' + rawCode.trim() + '\\n```\\n\\n';
        }

        const inner = Array.from(node.childNodes).map(c => walk(c, listDepth)).join('');
        const trimmed = inner.trim();
        if (!trimmed) return '';
        if (UI_LINE_PATTERNS.some(re => re.test(trimmed))) return '';

        if (tag === 'CODE') return '`' + trimmed + '`';
        if (tag === 'STRONG' || tag === 'B') return '**' + trimmed + '**';
        if (tag === 'EM' || tag === 'I') return '*' + trimmed + '*';
        if (tag === 'A') {
            const href = node.getAttribute('href') || '';
            return href && href.startsWith('http') ? '[' + trimmed + '](' + href + ')' : trimmed;
        }
        if (tag === 'H1') return '\\n\\n# ' + trimmed + '\\n\\n';
        if (tag === 'H2') return '\\n\\n## ' + trimmed + '\\n\\n';
        if (tag === 'H3') return '\\n\\n### ' + trimmed + '\\n\\n';
        if (tag === 'H4' || tag === 'H5' || tag === 'H6') return '\\n\\n#### ' + trimmed + '\\n\\n';
        if (tag === 'BLOCKQUOTE') {
            return '\\n\\n' + trimmed.split('\\n').map(l => '> ' + l).join('\\n') + '\\n\\n';
        }
        if (tag === 'UL') {
            const items = Array.from(node.children).filter(c => c.tagName === 'LI');
            const out = items.map(li => {
                const liText = Array.from(li.childNodes).map(c => walk(c, listDepth + 1)).join('').trim();
                return liText ? '  '.repeat(listDepth) + '- ' + liText.replace(/\\n{2,}/g, '\\n' + '  '.repeat(listDepth + 1)) : '';
            }).filter(Boolean).join('\\n');
            return out ? '\\n\\n' + out + '\\n\\n' : '';
        }
        if (tag === 'OL') {
            const items = Array.from(node.children).filter(c => c.tagName === 'LI');
            const out = items.map((li, idx) => {
                const liText = Array.from(li.childNodes).map(c => walk(c, listDepth + 1)).join('').trim();
                return liText ? '  '.repeat(listDepth) + (idx + 1) + '. ' + liText.replace(/\\n{2,}/g, '\\n' + '  '.repeat(listDepth + 1)) : '';
            }).filter(Boolean).join('\\n');
            return out ? '\\n\\n' + out + '\\n\\n' : '';
        }
        if (tag === 'P') return '\\n\\n' + trimmed + '\\n\\n';
        if (tag === 'DIV' || tag === 'SECTION' || tag === 'ARTICLE') {
            return inner.includes('\\n') ? '\\n' + inner + '\\n' : inner + '\\n';
        }
        return inner;
    }

    const md = walk(rootEl, 0)
        .replace(/[ \\t]+\\n/g, '\\n')
        .replace(/\\n{3,}/g, '\\n\\n')
        .trim();
    return md;
}
"""


class PlaywrightSession:
    def __init__(
        self,
        context: Any,
        page: Any,
        proxy_endpoint: Optional[str] = None,
        proxy_node: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.context = context
        self.page = page
        self.proxy_endpoint = proxy_endpoint
        self.proxy_node = proxy_node
        self.created_at = time.time()
        self.last_active_at = self.created_at
        self.captured_requests: List[Dict[str, Any]] = []
        self.captured_responses: List[Dict[str, Any]] = []


class PlaywrightDriver:
    """Docker konteyneri içinde çalışan başsız Playwright Chromium yöneticisi."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._sessions: Dict[str, PlaywrightSession] = {}
        self._warm_sessions: Dict[str, List[PlaywrightSession]] = {}
        self._lock = asyncio.Lock()

    async def _attach_resource_blocker(self, page: Any) -> None:
        """Sayfa yüklemesini 2-3x hızlandırmak için görsel, font ve analitik isteklerini engeller."""
        async def _route_handler(route: Any) -> None:
            try:
                req = route.request
                if req.resource_type in BLOCKED_RESOURCE_TYPES:
                    await route.abort()
                    return
                url_lower = (req.url or "").lower()
                if any(frag in url_lower for frag in BLOCKED_URL_FRAGMENTS):
                    await route.abort()
                    return
            except Exception:
                pass
            try:
                await route.continue_()
            except Exception:
                pass

        try:
            await page.route("**/*", _route_handler)
        except Exception:
            pass

    WARM_SESSION_TTL_SEC: float = 900.0  # 15 dk: oturum/çerez bayatlamadan yenile

    async def _prune_expired_warm_sessions(self, target_url: str) -> None:
        """Süresi dolmuş veya kapanmış warm sekmeleri havuzdan temizler."""
        now = time.time()
        stale: List[PlaywrightSession] = []
        async with self._lock:
            pool = self._warm_sessions.get(target_url, [])
            kept: List[PlaywrightSession] = []
            for sess in pool:
                try:
                    is_dead = sess.page.is_closed() or (now - sess.created_at) > self.WARM_SESSION_TTL_SEC
                except Exception:
                    is_dead = True
                if is_dead:
                    stale.append(sess)
                else:
                    kept.append(sess)
            self._warm_sessions[target_url] = kept
        for sess in stale:
            try:
                await sess.context.close()
            except Exception:
                pass

    def warm_pool_stats(self) -> Dict[str, int]:
        """URL bazında hazır bekleyen sıcak sekme sayılarını döner."""
        return {url: len(pool) for url, pool in self._warm_sessions.items() if pool}

    async def peek_warm_proxy(
        self,
        target_url: str,
        exclude_proxy_ids: Optional[List[str]] = None,
    ) -> Optional[Tuple[Optional[str], Optional[Dict[str, Any]]]]:
        """Hedef URL için geçerli bir warm sekme varsa onun proxy bilgilerini döner."""
        await self._prune_expired_warm_sessions(target_url)
        excluded = set(str(x) for x in (exclude_proxy_ids or []))
        async with self._lock:
            pool = self._warm_sessions.get(target_url, [])
            for sess in pool:
                pid = str((sess.proxy_node or {}).get("id") or "")
                if pid and pid in excluded:
                    continue
                try:
                    if not sess.page.is_closed():
                        return (sess.proxy_endpoint, sess.proxy_node)
                except Exception:
                    continue
        return None

    async def prewarm_session(
        self,
        target_url: str,
        proxy_url: Optional[str] = None,
        max_warm_per_url: int = 2,
        proxy_node: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Arka planda belirtilen hedef URL için hazır (warm) bir tarayıcı sekmesi oluşturur."""
        if not target_url:
            return False
        await self._prune_expired_warm_sessions(target_url)
        async with self._lock:
            existing_warm = self._warm_sessions.get(target_url, [])
            if len(existing_warm) >= max_warm_per_url:
                return True
        warm_id = f"__warm_{int(time.time() * 1000)}"
        try:
            page = await self.get_or_create_page(warm_id, proxy_url=proxy_url, proxy_node=proxy_node)
            await page.goto(target_url, wait_until="domcontentloaded", timeout=12000)
            try:
                await page.wait_for_selector(
                    "#prompt-textarea, div#prompt-textarea[contenteditable='true'], rich-textarea div[contenteditable='true'], textarea, div[role='textbox']",
                    timeout=5000,
                )
            except Exception:
                pass
            await self._dismiss_blocking_overlays(page)
            async with self._lock:
                sess = self._sessions.pop(warm_id, None)
                if sess:
                    sess.proxy_node = proxy_node
                    sess.created_at = time.time()
                    sess.last_active_at = sess.created_at
                    self._warm_sessions.setdefault(target_url, []).append(sess)
                    logger.info(
                        f"[WarmPool] Hazır sekme eklendi: {target_url} (proxy={proxy_url or 'direct'}, havuz={len(self._warm_sessions[target_url])})"
                    )
                    return True
        except Exception as exc:
            await self.close_session(warm_id)
            logger.debug(f"[WarmPool] Ön ısıtma atlandı ({target_url}): {exc}")
        return False

    async def _pop_warm_session(
        self,
        conversation_id: str,
        target_url: str,
        proxy_url: Optional[str] = None,
        exclude_proxy_ids: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """Hedef URL için hazır (warm) sekme varsa doğrudan bu oturuma devreder (0ms sayfa yükleme)."""
        await self._prune_expired_warm_sessions(target_url)
        excluded = set(str(x) for x in (exclude_proxy_ids or []))
        async with self._lock:
            if conversation_id in self._sessions:
                return self._sessions[conversation_id].page
            pool = self._warm_sessions.get(target_url, [])
            for idx, sess in enumerate(pool):
                pid = str((sess.proxy_node or {}).get("id") or "")
                if pid and pid in excluded:
                    continue
                if proxy_url and sess.proxy_endpoint and sess.proxy_endpoint != proxy_url:
                    continue
                try:
                    if not sess.page.is_closed():
                        pool.pop(idx)
                        sess.last_active_at = time.time()
                        self._sessions[conversation_id] = sess
                        logger.info(
                            f"[WarmPool] Hazır sekme devredildi (0ms): {conversation_id} -> {target_url} (kalan={len(pool)})"
                        )
                        return sess.page
                except Exception:
                    pass
        return None

    @staticmethod
    async def _dismiss_blocking_overlays(page: Any) -> None:
        """Gemini/ChatGPT üzerinde giriş kutusunu engelleyen çerez, tanıtım veya cdk-overlay katmanlarını kapatır."""
        try:
            await page.evaluate(
                """() => {
                    const dismissTexts = [
                        'got it', 'anladım', 'no thanks', 'hayır', 'stay signed out',
                        'oturum açmadan', 'dismiss', 'kapat', 'close', 'accept all',
                        'tümünü kabul et', 'reject all', 'tümünü reddet', 'tamam', 'ok'
                    ];
                    const overlayRoots = document.querySelectorAll('.cdk-overlay-container, [role="dialog"], .banner-body');
                    for (const root of overlayRoots) {
                        const btns = root.querySelectorAll('button, [role="button"]');
                        for (const btn of btns) {
                            const txt = (btn.innerText || btn.getAttribute('aria-label') || '').trim().toLowerCase();
                            if (txt && dismissTexts.some(k => txt.includes(k))) {
                                btn.click();
                            }
                        }
                    }
                    // Hâlâ input alanını kapatan cdk-overlay/banner varsa tıklama engelini kaldır
                    const blockers = document.querySelectorAll('.cdk-overlay-backdrop, .cdk-overlay-container .banner-body');
                    for (const el of blockers) {
                        el.style.pointerEvents = 'none';
                    }
                }"""
            )
        except Exception:
            pass

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
        proxy_node: Optional[Dict[str, Any]] = None,
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
            await self._attach_resource_blocker(page)

            session = PlaywrightSession(
                context,
                page,
                proxy_endpoint=proxy_url,
                proxy_node=proxy_node,
            )

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
        timeout_ms: int = 12000,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        on_status: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        LLM web sayfasına hızlı biçimde prompt gönderir ve dönen cevabı gerçek Markdown
        yapısını koruyarak yakalar. `on_status` ile canlı aşama bilgisi, `on_delta` ile canlı akış verir.
        """
        async def _emit_status(stage: str, message: str) -> None:
            if on_status:
                try:
                    await on_status(stage, message)
                except Exception:
                    pass

        page = await self._pop_warm_session(conversation_id, target_url, proxy_url=proxy_url)
        used_warm = page is not None
        if page is None:
            await _emit_status("connect", f"Yeni sanal tarayıcı sekmesi açılıyor ({target_url})...")
            page = await self.get_or_create_page(conversation_id, proxy_url=proxy_url)
        else:
            await _emit_status("connect", f"Hazır (warm) tarayıcı sekmesi devralındı (0 ms) — {target_url}")

        candidate_selectors = [
            "#prompt-textarea",
            "div#prompt-textarea[contenteditable='true']",
            "rich-textarea div[contenteditable='true']",
            "div.ql-editor[contenteditable='true']",
            "textarea#chat-input",
            "textarea[aria-label*='prompt' i]",
            "textarea[placeholder*='prompt' i]",
            "textarea",
            "div[role='textbox']",
        ]

        # Sayfa henüz yüklenmediyse git ve networkidle yerine doğrudan giriş kutusunun hazır olmasını bekle
        is_gemini_target = "gemini.google.com" in (target_url or "").lower()
        if not page.url or page.url == "about:blank" or not page.url.startswith("http"):
            await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_selector(
                    ", ".join(candidate_selectors[:6]),
                    timeout=9000 if is_gemini_target else 5500,
                )
            except Exception:
                pass

        # Hızlı oturum/auth kontrolü (tam inspect yerine yalnızca başlık ve URL kontrolü)
        title = await page.title()
        current_url = page.url or target_url
        is_auth_required = any(
            x in title.lower() or x in current_url.lower()
            for x in ["sign in", "login", "giriş yap", "oturum aç", "accounts.google.com"]
        )

        # Eğer oturum açma engeli varsa, tespit edilen API'ler ve dinamik verilerle birlikte bildir
        if is_auth_required:
            inspection = await self.inspect_page_apis_and_controls(conversation_id)
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
        for sel in candidate_selectors:
            if await page.locator(sel).count() > 0:
                input_selector = sel
                break

        if not input_selector:
            inspection = await self.inspect_page_apis_and_controls(conversation_id)
            snap = await self.take_snapshot(conversation_id)
            return {
                "success": False,
                "error": f"Sayfada aktif sohbet metin kutusu bulunamadı ({target_url}). Başlık: '{title}'",
                "inspection": inspection,
                "snapshot": snap.get("snapshot_text", "")[:400],
            }

        # Gönderim öncesinde mevcut asistan mesajlarının durumunu kaydet (Site-özel kesin seçiciler; kullanıcı balonunu yakalamaz)
        if is_gemini_target:
            msg_candidates = [
                "model-response message-content .markdown",
                "model-response .model-response-text",
                "model-response message-content",
                "message-content .markdown",
                "message-content",
                ".model-response-text",
            ]
        elif "chatgpt.com" in (target_url or "").lower():
            msg_candidates = [
                '[data-message-author-role="assistant"] .markdown',
                'div[data-message-author-role="assistant"]',
                'article[data-testid^="conversation-turn"] .markdown',
                '[data-testid*="assistant" i]',
                "div.markdown.prose",
            ]
        else:
            msg_candidates = [
                '[data-message-author-role="assistant"] .markdown',
                'div[data-message-author-role="assistant"]',
                'article[data-testid^="conversation-turn"] .markdown',
                '[data-testid*="assistant" i]',
                "div.markdown.prose",
                "message-content",
                ".model-response-text",
                ".ds-markdown",
                ".font-claude-message",
            ]
        copy_response_selector = (
            "button[aria-label*='Copy response' i], "
            "button[data-testid='copy-turn-action-button'], "
            "button:has-text('Copy response')"
        )
        initial_copy_count = await page.locator(copy_response_selector).count()
        initial_url = (page.url or "").rstrip("/")

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

        await self._dismiss_blocking_overlays(page)
        inp = page.locator(input_selector).first
        try:
            await inp.click(timeout=3000)
        except Exception:
            await self._dismiss_blocking_overlays(page)
            try:
                await inp.click(force=True, timeout=2000)
            except Exception:
                await inp.evaluate("el => el.focus()")
        await asyncio.sleep(0.12)

        # Metni gir: ProseMirror / Quill / React uyumlu gerçek native insert_text kullan (çok satırlı promptlarda bile anlık ve güvenilir)
        is_content_editable = await inp.evaluate("el => el.isContentEditable")
        if is_content_editable:
            try:
                await page.keyboard.press("ControlOrMeta+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.insert_text(prompt_text)
            except Exception:
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

        await asyncio.sleep(0.25)

        # Gönder tetikle (Enter veya Gönder Butonu)
        send_btn_candidates = [
            "button[data-testid='send-button']",
            "button[data-testid='composer-submit-button']",
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
                        await btn.click(timeout=2500)
                        clicked_send = True
                        break
                    except Exception:
                        pass

        if not clicked_send:
            await page.keyboard.press("Enter")

        await _emit_status("submitted", "İstem hedef modele gönderildi, yanıt üretimi bekleniyor...")

        # Yeni cevabın üretilmesini hızlı poll (0.25s), canlı delta akışı ve fail-fast ile bekle
        response_text = ""
        start_wait = time.time()
        max_wait_sec = 120.0 if is_gemini_target else 60.0
        fail_fast_no_activity_sec = 15.0 if is_gemini_target else 11.0
        new_message_detected = False
        stream_started_announced = False
        active_selector = None
        last_observed_text = ""
        streamed_text = ""
        stable_count = 0
        retried_enter = False

        async def _is_generating() -> bool:
            """Herhangi bir görünür durdurma butonu veya üretim animasyonu aktif mi (yalnızca .first değil tüm eşleşmeler)."""
            try:
                return bool(
                    await page.evaluate(
                        """() => {
                            const sels = [
                                'button[data-testid="stop-button"]',
                                'button[aria-label*="Stop" i]',
                                'button[aria-label*="Durdur" i]',
                                'button.stop',
                                'button.send-button.stop',
                                'mat-icon[fonticon="stop"]',
                                '[data-mat-icon-name="stop"]',
                                'model-response mat-progress-spinner',
                                'model-response[aria-busy="true"]',
                                'model-response .avatar_spinner_animation',
                                'model-response .response-streaming',
                                'pending-response',
                                'infinite-progress-bar',
                                'bard-avatar[aria-busy="true"]'
                            ];
                            for (const sel of sels) {
                                const els = document.querySelectorAll(sel);
                                for (const el of els) {
                                    const r = el.getBoundingClientRect();
                                    const st = window.getComputedStyle(el);
                                    if (r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0') {
                                        return true;
                                    }
                                }
                            }
                            return false;
                        }"""
                    )
                )
            except Exception:
                return False

        async def _has_gemini_action_bar() -> bool:
            """Gemini Web'de son model-response altında kopyala/beğen aksiyon çubuğu oluştu mu?"""
            if not is_gemini_target:
                return True
            try:
                return bool(
                    await page.evaluate(
                        """() => {
                            const responses = document.querySelectorAll('model-response');
                            if (!responses.length) return false;
                            const last = responses[responses.length - 1];
                            const actionBtn = last.querySelector(
                                'button[aria-label*="Copy" i], button[aria-label*="Kopyala" i], copy-button, message-actions button'
                            );
                            if (!actionBtn) return false;
                            const r = actionBtn.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        }"""
                    )
                )
            except Exception:
                return False

        prompt_norm = " ".join((prompt_text or "").strip().lower().split())

        def _is_echo_or_chrome_noise(candidate_text: str) -> bool:
            """Kullanıcının kendi istemini (You said ...) veya Gemini alt menü/çöp metnini yanıt sanmayı engeller."""
            norm = " ".join((candidate_text or "").strip().lower().split())
            if not norm or len(norm) <= 3:
                return True
            if norm.startswith("#### you said") or norm.startswith("you said"):
                return True
            if prompt_norm and (norm == prompt_norm or (len(norm) <= len(prompt_norm) + 35 and prompt_norm in norm)):
                return True
            noise_only_markers = ("about gemini", "subscriptions", "for business")
            if all(m in norm for m in noise_only_markers) and len(norm) < len(prompt_norm) + 260:
                return True
            return False

        async def _extract_markdown_from_locator(locator: Any) -> str:
            try:
                md_res = await locator.evaluate(DOM_TO_MARKDOWN_JS)
                if isinstance(md_res, str) and md_res.strip():
                    return md_res.strip()
            except Exception:
                pass
            try:
                return (await locator.inner_text()).strip()
            except Exception:
                return ""

        while time.time() - start_wait < max_wait_sec:
            await asyncio.sleep(0.25)
            elapsed = time.time() - start_wait

            # 1. Yeni yanıtın başlayıp başlamadığını denetle
            if not new_message_detected:
                for sel in msg_candidates:
                    loc = page.locator(sel)
                    cnt = await loc.count()
                    init_cnt = initial_counts.get(sel, 0)
                    init_text = initial_last_texts.get(sel, "")

                    if cnt > init_cnt:
                        try:
                            probe_txt = (await loc.last.inner_text()).strip()
                        except Exception:
                            probe_txt = ""
                        if not _is_echo_or_chrome_noise(probe_txt):
                            new_message_detected = True
                            active_selector = sel
                            break
                    elif cnt > 0:
                        try:
                            cur_text = (await loc.last.inner_text()).strip()
                            if (
                                not _is_echo_or_chrome_noise(cur_text)
                                and (
                                    (init_cnt == 0 and len(cur_text) > 3)
                                    or (init_cnt > 0 and cur_text != init_text and len(cur_text) > 3)
                                )
                            ):
                                new_message_detected = True
                                active_selector = sel
                                break
                        except Exception:
                            pass

            # 2. Yeni yanıt tespit edildiyse DOM->Markdown ile canlı delta akıt ve tamamlanmayı algıla
            if new_message_detected and active_selector:
                if not stream_started_announced:
                    stream_started_announced = True
                    await _emit_status("streaming", "Model yanıt üretmeye başladı, Markdown yapısı aktarılıyor...")
                loc = page.locator(active_selector)
                current_text = await _extract_markdown_from_locator(loc.last)

                if current_text and not _is_echo_or_chrome_noise(current_text):
                    if on_delta:
                        # Satır tamamlanmadan (ör. yarım **kalın** veya `kod` etiketi) Markdown değişimi yüzünden
                        # startswith() bozulmasını önlemek için canlı akışta tamamlanan satır sonuna kadar gönder.
                        last_nl = current_text.rfind("\n")
                        if last_nl != -1:
                            stream_candidate = current_text[: last_nl + 1]
                        elif len(current_text) - len(streamed_text) >= 120:
                            last_sp = current_text.rfind(" ")
                            stream_candidate = (
                                current_text[: last_sp + 1]
                                if last_sp > len(streamed_text)
                                else current_text
                            )
                        else:
                            stream_candidate = ""

                        if stream_candidate and len(stream_candidate) > len(streamed_text):
                            if stream_candidate.startswith(streamed_text):
                                delta_piece = stream_candidate[len(streamed_text):]
                            else:
                                # DOM yeniden biçimlendirmesi durumunda ortak öneki bul, kalan metni asla düşürme
                                lcp = 0
                                limit = min(len(streamed_text), len(stream_candidate))
                                while lcp < limit and streamed_text[lcp] == stream_candidate[lcp]:
                                    lcp += 1
                                delta_piece = stream_candidate[lcp:]
                            if delta_piece:
                                streamed_text = stream_candidate
                                try:
                                    await on_delta(delta_piece)
                                except Exception:
                                    pass

                    if current_text == last_observed_text and len(current_text) > 3:
                        stable_count += 1
                        is_still_generating = await _is_generating()

                        # Gemini düşünme/proxy duraklamalarında erken kesmemek için aksiyon çubuğu varsa 12 tur (~3.0s),
                        # aksiyon çubuğu henüz görünmediyse 20 tur (~5.0s) bekle; diğer modellerde 4 tur (~1.0s).
                        if is_gemini_target:
                            has_actions = await _has_gemini_action_bar()
                            required_stable = 12 if has_actions else 20
                        else:
                            required_stable = 4
                        if stable_count >= required_stable and not is_still_generating:
                            response_text = current_text
                            break
                    else:
                        stable_count = 0
                        last_observed_text = current_text

            # 3. unauth-mweb / özel DOM fallback: "Copy response" butonu belirdiyse DOM'u doğrudan Markdown'a çevir!
            if not new_message_detected:
                copy_cnt = await page.locator(copy_response_selector).count()
                if copy_cnt > initial_copy_count:
                    is_still_generating = await _is_generating()
                    if not is_still_generating:
                        await _emit_status("streaming", "Yanıt tamamlandı, yapısal Markdown çıkarılıyor...")
                        extracted = await page.evaluate(
                            f"""() => {{
                                const toMd = {DOM_TO_MARKDOWN_JS};
                                const btns = Array.from(document.querySelectorAll(
                                    'button[aria-label*="Copy response" i], button[data-testid="copy-turn-action-button"], button'
                                )).filter(b => {{
                                    const al = (b.getAttribute('aria-label') || '').toLowerCase();
                                    const tx = (b.innerText || '').trim().toLowerCase();
                                    return al.includes('copy response') || tx === 'copy response';
                                }});
                                if (!btns.length) return '';
                                const lastBtn = btns[btns.length - 1];
                                let container = lastBtn.closest('model-response, article, [data-testid*="turn"], section, li');
                                if (container && container.tagName === 'MODEL-RESPONSE') {{
                                    const inner = container.querySelector('message-content .markdown, message-content, .model-response-text');
                                    if (inner) container = inner;
                                }}
                                if (!container) {{
                                    let cur = lastBtn.parentElement;
                                    for (let d = 0; d < 6 && cur; d++) {{
                                        const tLen = (cur.innerText || '').trim().length;
                                        if (tLen > 25 && cur.tagName !== 'BODY' && cur.tagName !== 'MAIN') {{
                                            container = cur;
                                            break;
                                        }}
                                        cur = cur.parentElement;
                                    }}
                                }}
                                if (!container) return '';
                                return toMd(container);
                            }}"""
                        )
                        if isinstance(extracted, str) and not _is_echo_or_chrome_noise(extracted):
                            response_text = extracted.strip()
                            break

                # 4. 3.5 sn geçtiyse ve hâlâ hareket yoksa Enter'ı 1 kez daha dene
                if not retried_enter and elapsed >= 3.5:
                    retried_enter = True
                    try:
                        await page.keyboard.press("Enter")
                    except Exception:
                        pass

                # 5. Fail-Fast: uzun süre ne mesaj başladı ne URL değişti ne de üretim var -> bozuk proxy'yi hemen ele
                if elapsed >= fail_fast_no_activity_sec:
                    is_still_generating = await _is_generating()
                    url_changed = (page.url or "").rstrip("/") != initial_url
                    if not is_still_generating and not url_changed:
                        break

        if not response_text and new_message_detected and last_observed_text:
            response_text = last_observed_text

        # Son parçayı da akıtmış ol
        if on_delta and response_text and len(response_text) > len(streamed_text):
            if response_text.startswith(streamed_text):
                tail = response_text[len(streamed_text):]
            else:
                lcp = 0
                limit = min(len(streamed_text), len(response_text))
                while lcp < limit and streamed_text[lcp] == response_text[lcp]:
                    lcp += 1
                tail = response_text[lcp:]
            if tail:
                streamed_text = response_text
                try:
                    await on_delta(tail)
                except Exception:
                    pass

        # Bir sonraki yeni sohbet için arka planda hazır sekme ısıt
        try:
            asyncio.create_task(self.prewarm_session(target_url, proxy_url=proxy_url))
        except Exception:
            pass

        # Tekrar en güncel API ve IP durumunu al
        post_inspection = await self.inspect_page_apis_and_controls(conversation_id)

        if not response_text or _is_echo_or_chrome_noise(response_text):
            # Eğer sayfa hâlâ boş açılış URL'sindeyse veya yanıt sadece istem yankısı/çöp ise asistan yanıtı oluşmamıştır
            if page.url.rstrip("/") == target_url.rstrip("/") or is_gemini_target:
                return {
                    "success": False,
                    "error": f"Sanal tarayıcıda geçerli bir asistan yanıtı oluşmadı ({target_url}).",
                    "url": page.url,
                    "title": post_inspection.get("title", title),
                    "inspection": post_inspection,
                }
            snap = await self.take_snapshot(conversation_id)
            response_text = snap.get("snapshot_text", "")

        return {
            "success": True,
            "text": response_text,
            "url": page.url,
            "title": post_inspection.get("title", title),
            "streamed_direct": bool(streamed_text),
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
            for pool in list(self._warm_sessions.values()):
                for sess in pool:
                    try:
                        await sess.context.close()
                    except Exception:
                        pass
            self._warm_sessions.clear()
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None


playwright_driver = PlaywrightDriver()

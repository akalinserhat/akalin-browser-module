"""
akalin-browser-module - Hibrit Yürütme Orkestratörü (hybrid_executor.py)
Hızlı HTTP okuma ve Playwright başsız Chromium etkileşimini dinamik olarak koordine eder.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from database.browser_postgres_db import browser_db
from engine.http_fetcher import http_fetcher
from engine.playwright_driver import playwright_driver
from engine.proxy_client import proxy_client
from engine.url_guard import url_guard

logger = logging.getLogger("hybrid_executor")


class HybridBrowserExecutor:
    """HTTP ve Chromium modları arasında akıllı hibrit yönlendirici."""

    async def execute(
        self,
        action: str,
        conversation_id: str,
        app_id: str = "",
        agent_id: str = "",
        url: Optional[str] = None,
        ref: Optional[int] = None,
        text: Optional[str] = None,
        direction: Optional[str] = "down",
        use_proxy: bool = False,
        force_chromium: bool = False,
        allow_private_networks: bool = False,
    ) -> Dict[str, Any]:
        start_time = time.time()
        proxy_node = None
        proxy_endpoint = None

        if use_proxy:
            proxy_node = proxy_client.get_rotating_proxy()
            if proxy_node:
                proxy_endpoint = f"{proxy_node.get('protocol', 'http')}://{proxy_node.get('endpoint')}"

        if action == "navigate":
            if not url:
                return {"error": "navigate eylemi için 'url' parametresi zorunludur."}

            valid, reason = url_guard.validate_url(url, allow_private=allow_private_networks)
            if not valid:
                return {"error": reason}

            # 1. Hızlı HTTP Okuma Denemesi (Eğer force_chromium istenmediyse)
            if not force_chromium:
                http_res = http_fetcher.fetch(url, proxy_url=proxy_endpoint)
                if not http_res.error and not http_res.requires_javascript and len(http_res.snapshot_text) > 200:
                    sess = browser_db.upsert_session(
                        conversation_id=conversation_id,
                        current_url=http_res.url,
                        current_title=http_res.title,
                        mode="http",
                        status="idle",
                        app_id=app_id,
                        agent_id=agent_id,
                        proxy_endpoint=proxy_endpoint or "",
                    )
                    browser_db.save_snapshot(
                        session_id=sess["id"],
                        url=http_res.url,
                        title=http_res.title,
                        snapshot_text=http_res.snapshot_text,
                        interactive_elements=http_res.interactive_elements,
                    )
                    if proxy_node:
                        proxy_client.report_outcome(proxy_node["id"], success=True, latency_ms=http_res.latency_ms)

                    return {
                        "session_id": sess["id"],
                        "conversation_id": conversation_id,
                        "mode": "http",
                        "url": http_res.url,
                        "title": http_res.title,
                        "snapshot_text": http_res.snapshot_text,
                        "interactive_elements": http_res.interactive_elements,
                        "latency_ms": int((time.time() - start_time) * 1000),
                    }

            # 2. Sayfa SPA/JS gerektiriyorsa veya force_chromium seçildiyse: Playwright Chromium
            try:
                pw_res = await playwright_driver.navigate(
                    conversation_id=conversation_id,
                    url=url,
                    proxy_url=proxy_endpoint,
                )
                sess = browser_db.upsert_session(
                    conversation_id=conversation_id,
                    current_url=pw_res["url"],
                    current_title=pw_res["title"],
                    mode="chromium",
                    status="busy",
                    app_id=app_id,
                    agent_id=agent_id,
                    proxy_endpoint=proxy_endpoint or "",
                )
                browser_db.save_snapshot(
                    session_id=sess["id"],
                    url=pw_res["url"],
                    title=pw_res["title"],
                    snapshot_text=pw_res["snapshot_text"],
                    interactive_elements=pw_res["interactive_elements"],
                )
                if proxy_node:
                    proxy_client.report_outcome(proxy_node["id"], success=True)

                return {
                    "session_id": sess["id"],
                    "conversation_id": conversation_id,
                    "mode": "chromium",
                    "url": pw_res["url"],
                    "title": pw_res["title"],
                    "snapshot_text": pw_res["snapshot_text"],
                    "interactive_elements": pw_res["interactive_elements"],
                    "latency_ms": int((time.time() - start_time) * 1000),
                }
            except Exception as exc:
                if proxy_node:
                    proxy_client.report_outcome(proxy_node["id"], success=False)
                return {"error": f"Chromium navigasyon hatası: {exc}"}

        elif action == "snapshot":
            # Mevcut sayfanın anlık görüntüsünü alma
            existing = browser_db.get_session_by_conversation(conversation_id)
            if not existing:
                return {"error": f"Konuşmaya ait açık bir tarayıcı oturumu bulunamadı ({conversation_id})."}

            if existing.get("mode") == "chromium":
                pw_res = await playwright_driver.take_snapshot(conversation_id)
                browser_db.save_snapshot(
                    session_id=existing["id"],
                    url=pw_res["url"],
                    title=pw_res["title"],
                    snapshot_text=pw_res["snapshot_text"],
                    interactive_elements=pw_res["interactive_elements"],
                )
                return {
                    "session_id": existing["id"],
                    "conversation_id": conversation_id,
                    "mode": "chromium",
                    "url": pw_res["url"],
                    "title": pw_res["title"],
                    "snapshot_text": pw_res["snapshot_text"],
                    "interactive_elements": pw_res["interactive_elements"],
                }
            else:
                # HTTP modunda tekrar fetch
                http_res = http_fetcher.fetch(existing.get("current_url", ""), proxy_url=existing.get("proxy_endpoint"))
                return {
                    "session_id": existing["id"],
                    "conversation_id": conversation_id,
                    "mode": "http",
                    "url": http_res.url,
                    "title": http_res.title,
                    "snapshot_text": http_res.snapshot_text,
                    "interactive_elements": http_res.interactive_elements,
                }

        elif action == "click":
            if ref is None:
                return {"error": "click eylemi için 'ref' parametresi zorunludur."}

            existing = browser_db.get_session_by_conversation(conversation_id)
            if not existing:
                return {"error": "Açık oturum bulunamadı, önce 'navigate' ile bir sayfa açmalısınız."}

            # Eğer oturum HTTP modundaysa, etkileşim için Chromium'a yükselt
            if existing.get("mode") != "chromium":
                await playwright_driver.navigate(
                    conversation_id=conversation_id,
                    url=existing.get("current_url", ""),
                    proxy_url=existing.get("proxy_endpoint"),
                )

            pw_res = await playwright_driver.click(conversation_id, int(ref))
            sess = browser_db.upsert_session(
                conversation_id=conversation_id,
                current_url=pw_res["url"],
                current_title=pw_res["title"],
                mode="chromium",
                status="busy",
            )
            browser_db.save_snapshot(
                session_id=sess["id"],
                url=pw_res["url"],
                title=pw_res["title"],
                snapshot_text=pw_res["snapshot_text"],
                interactive_elements=pw_res["interactive_elements"],
            )
            return {
                "session_id": sess["id"],
                "conversation_id": conversation_id,
                "mode": "chromium",
                "url": pw_res["url"],
                "title": pw_res["title"],
                "snapshot_text": pw_res["snapshot_text"],
                "interactive_elements": pw_res["interactive_elements"],
            }

        elif action == "type":
            if ref is None or text is None:
                return {"error": "type eylemi için 'ref' ve 'text' parametreleri zorunludur."}

            existing = browser_db.get_session_by_conversation(conversation_id)
            if not existing:
                return {"error": "Açık oturum bulunamadı, önce 'navigate' ile bir sayfa açmalısınız."}

            if existing.get("mode") != "chromium":
                await playwright_driver.navigate(
                    conversation_id=conversation_id,
                    url=existing.get("current_url", ""),
                    proxy_url=existing.get("proxy_endpoint"),
                )

            pw_res = await playwright_driver.type_text(conversation_id, int(ref), text)
            sess = browser_db.upsert_session(
                conversation_id=conversation_id,
                current_url=pw_res["url"],
                current_title=pw_res["title"],
                mode="chromium",
                status="busy",
            )
            return {
                "session_id": sess["id"],
                "conversation_id": conversation_id,
                "mode": "chromium",
                "url": pw_res["url"],
                "title": pw_res["title"],
                "snapshot_text": pw_res["snapshot_text"],
                "interactive_elements": pw_res["interactive_elements"],
            }

        elif action == "scroll":
            existing = browser_db.get_session_by_conversation(conversation_id)
            if not existing or existing.get("mode") != "chromium":
                return {"error": "Kaydırma (scroll) yalnızca aktif Chromium oturumlarında geçerlidir."}

            pw_res = await playwright_driver.scroll(conversation_id, direction=direction or "down")
            return {
                "session_id": existing["id"],
                "conversation_id": conversation_id,
                "mode": "chromium",
                "url": pw_res["url"],
                "title": pw_res["title"],
                "snapshot_text": pw_res["snapshot_text"],
                "interactive_elements": pw_res["interactive_elements"],
            }

        elif action == "back":
            existing = browser_db.get_session_by_conversation(conversation_id)
            if not existing or existing.get("mode") != "chromium":
                return {"error": "Geri gitme (back) yalnızca aktif Chromium oturumlarında geçerlidir."}

            pw_res = await playwright_driver.go_back(conversation_id)
            return {
                "session_id": existing["id"],
                "conversation_id": conversation_id,
                "mode": "chromium",
                "url": pw_res["url"],
                "title": pw_res["title"],
                "snapshot_text": pw_res["snapshot_text"],
                "interactive_elements": pw_res["interactive_elements"],
            }

        elif action == "close":
            await playwright_driver.close_session(conversation_id)
            existing = browser_db.get_session_by_conversation(conversation_id)
            if existing:
                browser_db.terminate_session(existing["id"])
            return {"status": "closed", "conversation_id": conversation_id}

        return {"error": f"Bilinmeyen tarayıcı eylemi: {action}"}


hybrid_executor = HybridBrowserExecutor()

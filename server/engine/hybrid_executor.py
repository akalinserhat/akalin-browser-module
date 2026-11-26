"""
akalin-browser-module - Hibrit Yürütme Orkestratörü (hybrid_executor.py)
Hızlı HTTP okuma ve Playwright başsız Chromium etkileşimini dinamik olarak koordine eder.
"""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from database.browser_postgres_db import browser_db
from engine.http_fetcher import http_fetcher
from engine.playwright_driver import playwright_driver
from engine.proxy_client import proxy_client
from engine.url_guard import url_guard

logger = logging.getLogger("hybrid_executor")


class HybridBrowserExecutor:
    """HTTP ve Chromium modları arasında akıllı hibrit yönlendirici."""

    async def prewarm_target_with_proxy(
        self,
        target_url: str,
        max_warm_per_url: int = 2,
        use_proxy: bool = True,
        max_attempts: int = 3,
    ) -> int:
        """Hedef LLM URL'si için çalışan bir proxy seçerek arka planda sıcak sekmeler hazırlar."""
        added = 0
        for _ in range(max_warm_per_url):
            stats = playwright_driver.warm_pool_stats()
            if stats.get(target_url, 0) >= max_warm_per_url:
                break
            for _attempt in range(max(1, max_attempts)):
                p_node = None
                p_endpoint = None
                if use_proxy:
                    p_node = await asyncio.to_thread(proxy_client.get_rotating_proxy, target_url)
                    if p_node and p_node.get("endpoint"):
                        p_endpoint = f"{p_node.get('protocol', 'http')}://{p_node.get('endpoint')}"
                ok = await playwright_driver.prewarm_session(
                    target_url=target_url,
                    proxy_url=p_endpoint,
                    max_warm_per_url=max_warm_per_url,
                    proxy_node=p_node,
                )
                if ok:
                    added += 1
                    break
        return added

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
        proxy_override: Optional[Dict[str, Any]] = None,
        exclude_proxy_ids: Optional[List[str]] = None,
        force_chromium: bool = False,
        allow_private_networks: bool = False,
        on_delta: Optional[Callable[[str], Awaitable[None]]] = None,
        on_status: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        proxy_node = None
        proxy_endpoint = None

        if use_proxy:
            if proxy_override and proxy_override.get("endpoint"):
                proxy_node = proxy_override
            elif action == "prompt_llm":
                target_for_warm = url or "https://gemini.google.com/app"
                # 1. Aktif oturum zaten açıksa onun proxy bilgisini koru
                active_sess = playwright_driver._sessions.get(conversation_id)
                if active_sess and active_sess.proxy_endpoint:
                    proxy_endpoint = active_sess.proxy_endpoint
                    proxy_node = active_sess.proxy_node
                else:
                    # 2. Hazır (warm) sekme varsa yeni rastgele proxy çekip sekmeyi çöpe atma
                    warm_hit = await playwright_driver.peek_warm_proxy(
                        target_for_warm,
                        exclude_proxy_ids=exclude_proxy_ids,
                    )
                    if warm_hit is not None:
                        proxy_endpoint, proxy_node = warm_hit
                    else:
                        proxy_node = await asyncio.to_thread(proxy_client.get_rotating_proxy, target_for_warm)
            else:
                proxy_node = await asyncio.to_thread(proxy_client.get_rotating_proxy, url)
            if not proxy_endpoint and proxy_node and proxy_node.get("endpoint"):
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

        elif action == "inspect_apis":
            target_url = url or "https://gemini.google.com/app"
            try:
                await playwright_driver.get_or_create_page(conversation_id, proxy_url=proxy_endpoint)
                pw_page = playwright_driver._sessions[conversation_id].page
                if not pw_page.url or pw_page.url == "about:blank" or not pw_page.url.startswith("http"):
                    await pw_page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                    try:
                        await pw_page.wait_for_load_state("networkidle", timeout=4000)
                    except Exception:
                        pass

                inspection = await playwright_driver.inspect_page_apis_and_controls(conversation_id)
                sess = browser_db.upsert_session(
                    conversation_id=conversation_id,
                    current_url=inspection.get("url", target_url),
                    current_title=inspection.get("title", ""),
                    mode="chromium",
                    status="idle",
                    app_id=app_id,
                    agent_id=agent_id,
                    proxy_endpoint=proxy_endpoint or "",
                )
                return {
                    "session_id": sess["id"],
                    "conversation_id": conversation_id,
                    "mode": "chromium",
                    "inspection": inspection,
                    "latency_ms": int((time.time() - start_time) * 1000),
                }
            except Exception as exc:
                return {"error": f"API inceleme hatası: {exc}"}

        elif action == "prompt_llm":
            if not text:
                return {"error": "prompt_llm eylemi için 'text' (istem) parametresi zorunludur."}
            target_url = url or "https://gemini.google.com/app"
            try:
                pw_res = await playwright_driver.execute_prompt_and_capture_response(
                    conversation_id=conversation_id,
                    prompt_text=text,
                    target_url=target_url,
                    proxy_url=proxy_endpoint,
                    on_delta=on_delta,
                    on_status=on_status,
                )
                if pw_res.get("error"):
                    err_str = str(pw_res.get("error"))
                    incident_res: Dict[str, Any] = {}
                    if proxy_node:
                        await playwright_driver.close_session(conversation_id)
                        incident_res = await asyncio.to_thread(
                            proxy_client.report_failure,
                            proxy_id=proxy_node.get("id"),
                            endpoint=proxy_node.get("endpoint"),
                            error_reason=err_str,
                            target_url=target_url,
                            exclude_ids=exclude_proxy_ids,
                        )
                    return {
                        "error": err_str,
                        "retryable_proxy_error": bool(use_proxy and not pw_res.get("requires_auth")),
                        "proxy_id": proxy_node.get("id") if proxy_node else None,
                        "proxy_endpoint": proxy_node.get("endpoint") if proxy_node else None,
                        "proxy_incident": incident_res,
                        "replacement_proxy": incident_res.get("replacement_proxy"),
                        **{k: v for k, v in pw_res.items() if k not in ("error", "success")},
                    }

                if proxy_node and proxy_node.get("id"):
                    # Tam LLM üretim süresini proxy ağ gecikmesi olarak yazma; arka planda domain başarısı bildir
                    asyncio.create_task(
                        asyncio.to_thread(
                            proxy_client.report_outcome,
                            proxy_node["id"],
                            True,
                            None,
                            3,
                            target_url,
                            False,
                        )
                    )
                sess = browser_db.upsert_session(
                    conversation_id=conversation_id,
                    current_url=pw_res.get("url", target_url),
                    current_title=pw_res.get("title", ""),
                    mode="chromium",
                    status="busy",
                    app_id=app_id,
                    agent_id=agent_id,
                    proxy_endpoint=proxy_endpoint or "",
                )
                try:
                    asyncio.create_task(
                        self.prewarm_target_with_proxy(
                            target_url=target_url,
                            max_warm_per_url=2,
                            use_proxy=use_proxy,
                        )
                    )
                except Exception:
                    pass
                return {
                    "session_id": sess["id"],
                    "conversation_id": conversation_id,
                    "mode": "chromium",
                    "proxy_id": proxy_node.get("id") if proxy_node else None,
                    "proxy_endpoint": proxy_node.get("endpoint") if proxy_node else None,
                    "latency_ms": int((time.time() - start_time) * 1000),
                    **pw_res,
                }
            except Exception as exc:
                err_str = str(exc)
                incident_res = {}
                await playwright_driver.close_session(conversation_id)
                if proxy_node:
                    incident_res = await asyncio.to_thread(
                        proxy_client.report_failure,
                        proxy_id=proxy_node.get("id"),
                        endpoint=proxy_node.get("endpoint"),
                        error_reason=err_str,
                        target_url=target_url,
                        exclude_ids=exclude_proxy_ids,
                    )
                return {
                    "error": f"Sanal tarayıcı LLM yürütme hatası ({target_url}): {err_str}",
                    "retryable_proxy_error": bool(use_proxy),
                    "proxy_id": proxy_node.get("id") if proxy_node else None,
                    "proxy_endpoint": proxy_node.get("endpoint") if proxy_node else None,
                    "proxy_incident": incident_res,
                    "replacement_proxy": incident_res.get("replacement_proxy"),
                }

        elif action == "close":
            await playwright_driver.close_session(conversation_id)
            existing = browser_db.get_session_by_conversation(conversation_id)
            if existing:
                browser_db.terminate_session(existing["id"])
            return {"status": "closed", "conversation_id": conversation_id}

        return {"error": f"Bilinmeyen tarayıcı eylemi: {action}"}


hybrid_executor = HybridBrowserExecutor()

"""
akalin-browser-module - Sanal Tarayıcı Arka Plan Motoru REST API (main.py)
"""

from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database.browser_postgres_db import browser_db
from engine.hybrid_executor import hybrid_executor
from engine.playwright_driver import playwright_driver


DEFAULT_WARM_URLS = [
    u.strip()
    for u in os.getenv(
        "BROWSER_WARM_URLS",
        "https://chatgpt.com/,https://gemini.google.com/app,https://claude.ai/new,https://chat.deepseek.com/",
    ).split(",")
    if u.strip()
]
WARM_POOL_PER_URL = max(1, int(os.getenv("BROWSER_WARM_POOL_SIZE", "1")))
WARM_REFRESH_INTERVAL_SEC = max(30, int(os.getenv("BROWSER_WARM_REFRESH_SEC", "60")))


async def _warm_pool_maintainer() -> None:
    """Arka planda tüm hedef web LLM modelleri (ChatGPT Web, Gemini Web vb.) için en az 1 hazır sekme tutar."""
    if WARM_POOL_PER_URL <= 0 or not DEFAULT_WARM_URLS:
        return
    await asyncio.sleep(1.0)
    while True:
        await asyncio.gather(
            *(
                hybrid_executor.prewarm_target_with_proxy(
                    target_url=target_url,
                    max_warm_per_url=WARM_POOL_PER_URL,
                    use_proxy=True,
                )
                for target_url in DEFAULT_WARM_URLS
            ),
            return_exceptions=True,
        )
        await asyncio.sleep(WARM_REFRESH_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm_task = asyncio.create_task(_warm_pool_maintainer())
    try:
        yield
    finally:
        warm_task.cancel()
        try:
            await warm_task
        except asyncio.CancelledError:
            pass
        await playwright_driver.shutdown()


app = FastAPI(
    title="Akalin Hybrid Virtual Browser Service",
    description="AI Ajanları için HTTP ve Playwright Hibrit Sanal Tarayıcı Motoru",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExecuteActionRequest(BaseModel):
    action: str = Field(..., description="navigate, snapshot, click, type, scroll, back, inspect_apis, prompt_llm, close")
    conversation_id: str = Field(..., description="Ajan konuşma veya oturum kimliği")
    app_id: str = Field("", description="Uygulama kimliği")
    agent_id: str = Field("", description="Ajan kodu")
    url: Optional[str] = Field(None, description="Açılacak web adresi")
    ref: Optional[int] = Field(None, description="Tıklanacak veya yazılacak öğe ref numarası")
    text: Optional[str] = Field(None, description="Yazılacak metin")
    direction: Optional[str] = Field("down", description="Kaydırma yönü: up veya down")
    use_proxy: bool = Field(False, description="akalin-proxy-service üzerinden proxy kullanılsın mı?")
    proxy_override: Optional[Dict[str, Any]] = Field(None, description="Belirli bir yedek proxy düğümü (id, protocol, endpoint)")
    exclude_proxy_ids: Optional[List[str]] = Field(None, description="Önceki başarısız denemelerde kullanılan proxy ID listesi")
    force_chromium: bool = Field(False, description="Doğrudan Chromium açılsın mı?")
    allow_private_networks: bool = Field(False, description="İç ağlara izin verilsin mi?")


class PrewarmRequest(BaseModel):
    url: str = Field(..., description="Isıtılacak hedef web URL")
    use_proxy: bool = Field(True, description="Proxy havuzu üzerinden ısıtma yapılsın mı?")
    min_warm: int = Field(1, ge=1, le=5, description="Hedef URL için tutulacak en az sıcak sekme sayısı")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "akalin-browser-module",
        "warm_pool": playwright_driver.warm_pool_stats(),
    }


@app.post("/api/browser/prewarm")
async def prewarm_browser_target(req: PrewarmRequest) -> Dict[str, Any]:
    """Hedef URL için sıcak sekme yoksa arka planda hızlıca hazırlar."""
    target_url = (req.url or "").strip()
    if not target_url:
        return {"status": "ignored", "warm_count": 0}
    await playwright_driver._prune_expired_warm_sessions(target_url)
    stats = playwright_driver.warm_pool_stats()
    current_warm = stats.get(target_url, 0)
    if current_warm >= req.min_warm:
        return {
            "status": "already_warm",
            "url": target_url,
            "warm_count": current_warm,
        }
    asyncio.create_task(
        hybrid_executor.prewarm_target_with_proxy(
            target_url=target_url,
            max_warm_per_url=req.min_warm,
            use_proxy=req.use_proxy,
            max_attempts=3,
        )
    )
    return {
        "status": "warming_started",
        "url": target_url,
        "warm_count": current_warm,
    }


@app.post("/api/browser/execute")
async def execute_browser_action(req: ExecuteActionRequest) -> Dict[str, Any]:
    """Ajanın web gezinti ve etkileşim eylemini yürütür."""
    result = await hybrid_executor.execute(
        action=req.action,
        conversation_id=req.conversation_id,
        app_id=req.app_id,
        agent_id=req.agent_id,
        url=req.url,
        ref=req.ref,
        text=req.text,
        direction=req.direction,
        use_proxy=req.use_proxy,
        proxy_override=req.proxy_override,
        exclude_proxy_ids=req.exclude_proxy_ids,
        force_chromium=req.force_chromium,
        allow_private_networks=req.allow_private_networks,
    )
    if "error" in result:
        return {"success": False, **result}
    return {"success": True, **result}


@app.post("/api/browser/prompt-stream")
async def stream_browser_prompt(req: ExecuteActionRequest) -> StreamingResponse:
    """Sanal tarayıcı LLM yanıtını DOM üzerinden gerçek zamanlı SSE delta akışıyla döndürür."""
    queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()

    async def _on_delta(text_chunk: str) -> None:
        if text_chunk:
            await queue.put({"event": "delta", "text": text_chunk})

    async def _on_status(stage: str, message: str) -> None:
        if message:
            await queue.put({"event": "status", "stage": stage, "message": message})

    async def _runner() -> None:
        try:
            result = await hybrid_executor.execute(
                action="prompt_llm",
                conversation_id=req.conversation_id,
                app_id=req.app_id,
                agent_id=req.agent_id,
                url=req.url,
                ref=req.ref,
                text=req.text,
                direction=req.direction,
                use_proxy=req.use_proxy,
                proxy_override=req.proxy_override,
                exclude_proxy_ids=req.exclude_proxy_ids,
                force_chromium=req.force_chromium,
                allow_private_networks=req.allow_private_networks,
                on_delta=_on_delta,
                on_status=_on_status,
            )
            if "error" in result:
                await queue.put({"event": "done", "result": {"success": False, **result}})
            else:
                await queue.put({"event": "done", "result": {"success": True, **result}})
        except Exception as exc:
            await queue.put({"event": "done", "result": {"success": False, "error": str(exc)}})
        finally:
            await queue.put(None)

    async def _sse_generator() -> AsyncIterator[str]:
        task = asyncio.create_task(_runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/browser/sessions")
def list_browser_sessions() -> List[Dict[str, Any]]:
    """Tüm aktif sanal tarayıcı oturumlarını döner."""
    return browser_db.list_sessions()


@app.delete("/api/browser/sessions/{session_id}")
async def terminate_browser_session(session_id: str) -> Dict[str, Any]:
    """Belirtilen oturumu kapatır."""
    sess = browser_db.get_session_by_id(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı.")
    conv_id = sess.get("conversation_id", "")
    if conv_id:
        await playwright_driver.close_session(conv_id)
    browser_db.terminate_session(session_id)
    return {"message": "Oturum sonlandırıldı.", "session_id": session_id}


@app.post("/api/browser/sessions/prune")
def prune_idle_sessions() -> Dict[str, Any]:
    """Süresi dolmuş tüm boşta oturumları temizler."""
    count = browser_db.prune_expired_sessions()
    return {"pruned_count": count}


@app.get("/api/browser/dashboard")
def get_browser_dashboard() -> Dict[str, Any]:
    """Sanal tarayıcı havuz telemetri ve metriklerini döner."""
    return browser_db.get_dashboard_metrics()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BROWSER_SERVICE_PORT", "8002"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

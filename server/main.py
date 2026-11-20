"""
akalin-browser-module - Sanal Tarayıcı Arka Plan Motoru REST API (main.py)
"""

from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database.browser_postgres_db import browser_db
from engine.hybrid_executor import hybrid_executor
from engine.playwright_driver import playwright_driver


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
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
    action: str = Field(..., description="navigate, snapshot, click, type, scroll, back, close")
    conversation_id: str = Field(..., description="Ajan konuşma veya oturum kimliği")
    app_id: str = Field("", description="Uygulama kimliği")
    agent_id: str = Field("", description="Ajan kodu")
    url: Optional[str] = Field(None, description="Açılacak web adresi")
    ref: Optional[int] = Field(None, description="Tıklanacak veya yazılacak öğe ref numarası")
    text: Optional[str] = Field(None, description="Yazılacak metin")
    direction: Optional[str] = Field("down", description="Kaydırma yönü: up veya down")
    use_proxy: bool = Field(False, description="akalin-proxy-service üzerinden proxy kullanılsın mı?")
    force_chromium: bool = Field(False, description="Doğrudan Chromium açılsın mı?")
    allow_private_networks: bool = Field(False, description="İç ağlara izin verilsin mi?")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "healthy", "service": "akalin-browser-module"}


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
        force_chromium=req.force_chromium,
        allow_private_networks=req.allow_private_networks,
    )
    if "error" in result:
        return {"success": False, "error": result["error"]}
    return {"success": True, **result}


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

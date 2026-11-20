"""
akalin-browser-module - Proxy Servisi İstemcisi (proxy_client.py)
akalin-proxy-service ile REST API üzerinden haberleşir.
"""

from __future__ import annotations
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger("browser_proxy_client")

PROXY_SERVICE_URL = os.getenv("PROXY_SERVICE_URL", "http://localhost:8001").rstrip("/")


class ProxyServiceClient:
    """akalin-proxy-service REST API köprüsü."""

    def __init__(self, base_url: str = PROXY_SERVICE_URL) -> None:
        self.base_url = base_url

    def get_rotating_proxy(self) -> Optional[Dict[str, Any]]:
        """Düşük gecikmeli, aktif bir rotasyonlu proxy çeker."""
        url = f"{self.base_url}/api/proxies/rotating?count=1"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AkalinBrowserModule/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    return data[0]
        except Exception as exc:
            logger.warning(f"Proxy servisinden proxy alınamadı ({url}): {exc}")
        return None

    def report_outcome(
        self,
        proxy_id: str,
        success: bool,
        latency_ms: Optional[int] = None,
        cooldown_threshold: int = 3,
    ) -> None:
        """Proxy kullanım sonucunu akalin-proxy-service'e bildirir."""
        if not proxy_id:
            return
        url = f"{self.base_url}/api/proxies/outcome"
        payload = json.dumps({
            "proxy_id": proxy_id,
            "success": success,
            "latency_ms": latency_ms,
            "cooldown_threshold": cooldown_threshold,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "AkalinBrowserModule/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                pass
        except Exception as exc:
            logger.debug(f"Proxy sonucu bildirilemedi ({proxy_id}): {exc}")


proxy_client = ProxyServiceClient()

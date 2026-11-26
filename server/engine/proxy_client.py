"""
akalin-browser-module - Proxy Servisi İstemcisi (proxy_client.py)
akalin-proxy-service ile REST API üzerinden haberleşir.
"""

from __future__ import annotations
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("browser_proxy_client")

PROXY_SERVICE_URL = os.getenv("PROXY_SERVICE_URL", "http://localhost:8001").rstrip("/")


class ProxyServiceClient:
    """akalin-proxy-service REST API köprüsü."""

    def __init__(self, base_url: str = PROXY_SERVICE_URL) -> None:
        self.base_url = base_url

    def get_rotating_proxy(self, target_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Düşük gecikmeli, aktif, Chromium uyumlu (socks4 hariç) ve hedef alan adına uyumlu proxy çeker."""
        query = "count=1&exclude_protocols=socks4"
        if target_url:
            parsed = urllib.parse.urlparse(target_url)
            host = (parsed.hostname or target_url).strip().lower()
            if host:
                query += f"&target_host={urllib.parse.quote(host)}"
        url = f"{self.base_url}/api/proxies/rotating?{query}"
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
        target_url: Optional[str] = None,
        is_tunnel_latency: bool = False,
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
            "target_url": target_url,
            "is_tunnel_latency": is_tunnel_latency,
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

    def report_failure(
        self,
        proxy_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        error_reason: str = "",
        target_url: Optional[str] = None,
        exclude_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Proxy bağlantı hatasını akalin-proxy-service'in özel ProxyIncidentRoutine uç noktasına
        (`/api/proxies/report-failure`) bildirir. Servis IP'yi anında test edip ölmüşse siler,
        havuzu tamamlar ve temiz bir `replacement_proxy` döner.
        """
        if not proxy_id and not endpoint:
            return {}
        url = f"{self.base_url}/api/proxies/report-failure"
        payload = json.dumps({
            "proxy_id": proxy_id,
            "endpoint": endpoint,
            "error_reason": error_reason,
            "target_url": target_url,
            "exclude_ids": exclude_ids or [],
            "exclude_protocols": ["socks4"],
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "AkalinBrowserModule/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning(f"Proxy arıza bildirimi iletilemedi ({proxy_id or endpoint}): {exc}")
            return {}


proxy_client = ProxyServiceClient()

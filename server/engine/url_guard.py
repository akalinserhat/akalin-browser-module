"""
akalin-browser-module - Güvenli URL ve SSRF Koruması (url_guard.py)
"""

from __future__ import annotations
import ipaddress
import socket
import urllib.parse
from typing import Tuple


BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
}


class UrlGuard:
    """SSRF ve iç ağ erişim engelleyicisi."""

    @staticmethod
    def validate_url(url: str, allow_private: bool = False) -> Tuple[bool, str]:
        if not url or not isinstance(url, str):
            return False, "Geçersiz veya boş URL."

        clean = url.strip()
        if not (clean.startswith("http://") or clean.startswith("https://")):
            return False, "Yalnızca HTTP ve HTTPS protokolleri desteklenmektedir."

        try:
            parsed = urllib.parse.urlparse(clean)
            hostname = (parsed.hostname or "").strip().lower()

            if not hostname:
                return False, "URL alan adı (host) çözümlenemedi."

            if not allow_private:
                if hostname in BLOCKED_HOSTS or hostname.endswith(".local") or hostname.endswith(".internal"):
                    return False, f"Erişim engellendi: Yerel/İç ağ adresi ({hostname})."

                # DNS Çözümleme ve IP denetimi
                try:
                    ips = socket.getaddrinfo(hostname, None)
                    for family, _, _, _, sockaddr in ips:
                        ip_str = sockaddr[0]
                        ip_obj = ipaddress.ip_address(ip_str)
                        if (
                            ip_obj.is_loopback
                            or ip_obj.is_private
                            or ip_obj.is_link_local
                            or ip_obj.is_reserved
                            or str(ip_obj) == "169.254.169.254"
                        ):
                            return False, f"Erişim engellendi: İç ağ IP adresi ({ip_str})."
                except socket.gaierror:
                    # DNS çözümlenemedi, isteğin gitmesi zaten başarısız olur
                    pass

            return True, ""
        except Exception as exc:
            return False, f"URL denetim hatası: {exc}"


url_guard = UrlGuard()

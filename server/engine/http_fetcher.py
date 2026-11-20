"""
akalin-browser-module - Hızlı HTTP İstemcisi ve DOM Ayrıştırıcı (http_fetcher.py)
JavaScript gerektirmeyen sayfaları milisaniyeler içinde okur ve [ref] etiketleriyle döner.
"""

from __future__ import annotations
import gzip
from html.parser import HTMLParser
import io
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 AkalinBrowser/1.0"


@dataclass
class HttpFetchResult:
    url: str
    title: str
    snapshot_text: str
    interactive_elements: List[Dict[str, Any]] = field(default_factory=list)
    requires_javascript: bool = False
    status_code: int = 200
    latency_ms: int = 0
    error: Optional[str] = None


class SimpleHtmlContentExtractor(HTMLParser):
    """HTML belgesinden başlık, temiz metin ve numaralı etkileşimli öğeleri ayıklar."""

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.in_title: bool = False
        self.in_ignored_tag: bool = False
        self.ignored_tags = {"script", "style", "noscript", "svg", "path"}

        self.text_parts: List[str] = []
        self.elements: List[Dict[str, Any]] = []
        self.current_ref: int = 1

        self.current_element: Optional[Dict[str, Any]] = None
        self.current_element_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.ignored_tags:
            self.in_ignored_tag = True
            return

        if tag_lower == "title":
            self.in_title = True
            return

        attr_dict = {k.lower(): v or "" for k, v in attrs}

        # Etkileşimli öğeler (a, button, input, textarea, select)
        if tag_lower in ("a", "button", "input", "textarea", "select"):
            ref = self.current_ref
            self.current_ref += 1

            elem_type = attr_dict.get("type", "")
            placeholder = attr_dict.get("placeholder", "")
            aria_label = attr_dict.get("aria-label", "")
            href = attr_dict.get("href", "")
            value = attr_dict.get("value", "")

            elem_info = {
                "ref": ref,
                "tag": tag_lower,
                "type": elem_type,
                "role": attr_dict.get("role", tag_lower),
                "href": href,
                "placeholder": placeholder,
                "aria_label": aria_label,
                "value": value,
                "text": "",
            }

            if tag_lower in ("a", "button"):
                self.current_element = elem_info
                self.current_element_text = []
            else:
                # input / textarea / select tekil öğedir
                label = placeholder or aria_label or value or attr_dict.get("name", "")
                elem_info["text"] = label
                self.elements.append(elem_info)
                self.text_parts.append(f"[{ref}] {tag_lower}{f'[{elem_type}]' if elem_type else ''} \"{label}\"")

        elif tag_lower in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.ignored_tags:
            self.in_ignored_tag = False
            return

        if tag_lower == "title":
            self.in_title = False
            return

        if self.current_element and tag_lower in ("a", "button"):
            content = " ".join(self.current_element_text).strip()
            label = content or self.current_element.get("aria_label") or self.current_element.get("href") or "Link"
            self.current_element["text"] = label
            self.elements.append(self.current_element)
            self.text_parts.append(f"[{self.current_element['ref']}] {self.current_element['tag']} \"{label}\"")
            self.current_element = None
            self.current_element_text = []

        if tag_lower in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_ignored_tag:
            return

        clean = re.sub(r"\s+", " ", data).strip()
        if not clean:
            return

        if self.in_title:
            self.title_parts.append(clean)
            return

        if self.current_element is not None:
            self.current_element_text.append(clean)
        else:
            self.text_parts.append(clean + " ")


class HttpFetcher:
    """Hafif HTTP GET motoru."""

    @classmethod
    def fetch(
        cls,
        url: str,
        proxy_url: Optional[str] = None,
        max_chars: int = 8000,
        timeout: float = 8.0,
    ) -> HttpFetchResult:
        import time
        start_time = time.time()

        handlers = []
        if proxy_url:
            handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
        opener = urllib.request.build_opener(*handlers)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate",
            },
        )

        try:
            with opener.open(req, timeout=timeout) as resp:
                status_code = resp.status
                final_url = resp.geturl()
                encoding = resp.headers.get("Content-Encoding", "").lower()
                raw_bytes = resp.read()

                if "gzip" in encoding:
                    raw_bytes = gzip.decompress(raw_bytes)
                elif "deflate" in encoding:
                    try:
                        raw_bytes = zlib.decompress(raw_bytes)
                    except Exception:
                        raw_bytes = zlib.decompress(raw_bytes, -zlib.MAX_WBITS)

                charset = resp.headers.get_content_charset() or "utf-8"
                html_text = raw_bytes.decode(charset, errors="replace")

        except Exception as exc:
            lat = int((time.time() - start_time) * 1000)
            return HttpFetchResult(
                url=url,
                title="",
                snapshot_text="",
                status_code=500,
                latency_ms=lat,
                error=f"HTTP isteği başarısız: {exc}",
            )

        lat = int((time.time() - start_time) * 1000)

        # HTML Ayrıştırma
        parser = SimpleHtmlContentExtractor()
        try:
            parser.feed(html_text)
        except Exception:
            pass

        title = " ".join(parser.title_parts).strip() or urllib.parse.urlparse(final_url).netloc
        full_text = "".join(parser.text_parts)
        cleaned_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", full_text).strip()

        # JavaScript gereksinimi tespiti (sayfa içeriği çok kısaysa veya SPA kökü varsa)
        requires_js = False
        text_without_refs = re.sub(r"\[\d+\]\s*[a-z]+(\[[^\]]*\])?\s*\"[^\"]*\"", "", cleaned_text).strip()
        if len(text_without_refs) < 150:
            if "enable javascript" in html_text.lower() or "root" in html_text or "app" in html_text:
                requires_js = True

        truncated_snapshot = cleaned_text[:max_chars]
        if len(cleaned_text) > max_chars:
            truncated_snapshot += f"\n\n[...Metin sınırı nedeniyle kesildi: {len(cleaned_text)} karakterden ilk {max_chars} karakter...]"

        return HttpFetchResult(
            url=final_url,
            title=title,
            snapshot_text=truncated_snapshot,
            interactive_elements=parser.elements[:150],
            requires_javascript=requires_js,
            status_code=status_code,
            latency_ms=lat,
        )


http_fetcher = HttpFetcher()

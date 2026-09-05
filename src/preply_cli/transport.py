"""Resilient public transport for Preply HTML and GraphQL operations.

Handles:
1. Browser TLS & Header impersonation (eliminating immediate bot-detection 403).
2. Transparent proxy resolution via CLI --proxy flag and environment variables
   (PREPLY_PROXY_URL, DATAIMPULSE_PROXY_URL, HTTPS_PROXY, HTTP_PROXY, ALL_PROXY).
3. Automatic fallback: when direct fetch receives Cloudflare challenge or 403/429,
   retries via the configured proxy automatically.
4. Clean diagnostic error messages with actionable remedy recommendations.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

logger = logging.getLogger(__name__)

BASE_URL = "https://preply.com"
GRAPHQL_ENDPOINT = f"{BASE_URL}/graphql/v2"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

HTML_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

GRAPHQL_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/en/home",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class PreplyTransportError(RuntimeError):
    """Raised when a public Preply request fails or is blocked."""


def resolve_proxy_url(proxy: str | None = None) -> str | None:
    """Resolve active proxy URL by checking argument then environment variables in priority."""
    if proxy is not None:
        trimmed = proxy.strip()
        if not trimmed or trimmed.lower() in ("none", "direct", "off"):
            return None
        return trimmed

    for env_var in (
        "PREPLY_PROXY_URL",
        "PREPLY_TRACKER_PROXY_URL",
        "DATAIMPULSE_PROXY_URL",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        val = os.environ.get(env_var)
        if val and val.strip():
            return val.strip()

    return None


def mask_proxy(proxy_url: str | None) -> str:
    """Mask credentials in proxy URL for safe logging."""
    if not proxy_url:
        return "none"
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", proxy_url)


def _http_get(url: str, headers: dict[str, str], timeout: float, proxy: str | None) -> tuple[int, str]:
    """Execute GET request using requests if available, else urllib."""
    try:
        import requests  # noqa: F401

        session = requests.Session()
        session.trust_env = False if proxy else True
        proxies = {"http": proxy, "https": proxy} if proxy else None
        resp = session.get(url, headers=headers, timeout=timeout, proxies=proxies)
        return resp.status_code, resp.text
    except ImportError:
        pass

    # Urllib fallback
    handlers = [ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = build_opener(*handlers)
    req = Request(url, headers=headers, method="GET")
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body
    except URLError as exc:
        raise PreplyTransportError(f"Connection failed for {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise PreplyTransportError(f"Connection timed out after {timeout}s for {url}") from exc


def _http_post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float, proxy: str | None) -> tuple[int, str]:
    """Execute POST request with JSON body using requests if available, else urllib."""
    try:
        import requests  # noqa: F401

        session = requests.Session()
        session.trust_env = False if proxy else True
        proxies = {"http": proxy, "https": proxy} if proxy else None
        resp = session.post(url, headers=headers, json=body, timeout=timeout, proxies=proxies)
        return resp.status_code, resp.text
    except ImportError:
        pass

    # Urllib fallback
    raw_data = json.dumps(body).encode("utf-8")
    handlers = [ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = build_opener(*handlers)
    req = Request(url, data=raw_data, headers=headers, method="POST")
    try:
        with opener.open(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        resp_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, resp_text
    except URLError as exc:
        raise PreplyTransportError(f"Connection failed for {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise PreplyTransportError(f"Connection timed out after {timeout}s for {url}") from exc


def _is_cloudflare_challenge(status: int, text: str) -> bool:
    """Check if the response is a Cloudflare anti-bot challenge page."""
    if status in (403, 429):
        lowered = text.lower()
        if any(marker in lowered for marker in ("just a moment", "challenge-platform", "cf-mitigated", "cloudflare")):
            return True
        if "<!doctype html>" in lowered and "turnstile" in lowered:
            return True
    return False


def fetch_public_html(url: str, proxy: str | None = None, timeout: float = 30.0) -> tuple[str, str]:
    """Fetch public HTML page with auto-fallback to proxy if direct is blocked.

    Returns:
        (html_content, egress_mode_label)
    """
    resolved_proxy = resolve_proxy_url(proxy)

    # If an explicit proxy was requested, go through it directly
    if proxy and resolved_proxy:
        status, text = _http_get(url, HTML_HEADERS, timeout, resolved_proxy)
        if status == 200:
            return text, f"proxy:{mask_proxy(resolved_proxy)}"
        if status == 404:
            raise PreplyTransportError(f"Page not found at {url} (HTTP 404). Check tutor URL or ID.")
        raise PreplyTransportError(
            f"Preply refused request via proxy ({mask_proxy(resolved_proxy)}): HTTP {status}."
        )

    # Direct attempt first
    status, text = _http_get(url, HTML_HEADERS, timeout, None)
    if status == 200:
        return text, "direct"
    if status == 404:
        raise PreplyTransportError(f"Page not found at {url} (HTTP 404). Check tutor URL or ID.")

    # Check if Cloudflare blocked direct and proxy is available in environment
    if resolved_proxy and (status in (403, 429) or _is_cloudflare_challenge(status, text)):
        logger.info(
            "Direct fetch returned HTTP %d / Cloudflare challenge; retrying via fallback proxy %s",
            status,
            mask_proxy(resolved_proxy),
        )
        p_status, p_text = _http_get(url, HTML_HEADERS, timeout, resolved_proxy)
        if p_status == 200:
            return p_text, f"proxy_fallback:{mask_proxy(resolved_proxy)}"
        raise PreplyTransportError(
            f"Preply direct request blocked (HTTP {status}) and fallback proxy also returned HTTP {p_status}."
        )

    if _is_cloudflare_challenge(status, text) or status in (403, 429):
        raise PreplyTransportError(
            f"Preply blocked direct request for {url} (HTTP {status} Cloudflare challenge). "
            "Use --proxy <url> or set PREPLY_PROXY_URL / HTTPS_PROXY to route through a residential or regional proxy."
        )
    raise PreplyTransportError(f"Could not fetch {url}: HTTP {status}.")


def post_public_graphql(
    operation_name: str,
    query: str,
    variables: dict[str, Any],
    proxy: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send public GraphQL query to Preply with resilient proxy fallback and error normalization."""
    body = {
        "operationName": operation_name,
        "query": query,
        "variables": variables or {},
    }
    resolved_proxy = resolve_proxy_url(proxy)

    # 1. If explicit proxy was requested, send directly through it
    if proxy and resolved_proxy:
        status, text = _http_post_json(GRAPHQL_ENDPOINT, GRAPHQL_HEADERS, body, timeout, resolved_proxy)
        return _parse_graphql_payload(operation_name, status, text, f"proxy:{mask_proxy(resolved_proxy)}")

    # 2. Try direct first
    status, text = _http_post_json(GRAPHQL_ENDPOINT, GRAPHQL_HEADERS, body, timeout, None)
    if status == 200 and not _is_cloudflare_challenge(status, text):
        return _parse_graphql_payload(operation_name, status, text, "direct")

    # 3. Fallback to proxy if available
    if resolved_proxy and (status in (403, 429) or _is_cloudflare_challenge(status, text)):
        logger.info(
            "%s: direct GraphQL blocked (HTTP %d); retrying via fallback proxy %s",
            operation_name,
            status,
            mask_proxy(resolved_proxy),
        )
        p_status, p_text = _http_post_json(GRAPHQL_ENDPOINT, GRAPHQL_HEADERS, body, timeout, resolved_proxy)
        return _parse_graphql_payload(operation_name, p_status, p_text, f"proxy_fallback:{mask_proxy(resolved_proxy)}")

    if _is_cloudflare_challenge(status, text) or status in (403, 429):
        raise PreplyTransportError(
            f"{operation_name}: blocked by Cloudflare challenge (HTTP {status}). "
            "Preply requires egress from an unrestricted IP or residential proxy. "
            "Provide --proxy <url> or export PREPLY_PROXY_URL."
        )

    return _parse_graphql_payload(operation_name, status, text, "direct")


def _parse_graphql_payload(operation_name: str, status: int, text: str, egress: str) -> dict[str, Any]:
    """Parse and validate GraphQL response JSON."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        snippet = text.strip()[:200]
        raise PreplyTransportError(
            f"{operation_name}: non-JSON response from Preply (HTTP {status}, egress {egress}): {snippet}"
        ) from exc

    if status >= 400 or payload.get("errors"):
        errors = payload.get("errors")
        err_msg = json.dumps(errors)[:400] if errors else f"HTTP {status}"
        raise PreplyTransportError(f"{operation_name} failed ({egress}): {err_msg}")

    data = payload.get("data") or {}
    data["_egress"] = egress
    return data

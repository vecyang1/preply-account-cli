"""Direct authenticated HTTPS transport for Preply's private GraphQL API.

This is the unattended alternative to the browser-harness transport. Instead of
executing same-origin ``fetch()`` inside a logged-in Chrome tab, it replays a
stored Preply ``sessionid`` cookie straight to ``https://preply.com/graphql/v2``.
The session value comes from the credential store (1Password) and stays in
memory; nothing is written to disk.

It implements the same one-method transport contract as
``BrowserHarnessClient``: ``fetch_graphql(list[OperationCall]) -> dict`` keyed by
each call's ``key``, with an injected ``_account`` identity block so downstream
code (``cli._account_role``, ``cmd_account``) works unchanged.

Cloudflare fronts preply.com and can fingerprint the TLS client (JA3). The
transport therefore prefers ``curl_cffi`` with Chrome impersonation and falls
back to ``requests`` if curl_cffi is unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .browser import OperationCall
from .queries import get_operation

BASE_URL = "https://preply.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# (status_code, response_text) is all the transport needs from an HTTP client.
HttpPost = Callable[[str, dict[str, str], dict[str, Any], float], "tuple[int, str]"]


class PreplyDirectError(RuntimeError):
    """A direct HTTPS GraphQL request failed or the session was rejected."""


class PreplySessionExpired(PreplyDirectError):
    """Preply answered, and it did not accept the stored session.

    A subclass so every existing ``except PreplyDirectError`` still catches it,
    but callers that need the distinction can ask for it. `session status` does:
    a TLS failure or a Cloudflare challenge says nothing about the session, and
    reporting either as `stale` sends the user to re-capture a credential that
    may be perfectly good -- a verdict drawn from a failure to look.
    """


def _curl_cffi_post(url, headers, body, timeout):  # pragma: no cover - network
    from curl_cffi import requests as creq

    resp = creq.post(
        url, impersonate="chrome", headers=headers, json=body, timeout=timeout
    )
    return resp.status_code, resp.text


def _requests_post(url, headers, body, timeout):  # pragma: no cover - network
    import requests

    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    return resp.status_code, resp.text


def curl_cffi_available() -> bool:
    """Whether the Chrome-impersonating client is importable."""
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        return False
    return True


def _tls_client_note() -> str:
    """Name the fallback client when it is the likely cause of a challenge.

    `curl_cffi` impersonates Chrome's TLS fingerprint; `requests` does not, and
    a non-Chrome JA3 is the single likeliest way to be challenged. The downgrade
    happens silently, so a user on the fallback reads "the session was not
    accepted" and re-captures a session that was never the problem.
    """
    if curl_cffi_available():
        return ""
    return (
        "\nNote: 'curl_cffi' is not installed, so this ran on the 'requests' "
        "fallback, which does not impersonate Chrome's TLS fingerprint and is "
        "far more likely to be challenged. Try: python3 -m pip install curl_cffi"
    )


def default_http_post() -> HttpPost:
    """Pick the most Cloudflare-robust HTTP client available at runtime."""
    if curl_cffi_available():
        return _curl_cffi_post
    try:
        import requests  # noqa: F401

        return _requests_post
    except ImportError as exc:
        raise PreplyDirectError(
            "Direct transport needs 'curl_cffi' (preferred) or 'requests'. "
            "Install with: python3 -m pip install curl_cffi"
        ) from exc


@dataclass
class DirectHttpClient:
    """Replays a stored Preply session cookie to the GraphQL API.

    ``account`` is the resolved identity block that gets injected as ``_account``.
    When not supplied, it is resolved live on the first fetch via the account
    identity query, which also confirms the session is still valid.
    """

    sessionid: str = field(repr=False)
    csrftoken: str | None = field(default=None, repr=False)
    account: dict[str, Any] | None = None
    base_url: str = BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    timeout: float = 45.0
    http_post: HttpPost | None = None
    _resolved_account: dict[str, Any] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.sessionid:
            raise PreplyDirectError("DirectHttpClient requires a non-empty sessionid.")
        if self.http_post is None:
            self.http_post = default_http_post()
        if self.account is not None:
            self._resolved_account = dict(self.account)

    # -- HTTP -------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        cookie = f"sessionid={self.sessionid}"
        if self.csrftoken:
            cookie += f"; csrftoken={self.csrftoken}"
        headers = {
            "content-type": "application/json",
            "accept": "*/*",
            "user-agent": self.user_agent,
            "origin": self.base_url,
            "referer": f"{self.base_url}/en/home",
            "cookie": cookie,
        }
        if self.csrftoken:
            headers["x-csrftoken"] = self.csrftoken
        return headers

    def _post(self, operation, variables: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{operation.endpoint}"
        body = {
            "operationName": operation.name,
            "variables": variables or {},
            "query": operation.query,
        }
        assert self.http_post is not None  # set in __post_init__
        try:
            status, text = self.http_post(url, self._headers(), body, self.timeout)
        except Exception as exc:  # noqa: BLE001 - normalize transport failures
            raise PreplyDirectError(
                f"{operation.name}: transport error: {type(exc).__name__}: {exc}"
            ) from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            snippet = text.strip()[:300]
            lowered = snippet.lower()
            if any(m in lowered for m in ("just a moment", "challenge-platform", "cf-")):
                raise PreplyDirectError(
                    f"{operation.name}: blocked by Cloudflare challenge (http {status}). "
                    "The session or TLS client was not accepted."
                    + _tls_client_note()
                )
            raise PreplyDirectError(
                f"{operation.name}: non-JSON response (http {status}): {snippet}"
            )
        if status >= 400 or payload.get("errors"):
            raise PreplyDirectError(
                f"{operation.name}: {json.dumps(payload)[:1200]}"
            )
        return payload.get("data") or {}

    # -- Identity ---------------------------------------------------------
    def _resolve_account(self) -> dict[str, Any]:
        if self._resolved_account is not None:
            return self._resolved_account
        data = self._post(get_operation("PreplyCliAccountIdentity"), {})
        user = (data or {}).get("currentUser")
        if not user or not user.get("id"):
            raise PreplySessionExpired(
                "Stored Preply session is no longer authenticated "
                "(currentUser is null). Re-capture the session from a logged-in "
                "Chrome tab with `preply session capture`."
            )
        tutor = user.get("tutor") or {}
        self._resolved_account = {
            "targetUrl": "direct-https",
            "userId": user.get("id"),
            "name": user.get("fullName") or user.get("firstName"),
            "role": "tutor" if tutor else "learner",
            "tutorId": tutor.get("id"),
        }
        return self._resolved_account

    def resolve_account(self) -> dict[str, Any]:
        """Public liveness probe: resolve and return the account identity block."""
        return self._resolve_account()

    # -- Transport contract ----------------------------------------------
    def fetch_graphql(self, calls: list[OperationCall]) -> dict[str, Any]:
        """Execute each call over direct HTTPS, keyed by call.key, plus _account."""
        account = self._resolve_account()
        result: dict[str, Any] = {}
        for call in calls:
            result[call.key] = self._post(call.operation, call.variables)
        result["_account"] = account
        return result

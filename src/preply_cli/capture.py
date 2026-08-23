"""Capture live Preply sessions from Chrome into the 1Password credential store.

This is the present-user setup step: it decrypts each Chrome profile's Preply
``sessionid``, probes it live against the GraphQL API, and stores only the
sessions that actually authenticate — recording the account identity the server
reports (never the Chrome profile's email label).

Return values are non-secret: they describe what happened per profile without
ever exposing a cookie value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .chrome_cookies import (
    ChromeCookieError,
    ProfileCookies,
    read_all_profiles,
    read_profile_cookies,
    webkit_to_iso,
)
from .direct import DirectHttpClient, PreplyDirectError, PreplySessionExpired
from .session_store import SessionStoreError, list_sessions, resolve_session, store_session


@dataclass
class CaptureResult:
    profile: str
    status: str  # stored | stale | no-session | error
    account_id: str | None = None
    name: str | None = None
    role: str | None = None
    item_id: str | None = None
    detail: str | None = None

    def as_row(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "status": self.status,
            "account_id": self.account_id or "",
            "name": self.name or "",
            "role": self.role or "",
            "item_id": self.item_id or "",
            "detail": self.detail or "",
        }


def _capture_one(cookies: ProfileCookies) -> CaptureResult:
    if not cookies.has_session:
        if cookies.decrypt_error:
            return CaptureResult(
                cookies.profile, "error",
                detail=f"cookie present but undecryptable: {cookies.decrypt_error}"[:200],
            )
        return CaptureResult(cookies.profile, "no-session")
    client = DirectHttpClient(sessionid=cookies.sessionid, csrftoken=cookies.csrftoken)
    try:
        account = client.resolve_account()
    except PreplyDirectError as exc:
        # Cookie present but rejected server-side (logged out / expired).
        return CaptureResult(cookies.profile, "stale", detail=str(exc)[:160])
    try:
        meta = store_session(
            account_id=account["userId"],
            account_name=account.get("name") or "",
            role=account.get("role") or "unknown",
            sessionid=cookies.sessionid,
            csrftoken=cookies.csrftoken,
            source_profile=cookies.profile,
            sessionid_expiry=webkit_to_iso(cookies.sessionid_expiry_webkit),
        )
    except SessionStoreError as exc:
        return CaptureResult(
            cookies.profile, "error", account_id=str(account.get("userId")),
            name=account.get("name"), role=account.get("role"), detail=str(exc)[:200],
        )
    return CaptureResult(
        cookies.profile, "stored",
        account_id=meta.account_id, name=meta.name, role=meta.role,
        item_id=meta.item_id,
    )


def capture_sessions(profiles: list[str] | None = None) -> list[CaptureResult]:
    """Capture live sessions from the given profiles (default: all profiles)."""
    if profiles:
        cookie_sets: list[ProfileCookies] = []
        results: list[CaptureResult] = []
        for profile in profiles:
            try:
                cookie_sets.append(read_profile_cookies(profile))
            except ChromeCookieError as exc:
                results.append(CaptureResult(profile, "error", detail=str(exc)[:200]))
        results.extend(_capture_one(c) for c in cookie_sets)
        return results
    return [_capture_one(c) for c in read_all_profiles()]


def session_status() -> list[dict[str, Any]]:
    """Probe every stored session for current liveness. Non-secret rows only."""
    rows: list[dict[str, Any]] = []
    for meta in list_sessions():
        row: dict[str, Any] = {
            "item_id": meta.item_id,
            "name": meta.name or "",
            "role": meta.role or "",
            "account_id": meta.account_id or "",
            "live": "?",
        }
        # Resolving the credential and probing it are separate questions, and
        # only the second one can answer "is this session still valid".
        # Collapsing both into "stale" claimed a verdict about Preply from a
        # 1Password rate-limit or an ambiguous selector -- and "stale" sends the
        # user to `session capture`, which needs them physically present for a
        # Keychain prompt. A failure to look is `unknown`, not a negative result.
        try:
            _, sessionid, csrftoken = resolve_session(
                role="any", user_id=int(meta.account_id) if meta.account_id else None,
                name=None,
            )
        except (SessionStoreError, ValueError) as exc:
            row["live"] = "unknown"
            row["detail"] = f"could not read the stored credential: {str(exc)[:120]}"
            rows.append(row)
            continue
        try:
            client = DirectHttpClient(sessionid=sessionid, csrftoken=csrftoken)
            account = client.resolve_account()
        except PreplySessionExpired as exc:
            # Preply answered, and it did not accept the session. Only this one
            # is evidence the credential itself is dead.
            row["live"] = "stale"
            row["detail"] = str(exc)[:120]
        except (PreplyDirectError, OSError, ValueError) as exc:
            # Never got an answer -- network, TLS, Cloudflare, HTTP 500. The
            # session was not tested, so no verdict about it is available.
            row["live"] = "unknown"
            row["detail"] = f"could not reach Preply: {str(exc)[:120]}"
        else:
            row["live"] = "live"
            row["resolved_name"] = account.get("name") or ""
        rows.append(row)
    return rows

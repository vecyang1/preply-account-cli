"""Store and retrieve Preply session credentials in 1Password, unattended.

Each Preply account gets one ``API Credential`` item in a dedicated vault
(default ``Agent Automation``). The ``sessionid`` cookie is the secret; a
``csrftoken`` is kept alongside for mutations. Non-secret selection keys
(account id, role) live in item *tags* so the CLI can list and choose a session
without ever reading a secret value.

Reads and writes go through the 1Password Service Account bridge
(``bridge_router``), which does not require Touch ID and keeps secrets in
memory. That is what makes the direct transport runnable while the user is away.

Secret values returned by this module (the sessionid / csrftoken) must never be
printed or logged by callers.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Resolved from the running user's home, not a baked-in path: the previous
# hardcoded absolute path only worked on one machine and leaked a username.
# Override with PREPLY_OP_BRIDGE_DIR when the skill lives elsewhere.
DEFAULT_BRIDGE_DIR = str(Path.home() / ".agents" / "skills" / "1password" / "scripts")
DEFAULT_VAULT = "Agent Automation"
SESSION_TAG = "preply-session"
ROLE_TAG_PREFIX = "preply-role:"
ACCOUNT_TAG_PREFIX = "preply-account:"


class SessionStoreError(RuntimeError):
    """A 1Password credential-store operation failed."""


class OpBridgeUnavailable(SessionStoreError):
    """The 1Password Service Account bridge could not be reached."""


@dataclass(frozen=True)
class SessionMeta:
    """Non-secret metadata about a stored Preply session."""

    item_id: str
    title: str
    account_id: str | None
    role: str | None
    name: str | None

    def matches(self, role: str, user_id: int | None, name: str | None) -> bool:
        if role and role != "any" and self.role != role:
            return False
        if user_id is not None and str(user_id) != str(self.account_id):
            return False
        if name:
            haystack = (self.name or "").lower()
            if name.strip().lower() not in haystack:
                return False
        return True


def _vault() -> str:
    return os.environ.get("PREPLY_OP_VAULT", DEFAULT_VAULT)


def _bridge():
    """Import the 1Password Service Account bridge router, or fail clearly."""
    bridge_dir = os.environ.get("PREPLY_OP_BRIDGE_DIR", DEFAULT_BRIDGE_DIR)
    if bridge_dir not in sys.path:
        sys.path.insert(0, bridge_dir)
    try:
        import bridge_router  # type: ignore

        return bridge_router
    except ImportError as exc:
        raise OpBridgeUnavailable(
            "Could not import the 1Password Service Account bridge from "
            f"{bridge_dir!r}. Set PREPLY_OP_BRIDGE_DIR to the 1password skill's "
            "scripts directory, and ensure the Service Account bridge is running "
            "(`service_account_bridge.py status`)."
        ) from exc


def _op(args: list[str], *, timeout: float = 60, stdin_text: str | None = None) -> str:
    """Run an `op` command through the Service Account bridge; return stdout.

    Never pass secret values in ``args`` (they land in the process table). Put
    secrets in ``stdin_text`` instead.
    """
    bridge = _bridge()
    try:
        result = bridge.run_command(
            ["op", *args], timeout=timeout, stdin_text=stdin_text
        )
    except Exception as exc:  # noqa: BLE001 - normalize bridge failures
        raise OpBridgeUnavailable(f"1Password bridge error: {exc}") from exc
    # bridge_router returns a plain dict: {request_id, returncode, stdout, stderr}
    code = result.get("returncode")
    if code != 0:
        stderr = (result.get("stderr") or "").strip()
        raise SessionStoreError(
            f"op {' '.join(args[:2])} failed (exit {code}): {stderr[:400]}"
        )
    return result.get("stdout") or ""


# -- Listing / selection --------------------------------------------------
def _tag_value(tags: list[str], prefix: str) -> str | None:
    for tag in tags or []:
        if tag.startswith(prefix):
            return tag[len(prefix) :]
    return None


def list_sessions() -> list[SessionMeta]:
    """List stored Preply sessions (metadata only — no secrets are read)."""
    out = _op(["item", "list", "--tags", SESSION_TAG, "--vault", _vault(),
               "--format", "json"])
    try:
        items = json.loads(out) if out.strip() else []
    except json.JSONDecodeError as exc:
        raise SessionStoreError(f"Could not parse `op item list` output: {exc}") from exc
    sessions: list[SessionMeta] = []
    for item in items:
        tags = item.get("tags") or []
        sessions.append(
            SessionMeta(
                item_id=item.get("id"),
                title=item.get("title") or "",
                account_id=_tag_value(tags, ACCOUNT_TAG_PREFIX),
                role=_tag_value(tags, ROLE_TAG_PREFIX),
                name=_parse_name_from_title(item.get("title") or ""),
            )
        )
    return sessions


def _parse_name_from_title(title: str) -> str | None:
    # Title format: "Preply Session · <name> · <role> · <account_id>"
    parts = [p.strip() for p in title.split("·")]
    if len(parts) >= 4 and parts[0].lower().startswith("preply session"):
        return parts[1]
    return None


def select_session(role: str, user_id: int | None, name: str | None) -> SessionMeta:
    """Choose the one stored session matching the selector, or raise."""
    candidates = [s for s in list_sessions() if s.matches(role, user_id, name)]
    if not candidates:
        raise SessionStoreError(
            "No stored Preply session matches the selector "
            f"(role={role!r}, user_id={user_id!r}, name={name!r}). "
            "Capture one with `preply session capture`."
        )
    if len(candidates) > 1:
        listing = ", ".join(f"{s.name}({s.role}/{s.account_id})" for s in candidates)
        raise SessionStoreError(
            f"Selector is ambiguous across {len(candidates)} sessions: {listing}. "
            "Narrow it with --user-id or --name."
        )
    return candidates[0]


# -- Secret read ----------------------------------------------------------
def read_secret(item_id: str, field: str) -> str | None:
    """Read one concealed field via `op read` (secret stays in memory)."""
    ref = f"op://{_vault()}/{item_id}/{field}"
    try:
        value = _op(["read", ref]).strip()
    except SessionStoreError:
        return None
    return value or None


def read_item_secrets(item_id: str) -> dict[str, str]:
    """Read all concealed fields of one item in a single bridge round-trip.

    Returns a mapping of field id/label -> value. Values stay in memory; callers
    must not print them. One `op item get` is used instead of one `op read` per
    field, which halves the slow Service Account bridge calls per command.
    """
    out = _op(["item", "get", item_id, "--vault", _vault(), "--format", "json"])
    try:
        item = json.loads(out) if out.strip() else {}
    except json.JSONDecodeError as exc:
        raise SessionStoreError(f"Could not parse `op item get` output: {exc}") from exc
    secrets: dict[str, str] = {}
    for field in item.get("fields") or []:
        value = field.get("value")
        if value is None:
            continue
        for key in (field.get("id"), field.get("label")):
            if key:
                secrets.setdefault(str(key), str(value))
    return secrets


def resolve_session(
    role: str, user_id: int | None, name: str | None
) -> tuple[SessionMeta, str, str | None]:
    """Return (meta, sessionid, csrftoken) for the matching stored session."""
    meta = select_session(role, user_id, name)
    secrets = read_item_secrets(meta.item_id)
    sessionid = secrets.get("credential")
    if not sessionid:
        raise SessionStoreError(
            f"Stored session {meta.title!r} has no readable 'credential' field."
        )
    csrftoken = secrets.get("csrftoken") or None
    return meta, sessionid, csrftoken


# -- Write ----------------------------------------------------------------
def _build_item_template(
    *,
    account_id: str,
    account_name: str,
    role: str,
    sessionid: str,
    csrftoken: str | None,
    source_profile: str,
    sessionid_expiry: str | None,
) -> dict[str, Any]:
    title = f"Preply Session · {account_name} · {role} · {account_id}"
    captured_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    fields: list[dict[str, Any]] = [
        {"id": "credential", "type": "CONCEALED", "label": "credential",
         "value": sessionid},
        {"id": "csrftoken", "type": "CONCEALED", "label": "csrftoken",
         "value": csrftoken or ""},
        {"id": "account_id", "type": "STRING", "label": "preply_account_id",
         "value": account_id},
        {"id": "account_name", "type": "STRING", "label": "preply_account_name",
         "value": account_name},
        {"id": "role", "type": "STRING", "label": "preply_role", "value": role},
        {"id": "source_profile", "type": "STRING", "label": "source_chrome_profile",
         "value": source_profile},
        {"id": "captured_at", "type": "STRING", "label": "captured_at",
         "value": captured_at},
    ]
    if sessionid_expiry:
        fields.append(
            {"id": "sessionid_expiry", "type": "STRING", "label": "sessionid_expiry",
             "value": sessionid_expiry}
        )
    return {
        "title": title,
        "category": "API_CREDENTIAL",
        "tags": [
            SESSION_TAG,
            f"{ROLE_TAG_PREFIX}{role}",
            f"{ACCOUNT_TAG_PREFIX}{account_id}",
            "preply-cli",
        ],
        "fields": fields,
    }


def store_session(
    *,
    account_id: str,
    account_name: str,
    role: str,
    sessionid: str,
    csrftoken: str | None,
    source_profile: str,
    sessionid_expiry: str | None = None,
) -> SessionMeta:
    """Create/refresh the 1Password item for one Preply account.

    Existing items for the same account_id are removed after the new item is
    created, so a re-capture replaces stale credentials without leaving a
    duplicate. All secret values travel via stdin, never argv.
    """
    existing = [s for s in list_sessions() if s.account_id == str(account_id)]
    template = _build_item_template(
        account_id=str(account_id),
        account_name=account_name,
        role=role,
        sessionid=sessionid,
        csrftoken=csrftoken,
        source_profile=source_profile,
        sessionid_expiry=sessionid_expiry,
    )
    created = _op(
        ["item", "create", "--vault", _vault(), "--format", "json", "-"],
        stdin_text=json.dumps(template),
        timeout=90,
    )
    try:
        new_item = json.loads(created)
    except json.JSONDecodeError as exc:
        raise SessionStoreError(f"Could not parse created item: {exc}") from exc
    new_id = new_item.get("id")
    # Remove stale duplicates only after a confirmed create.
    for stale in existing:
        if stale.item_id and stale.item_id != new_id:
            try:
                _op(["item", "delete", stale.item_id, "--vault", _vault()])
            except SessionStoreError:
                pass  # non-fatal; report the new item regardless
    return SessionMeta(
        item_id=new_id,
        title=new_item.get("title") or template["title"],
        account_id=str(account_id),
        role=role,
        name=account_name,
    )

"""Shared readers and the sentinels every summary uses.

`_opt_number` returns None for an absent field; `_number`'s 0.0 default is only
for genuine optional addends. Conflating them is the bug this package keeps
re-learning: a moved field becomes a confident zero the user acts on."""

from __future__ import annotations

from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict_nodes(value: Any) -> list[dict[str, Any]]:
    """Keep only the dict entries of a node list.

    GraphQL list elements are nullable, so `nodes: [null]` is a legal response
    and does arrive. Every accessor funnels through here so a single null
    element cannot take down a command with an AttributeError at the user.
    """
    if not isinstance(value, list):
        return []
    return [node for node in value if isinstance(node, dict)]


def student_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    profile = snapshot.get("profile") or {}
    tutor = (profile.get("currentUser") or {}).get("tutor")
    connection = (tutor or {}).get("studentManagementTutorings") or {}
    return _dict_nodes(connection.get("nodes"))


def _sum_or_unknown(items: list[dict[str, Any]], key: str) -> tuple[float, int]:
    """Sum a field across nodes, returning (total, count_unreadable).

    A field that moved must not vanish into the total as a silent zero: the
    caller turns a non-zero unreadable count into a visible warning.
    """
    total = 0.0
    unreadable = 0
    for item in items:
        value = _opt_number(item, key)
        if value is None:
            unreadable += 1
        else:
            total += value
    return total, unreadable


NO_SUBSCRIPTION = "NO_SUBSCRIPTION"
UNKNOWN = "UNKNOWN"
UNREADABLE_DATE = "?"


def _opt_number(container: dict[str, Any], key: str) -> float | None:
    """Read a numeric field, returning None when it is absent or unreadable.

    Deliberately not ``_number``: defaulting to 0.0 is right when summing an
    optional quantity, and wrong here, where a missing field would otherwise be
    displayed as a confident zero balance.
    """
    if not isinstance(container, dict) or key not in container:
        return None
    raw = container[key]
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def balance_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-tutoring balance nodes from a BalanceManagementData payload."""
    root = (snapshot.get("balance") or {}).get("balanceManagementData") or {}
    return _dict_nodes(root.get("nodes"))


def _opt_int(container: dict[str, Any], key: str) -> int | None:
    """Like ``_opt_number`` but for fields that are counts, not quantities.

    Certificate levels are whole numbers; rendering them as ``90.0`` reads like
    a measurement. Absent still means ``None``, never 0.
    """
    value = _opt_number(container, key)
    return None if value is None else int(value)


def _absolute_preply_url(url: Any) -> str:
    """Make a Preply asset link openable.

    Preply returns two relative forms and neither works as-is. Measured live:
    ``downloadUrl`` is root-relative (``/files/<id>?download=true``), while
    avatar-style assets are protocol-relative (``//...``). Anything printing a
    Preply asset URL has to do this or it emits dead links.
    """
    if not isinstance(url, str) or not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://preply.com{url}"
    return url



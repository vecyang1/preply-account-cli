"""Helpers shared by every command group.

Transport selection, snapshot loading, output shaping, and the data-warning
channel that carries `absent is not zero` findings to stderr."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..browser import (
    HARNESS_COMMAND,
    BrowserHarnessClient,
    BrowserTargetSelector,
    PreplyBrowserError,
    harness_available,
)
from ..client import PreplyClient
from ..formatting import format_table, money


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


class SnapshotError(RuntimeError):
    """A ``--file`` snapshot could not be read, parsed, or recognised."""


def _count(value: str) -> int:
    """An argparse type for row/day counts: a positive integer.

    ``type=int`` accepted 0 and negatives. Offline they reached a Python slice
    (``rows[:-2]`` quietly dropped rows off the *end* of the table); live they
    were forwarded verbatim to Preply as ``count: -5``. Both look like a normal
    result, so the wrong number of rows is never questioned.
    """
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or greater, got {number}")
    return number


# A snapshot always carries at least one of these at the top level: the
# transport attaches `_account`, `cmd_snapshot` adds `account_role` /
# `account_label` / `summary`, and every fetch keys its operations by name.
# Older (v0.6-era) snapshots predate `_account` but still have `account`.
SNAPSHOT_MARKERS = frozenset({
    "_account", "account", "account_role", "account_label", "summary",
    "student_details", "payments", "students", "history", "balance",
    "chat", "lessons", "upcoming", "tutorings", "stats", "schedule",
    "renewals", "certificates",
})


def _load_snapshot(path: Path) -> dict[str, Any]:
    """Read a ``--file`` snapshot, or fail with a message naming the cause.

    Two failures this prevents, both measured:

    - I/O and parse errors used to escape as raw tracebacks with exit 1, while
      every other CLI failure exits 2 with a ``preply:`` prefix.
    - Worse, a *well-formed* JSON file that is not a snapshot rendered as a
      confident all-zero financial report at exit 0 -- `spent_total 0.0`,
      `student_revenue_total 0.00 USD` -- because every extractor asked a dict
      that simply had none of the keys. Nothing raised, nothing warned. An
      unrecognised payload is unreadable, not empty, so it is refused here.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SnapshotError(f"cannot read snapshot {str(path)!r}: {exc.strerror}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(
            f"{str(path)!r} is not valid JSON ({exc.msg}, line {exc.lineno} column {exc.colno})."
        ) from exc
    if not isinstance(data, dict):
        raise SnapshotError(
            f"{str(path)!r} contains a JSON {type(data).__name__}, not a snapshot object. "
            "Snapshots are written by `preply snapshot`."
        )
    if not SNAPSHOT_MARKERS & data.keys():
        found = ", ".join(sorted(data)[:6]) or "(no keys)"
        raise SnapshotError(
            f"{str(path)!r} is valid JSON but not a Preply snapshot -- none of its "
            f"top-level keys are recognised (found: {found}). Reading it would report "
            "empty totals as if the account were empty. Produce one with `preply snapshot`."
        )
    return data


def _client(args: argparse.Namespace) -> PreplyClient:
    """Build a client using the selected transport.

    - ``direct``: read a stored session from 1Password and replay it over HTTPS.
      Fails loudly if no matching stored session or the bridge is unavailable.
    - ``browser``: the original logged-in-Chrome-tab transport.
    - ``auto`` (default): use ``direct`` when a matching stored session exists,
      otherwise fall back to ``browser``. A stored-but-stale session is not a
      fallback trigger — it surfaces as a clear "re-capture" error at fetch time,
      so a silent, wrong-looking browser fallback cannot mask an expired session.
    """
    transport = getattr(args, "transport", "auto")
    role, user_id, name = args.role, args.user_id, args.name
    direct_reason: str | None = None
    if transport in ("direct", "auto"):
        from ..direct import DirectHttpClient
        from ..session_store import SessionStoreError, resolve_session

        try:
            _meta, sessionid, csrftoken = resolve_session(role, user_id, name)
        except SessionStoreError as exc:
            # No matching stored session or bridge unavailable
            # (OpBridgeUnavailable is a SessionStoreError). Hard-fail only when
            # the user explicitly asked for direct; otherwise fall back to
            # browser -- but keep the reason. Discarding it was a real defect:
            # a first-time user with nothing set up was told only
            # "browser-harness is not on PATH", which names one route's
            # dependency as if it were the whole problem.
            if transport == "direct":
                raise
            direct_reason = str(exc)
        else:
            return PreplyClient(browser=DirectHttpClient(sessionid=sessionid, csrftoken=csrftoken))
    if transport == "auto" and not harness_available():
        raise PreplyBrowserError(_no_transport_message(direct_reason))
    selector = BrowserTargetSelector(role=role, user_id=user_id, name=name)
    return PreplyClient(
        browser=BrowserHarnessClient(selector=selector, fallback_note=direct_reason)
    )


def _no_transport_message(direct_reason: str | None) -> str:
    """Explain that *both* routes are unavailable, and why each one is.

    Only used for ``--transport auto``. When the user names a transport they
    get that transport's own error, undiluted.
    """
    direct = direct_reason or "no stored session could be resolved."
    return (
        "Cannot reach Preply: neither transport is available.\n"
        f"  direct  (stored session) : {direct}\n"
        f"  browser (logged-in tab)  : {HARNESS_COMMAND} is not on PATH.\n"
        "\n"
        "Set up either route:\n"
        "  direct  - log in to Preply in Chrome, then run `preply session capture`\n"
        "            (requires 1Password and the Service Account bridge).\n"
        f"  browser - put {HARNESS_COMMAND} on PATH and open a logged-in Preply tab.\n"
        "\n"
        "`preply session list` shows what is already stored. Pass "
        "--transport direct or --transport browser to see one route's error alone."
    )


def _account_role(data: dict[str, Any]) -> str:
    account = data.get("_account") or {}
    if account.get("role"):
        return str(account["role"])
    current = (data.get("account") or {}).get("currentUser") or {}
    return "tutor" if current.get("tutor") else "learner"


def _emit(data: Any, rows: list[dict[str, Any]] | None, columns: list[str], args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        _print_json(data)
    elif getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows or [], columns), end="")
    else:
        print(format_table(rows or [], columns))


def _money_or_unknown(value: Any) -> str:
    """Format money, but say "unknown" rather than leaving a bare blank cell.

    `money(None)` renders "", which in a side-by-side financial comparison is
    indistinguishable from a field that was simply not applicable. Swapping a
    confidently-wrong 0.00 for an unexplained blank is not a fix.
    """
    return "unknown" if value is None else money(value)


BALANCE_COLUMNS = ["tutor", "subject", "hours", "unscheduled", "unavailable",
                   "next_charge", "frequency", "status"]
PENDING_COLUMNS = ["tutor", "country", "price_usd", "tutor_status"]


def _summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Summary as metric/value rows, minus the warnings channel.

    Warnings already went to stderr; rendering them again as a table cell shows
    an empty list on every healthy run, which trains the eye to ignore the row.
    """
    return [
        {"metric": key, "value": value}
        for key, value in summary.items()
        if key != "warnings"
    ]


def _print_data_warnings(*sources: dict[str, Any] | None) -> None:
    """Print data-integrity warnings from summaries and/or raw payloads.

    stderr, not stdout, so piping `--csv`/`--json` into another tool stays clean
    while a human still sees that the numbers are incomplete. Accepts both
    analysis summaries (``warnings``) and transport payloads (``_warnings``).
    Silence here means every field was read as expected.
    """
    seen: set[str] = set()
    for source in sources:
        if not source:
            continue
        for key in ("warnings", "_warnings"):
            for warning in source.get(key) or []:
                if warning not in seen:
                    seen.add(warning)
                    print(f"warning: {warning}", file=sys.stderr)


def _hours_display(value: Any) -> Any:
    """Render an hour figure, distinguishing 'unknown' from a real zero."""
    return "unknown" if value is None else value


def _print_pending(pending: list[dict[str, Any]]) -> None:
    if not pending:
        return
    print()
    print(f"Awaiting first payment ({len(pending)})")
    print(format_table(pending, PENDING_COLUMNS))



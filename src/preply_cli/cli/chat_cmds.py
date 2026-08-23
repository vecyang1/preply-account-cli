"""Conversation commands: contacts, transcript, attachments.

An ambiguous name is an error rather than a silent pick -- the wrong choice
shows the wrong person's private conversation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import json
import sys

from ..browser import PreplyBrowserError
from ..client import PreplyClient
from ..formatting import format_table, shorten
from ._shared import _client, _load_snapshot, _print_data_warnings, _print_json


def _contact_rows(client: PreplyClient) -> list[dict[str, Any]]:
    nodes = (
        (client.chat_collocutors().get("messages") or {})
        .get("currentUser", {})
        .get("messageThreads", {})
        .get("nodes", [])
    )
    rows = []
    for node in nodes:
        collocutor = node.get("collocutor") or {}
        rows.append({
            "user_id": collocutor.get("id"),
            "name": collocutor.get("fullName") or collocutor.get("firstName") or "",
            "unread": node.get("unreadCount"),
        })
    rows.sort(key=lambda r: (-(r["unread"] or 0), str(r["name"])))
    return rows


def _print_contacts(client: PreplyClient) -> None:
    rows = _contact_rows(client)
    print(f"Conversations ({len(rows)})")
    print(format_table(rows, ["user_id", "name", "unread"]))
    print()
    print("Open one with: preply chat <name-or-user-id>")


def _resolve_collocutor(client: PreplyClient, who: str) -> tuple[int, str]:
    """Turn a tutor name or numeric user id into a collocutor id.

    A numeric argument is used directly. A name is matched case-insensitively
    against thread collocutors; an ambiguous match is an error rather than a
    silent pick, because the wrong choice silently shows the wrong person's
    private conversation.
    """
    if who.isdigit():
        return int(who), who
    nodes = (
        (client.chat_collocutors().get("messages") or {})
        .get("currentUser", {})
        .get("messageThreads", {})
        .get("nodes", [])
    )
    needle = who.strip().casefold()
    matches = []
    for node in nodes:
        collocutor = node.get("collocutor") or {}
        name = collocutor.get("fullName") or collocutor.get("firstName") or ""
        if collocutor.get("id") and needle in name.casefold():
            matches.append((int(collocutor["id"]), name))
    if not matches:
        known = ", ".join(
            sorted(
                (n.get("collocutor") or {}).get("firstName")
                or (n.get("collocutor") or {}).get("fullName")
                or "?"
                for n in nodes
            )
        )
        raise PreplyBrowserError(
            f"No conversation matches {who!r}. Known contacts: {known or 'none'}."
        )
    if len(matches) > 1:
        listing = ", ".join(f"{name} ({uid})" for uid, name in matches)
        raise PreplyBrowserError(
            f"{who!r} matches {len(matches)} contacts: {listing}. Use the numeric id."
        )
    return matches[0]


def cmd_chat(args: argparse.Namespace) -> None:
    from ..analysis import build_chat_summary, chat_file_rows, chat_rows
    from ..formatting import shorten

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        client = _client(args)
        if not (args.who or "").strip():
            _print_contacts(client)
            return
        user_id, _label = _resolve_collocutor(client, args.who)
        data = client.chat_thread(user_id, limit=args.limit)

    summary = build_chat_summary(data)
    rows = chat_rows(data)
    files = chat_file_rows(data)
    columns = ["time", "from", "body", "attachments"]

    if getattr(args, "files", False):
        file_columns = ["time", "from", "name", "mime", "size", "url"]
        if getattr(args, "json", False):
            _print_json({"summary": summary, "files": files})
            return
        if getattr(args, "csv", False):
            from ..formatting import format_csv
            print(format_csv(files, file_columns), end="")
            return
        print(f"Attachments ({len(files)}) with {summary['collocutor']}")
        print(format_table(files, file_columns))
        return

    if summary["unknown_sender"]:
        print(
            f"warning: {summary['unknown_sender']} message(s) could not be attributed "
            "to a sender and are shown as 'unknown'.",
            file=sys.stderr,
        )

    if getattr(args, "json", False):
        _print_json({"summary": summary, "messages": rows, "files": files})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, ["time", "from", "body", "attachments", "edited",
                                "removed", "system_type", "message_id"]), end="")
        return

    head = [
        {"metric": "with", "value": summary["collocutor"]},
        {"metric": "subject", "value": summary["subject"]},
        {"metric": "messages", "value": summary["message_count"]},
        {"metric": "by_sender", "value": json.dumps(summary["by_sender"], ensure_ascii=False)},
        {"metric": "attachments", "value": summary["attachments"]},
        {"metric": "unread", "value": summary["unread"]},
        {"metric": "from", "value": summary["earliest"]},
        {"metric": "to", "value": summary["latest"]},
        {"metric": "older_history_remains", "value": summary["has_older"]},
    ]
    print("Conversation")
    print(format_table(head, ["metric", "value"]))
    print()
    if args.full:
        for row in rows:
            marker = " (removed)" if row["removed"] else ""
            print(f"[{row['time']}] {row['from']}{marker}")
            print(f"    {row['body']}" if row["body"] else "    (no text)")
            for entry in row["files"]:
                size = f" ({entry['size']} bytes)" if entry.get("size") else ""
                print(f"    -- attachment: {entry['name'] or entry['file_id']}{size}")
                if entry["url"]:
                    print(f"       {entry['url']}")
            print()
    else:
        display = [dict(r, body=shorten(r["body"], 80),
                        attachments=r["file_names"] or (r["attachments"] or ""))
                   for r in rows]
        print(format_table(display, columns))
        print()
        print("Use --full for complete message text, --files to list attachments.")
    if summary["has_older"]:
        print(f"note: older history remains. Raise --limit (currently {args.limit}).")



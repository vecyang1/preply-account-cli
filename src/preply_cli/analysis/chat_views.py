"""Conversation aggregates: sender attribution and attachments.

Sender is measured, never inferred: `authorId` is null on about two thirds of
messages, so anything outside the four measured buckets renders as `unknown`
and is counted rather than attributed to a person."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ._common import _absolute_preply_url, _dict_nodes


SENDER_ME = "me"
SENDER_SYSTEM = "system"
SENDER_UNKNOWN = "unknown"


def chat_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Identity and thread metadata from a ChatAndMessages payload."""
    root = snapshot.get("chat") or {}
    chat = root.get("chat") or {}
    user = root.get("currentUser") or {}
    collocutor = chat.get("collocutorUser") or {}
    lead = chat.get("lead") or {}
    messages = chat.get("messages") or {}
    return {
        "me_id": user.get("id"),
        "collocutor_id": collocutor.get("id"),
        "collocutor_name": collocutor.get("firstName"),
        "collocutor_timezone": ((collocutor.get("profile") or {}).get("timezone") or {}).get("tzname"),
        "subject": ((lead.get("subject") or {}).get("translatedName")),
        "tutoring_id": (chat.get("tutoring") or {}).get("id"),
        "unread": (user.get("messageThread") or {}).get("unreadCount"),
        "has_older": bool(messages.get("hasNext") or messages.get("hasOlder")),
    }


def chat_message_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    chat = (snapshot.get("chat") or {}).get("chat") or {}
    return _dict_nodes((chat.get("messages") or {}).get("nodes"))


def _message_sender(node: dict[str, Any], me_id: Any, collocutor: str | None,
                    collocutor_id: Any) -> str:
    """Attribute one message, never guessing.

    Measured on a 50-message conversation (2026-08-14): every message fell into
    exactly one of four buckets - authored by me (5), by the collocutor (13),
    system-typed with a null author (24), and null-authored platform cards that
    carry an action ``button`` (8). Anything outside those is reported as
    ``unknown`` rather than being attributed to a person.
    """
    author = node.get("authorId")
    if author is not None:
        if me_id is not None and author == me_id:
            return SENDER_ME
        if collocutor_id is not None and author == collocutor_id:
            return collocutor or SENDER_UNKNOWN
        return f"user:{author}"
    if node.get("systemMessageType") or node.get("appreciationSystemMessageType"):
        return SENDER_SYSTEM
    if node.get("button"):
        return SENDER_SYSTEM
    return SENDER_UNKNOWN


def _file_entries(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Attachment metadata on one message, tolerant of null list elements."""
    entries = []
    for item in _dict_nodes(node.get("files")):
        url = _absolute_preply_url(item.get("downloadUrl") or item.get("url"))
        entries.append({
            "file_id": item.get("id"),
            "name": item.get("name") or "",
            "mime": item.get("mimeType") or "",
            "size": item.get("size"),
            "url": url,
        })
    return entries


def chat_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a conversation into display rows, oldest first (reading order)."""
    context = chat_context(snapshot)
    me_id = context["me_id"]
    collocutor = context["collocutor_name"]
    collocutor_id = context["collocutor_id"]
    rows = []
    for node in chat_message_nodes(snapshot):
        files = _file_entries(node)
        rows.append({
            "time": str(node.get("timePosted") or "")[:19].replace("T", " "),
            "message_id": node.get("id"),
            "from": _message_sender(node, me_id, collocutor, collocutor_id),
            "body": node.get("body") or "",
            "attachments": len(files),
            "files": files,
            "file_names": ", ".join(f["name"] for f in files if f["name"]),
            "edited": bool(node.get("timeEdited")),
            "removed": bool(node.get("isRemoved")),
            "system_type": node.get("systemMessageType") or "",
        })
    rows.sort(key=lambda r: str(r.get("time") or ""))
    return rows


def chat_file_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per attachment across the conversation, oldest first.

    Materials a tutor shared (homework, slides, recordings) are usually the
    part of a thread worth revisiting, and they are invisible in a message
    table that only prints a count.
    """
    rows = []
    for message in chat_rows(snapshot):
        for entry in message["files"]:
            rows.append({
                "time": message["time"],
                "from": message["from"],
                "name": entry["name"],
                "mime": entry["mime"],
                "size": entry["size"],
                "message_id": message["message_id"],
                "url": entry["url"],
            })
    return rows


def build_chat_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Counts per sender, plus whether older history remains unfetched."""
    context = chat_context(snapshot)
    rows = chat_rows(snapshot)
    by_sender: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        by_sender[row["from"]] += 1
    times = [r["time"] for r in rows if r["time"]]
    # The weakest link in the attribution rule is "null author + action button
    # => system". That held on every message observed, but it is an inference
    # from one conversation, so count it: if this number ever looks like real
    # correspondence rather than platform cards, the rule needs revisiting.
    button_attributed = sum(
        1 for node in chat_message_nodes(snapshot)
        if node.get("authorId") is None
        and not node.get("systemMessageType")
        and not node.get("appreciationSystemMessageType")
        and node.get("button")
    )
    return {
        "collocutor": context["collocutor_name"],
        "subject": context["subject"],
        "tutoring_id": context["tutoring_id"],
        "unread": context["unread"],
        "message_count": len(rows),
        "by_sender": dict(sorted(by_sender.items())),
        "attachments": sum(r["attachments"] for r in rows),
        "unknown_sender": by_sender.get(SENDER_UNKNOWN, 0),
        "system_by_button": button_attributed,
        "earliest": times[0] if times else None,
        "latest": times[-1] if times else None,
        "has_older": context["has_older"],
    }



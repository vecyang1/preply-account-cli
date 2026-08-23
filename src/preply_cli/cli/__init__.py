"""The `preply` command line.

Split by command group; this module keeps the parser, ``main()``, session
management, and the one gated mutation together, so the only path that changes
state stays in a single reviewed file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .. import __version__
from ..browser import PreplyBrowserError
from ..formatting import format_table, shorten
from ..public_profile import PublicProfileError
from ._shared import (
    SNAPSHOT_MARKERS,
    SnapshotError,
    _account_role,
    _client,
    _count,
    _emit,
    _hours_display,
    _load_snapshot,
    _no_transport_message,
    _print_data_warnings,
    _print_json,
)
from .chat_cmds import cmd_chat
from .learner_cmds import (
    cmd_balance,
    cmd_certificates,
    cmd_history,
    cmd_lessons,
    cmd_me,
    cmd_renewals,
    cmd_stats,
    cmd_tutors,
    cmd_upcoming,
)
from .review_cmds import cmd_tutor_reviews
from .tutor_cmds import (
    cmd_account,
    cmd_analyze,
    cmd_compare,
    cmd_messages,
    cmd_schedule,
    cmd_snapshot,
    cmd_status,
    cmd_student,
    cmd_students,
    cmd_wallet,
)

__all__ = ["build_parser", "main", "SnapshotError", "SNAPSHOT_MARKERS"]


def _confirmation_lesson(data: dict[str, Any]) -> dict[str, Any] | None:
    confirmation = data.get("confirmation") or data
    lesson = confirmation.get("myNextLessonForConfirmation")
    return lesson if isinstance(lesson, dict) else None


def _confirmation_language(data: dict[str, Any]) -> str:
    confirmation = data.get("confirmation") or data
    language = (
        (confirmation.get("currentUser") or {})
        .get("profile", {})
        .get("language", {})
        .get("code")
    )
    return str(language or "en")[:2]


def _confirmation_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    lesson = _confirmation_lesson(data)
    if not lesson:
        return []
    tutor_user = ((lesson.get("tutor") or {}).get("user") or {})
    tutoring = lesson.get("tutoring") or {}
    subject = ((tutoring.get("lead") or {}).get("subject") or {})
    lesson_id = lesson.get("id")
    language = _confirmation_language(data)
    return [
        {
            "lesson_id": lesson_id,
            "datetime": lesson.get("datetime"),
            "tutor": tutor_user.get("firstName"),
            "status": lesson.get("status"),
            "first_lesson": lesson.get("isFirstLesson"),
            "tutoring_id": tutoring.get("id"),
            "subject": subject.get("alias"),
            "report_url": f"/{language}/lessons/report/{lesson_id}?src=confirmation_modal",
        }
    ]


def _validate_confirmation_target(row: dict[str, Any], args: argparse.Namespace) -> None:
    if args.lesson_id is not None and int(row.get("lesson_id") or -1) != int(args.lesson_id):
        raise PreplyBrowserError(
            f"Pending lesson id is {row.get('lesson_id')}, not requested lesson id {args.lesson_id}."
        )
    if args.expect_tutor:
        actual = str(row.get("tutor") or "").casefold()
        expected = args.expect_tutor.casefold()
        if expected not in actual:
            raise PreplyBrowserError(
                f"Pending confirmation tutor is {row.get('tutor')!r}, not expected tutor {args.expect_tutor!r}."
            )
    if args.expect_datetime:
        actual_datetime = str(row.get("datetime") or "")
        if args.expect_datetime not in actual_datetime:
            raise PreplyBrowserError(
                f"Pending confirmation datetime is {actual_datetime!r}, not expected datetime {args.expect_datetime!r}."
            )


def cmd_confirmation(args: argparse.Namespace) -> None:
    # Refuse the unconfirmed mutation *before* resolving a credential or
    # touching the network. Checking it after the fetch meant `--confirm`
    # without `--yes` paid for a 1Password unlock and a round trip only to say
    # no -- and on a broken transport it failed as a transport error, hiding a
    # plain usage mistake behind an unrelated diagnosis.
    if getattr(args, "confirm", False) and not getattr(args, "yes", False):
        raise PreplyBrowserError("Refusing to confirm lesson without --yes.")
    client = _client(args)
    data = client.next_lesson_confirmation()
    rows = _confirmation_rows(data)
    if not rows:
        if getattr(args, "json", False):
            _print_json(data)
        else:
            print("No pending lesson confirmation.")
        return

    row = rows[0]
    _validate_confirmation_target(row, args)
    if not args.confirm:
        _emit(
            data,
            rows,
            ["lesson_id", "datetime", "tutor", "status", "first_lesson", "tutoring_id", "subject", "report_url"],
            args,
        )
        return

    result = client.confirm_lesson(int(row["lesson_id"]))
    confirm_lesson = ((result.get("confirm") or {}).get("confirmLesson") or {})
    confirmed = confirm_lesson.get("lesson") or {}
    output = [
        {
            "ok": confirm_lesson.get("ok"),
            "lesson_id": confirmed.get("id") or row.get("lesson_id"),
            "status": confirmed.get("status"),
            "has_issue": confirmed.get("hasIssue"),
            "tutor": row.get("tutor"),
            "datetime": row.get("datetime"),
        }
    ]
    if getattr(args, "json", False):
        _print_json({"selected": row, "result": result})
    elif getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(output, ["ok", "lesson_id", "status", "has_issue", "tutor", "datetime"]), end="")
    else:
        print("Confirmed lesson")
        print(format_table(output, ["ok", "lesson_id", "status", "has_issue", "tutor", "datetime"]))


def cmd_session(args: argparse.Namespace) -> None:
    from ..capture import capture_sessions, session_status
    from ..session_store import list_sessions

    if args.action == "capture":
        results = capture_sessions(args.profile)
        rows = [r.as_row() for r in results]
        columns = ["profile", "status", "name", "role", "account_id", "item_id", "detail"]
        if args.json:
            _print_json(rows)
            return
        if args.csv:
            from ..formatting import format_csv

            print(format_csv(rows, columns), end="")
            return
        print(format_table(rows, columns))
        stored = [r for r in results if r.status == "stored"]
        stale = [r for r in results if r.status == "stale"]
        print()
        print(f"Stored {len(stored)} live session(s); {len(stale)} profile(s) logged out server-side.")
        if stale:
            print("Re-log-in those accounts in Chrome, then rerun `preply session capture`.")
        return

    if args.action == "list":
        sessions = list_sessions()
        rows = [
            {"item_id": s.item_id, "name": s.name or "", "role": s.role or "",
             "account_id": s.account_id or "", "title": s.title}
            for s in sessions
        ]
        columns = ["item_id", "name", "role", "account_id", "title"]
        if args.json:
            _print_json(rows)
            return
        if args.csv:
            from ..formatting import format_csv

            print(format_csv(rows, columns), end="")
            return
        print(format_table(rows, columns))
        return

    # status
    rows = session_status()
    columns = ["item_id", "name", "role", "account_id", "live", "detail"]
    if args.json:
        _print_json(rows)
        return
    if args.csv:
        from ..formatting import format_csv

        print(format_csv(rows, columns), end="")
        return
    print(format_table(rows, columns))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preply",
        description="Preply account CLI via logged-in Chrome tabs. Read-only by default; confirmation actions require --yes.",
    )
    parser.add_argument("--version", action="version", version=f"preply {__version__}")
    parser.add_argument("--role", choices=["any", "tutor", "learner"], default="any", help="Choose a matching account (stored session or logged-in Preply tab).")
    parser.add_argument("--user-id", type=int, help="Choose a specific Preply user id when several accounts are available.")
    parser.add_argument("--name", help="Choose an account whose name contains this text.")
    parser.add_argument(
        "--transport",
        choices=["auto", "direct", "browser"],
        default="auto",
        help="How to reach Preply: 'direct' replays a 1Password-stored session over HTTPS (unattended); 'browser' uses a logged-in Chrome tab; 'auto' uses direct when a matching stored session exists and falls back to browser only when none is stored (a stored-but-stale session is a clear error telling you to re-capture, not a silent fallback).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    account = sub.add_parser("account", help="Show which Preply tab/account the CLI will use.")
    account.add_argument("--json", action="store_true")
    account.set_defaults(func=cmd_account)

    status = sub.add_parser("status", help="Show account totals, wallet balance, and loaded student revenue.")
    status.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    status.add_argument("--limit", type=_count, default=100)
    status.add_argument("--json", action="store_true")
    status.add_argument("--csv", action="store_true", help="Format output as CSV.")
    status.set_defaults(func=cmd_status)

    students = sub.add_parser("students", help="List tutor students with price, lesson, and revenue fields.")
    students.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    students.add_argument("--limit", type=_count, default=100)
    students.add_argument("--offset", type=int, default=0)
    students.add_argument("--json", action="store_true")
    students.add_argument("--csv", action="store_true", help="Format output as CSV.")
    students.set_defaults(func=cmd_students)

    wallet = sub.add_parser("wallet", help="Show tutor wallet balance and payout method.")
    wallet.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    wallet.add_argument("--json", action="store_true")
    wallet.add_argument("--csv", action="store_true", help="Format output as CSV.")
    wallet.set_defaults(func=cmd_wallet)

    schedule = sub.add_parser("schedule", help="Show upcoming class schedule.")
    schedule.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    schedule.add_argument("--days", type=_count, default=14)
    schedule.add_argument("--timezone")
    schedule.add_argument("--json", action="store_true")
    schedule.add_argument("--csv", action="store_true", help="Format output as CSV.")
    schedule.set_defaults(func=cmd_schedule)

    messages = sub.add_parser("messages", help="Show message thread summaries and last message previews.")
    messages.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    messages.add_argument("--limit", type=_count, default=20)
    messages.add_argument("--json", action="store_true")
    messages.add_argument("--csv", action="store_true", help="Format output as CSV.")
    messages.set_defaults(func=cmd_messages)

    history = sub.add_parser("history", help="Show learner payment history from settings/history where available.")
    history.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    history.add_argument("--limit", type=_count, default=100)
    history.add_argument("--json", action="store_true")
    history.add_argument("--csv", action="store_true", help="Format output as CSV.")
    history.set_defaults(func=cmd_history)

    lessons = sub.add_parser("lessons", help="Learner completed-lesson ledger (date, subject, tutor, status, paid, rating).")
    lessons.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    lessons.add_argument("--limit", type=_count, default=50)
    lessons.add_argument("--offset", type=int, default=0)
    lessons.add_argument("--json", action="store_true")
    lessons.add_argument("--csv", action="store_true", help="Format output as CSV.")
    lessons.set_defaults(func=cmd_lessons)

    upcoming = sub.add_parser("upcoming", help="Learner upcoming lessons (booked lessons and recurrent reservations).")
    upcoming.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    upcoming.add_argument("--json", action="store_true")
    upcoming.add_argument("--csv", action="store_true", help="Format output as CSV.")
    upcoming.set_defaults(func=cmd_upcoming)

    tutors = sub.add_parser("tutors", help="Learner active tutors and subscriptions (price, lessons taken, refill state).")
    tutors.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    tutors.add_argument("--json", action="store_true")
    tutors.add_argument("--csv", action="store_true", help="Format output as CSV.")
    tutors.set_defaults(func=cmd_tutors)

    stats = sub.add_parser("stats", help="Learner lifetime learning stats (streak, lessons completed, practices).")
    stats.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    stats.add_argument("--json", action="store_true")
    stats.add_argument("--csv", action="store_true", help="Format output as CSV.")
    stats.set_defaults(func=cmd_stats)

    balance = sub.add_parser(
        "balance",
        help="Learner hour balance: banked hours, unscheduled (idle) hours, and the next charge date per tutor.",
    )
    balance.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    balance.add_argument("--json", action="store_true")
    balance.add_argument("--csv", action="store_true", help="Format output as CSV.")
    balance.set_defaults(func=cmd_balance)

    renewals = sub.add_parser(
        "renewals",
        help="Learner upcoming subscription charges: amount, currency, date, per tutor.",
    )
    renewals.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    renewals.add_argument(
        "--all",
        action="store_true",
        help="Include stopped subscriptions (no upcoming charge). They are always counted in the summary.",
    )
    renewals.add_argument("--json", action="store_true")
    renewals.add_argument("--csv", action="store_true", help="Format output as CSV.")
    renewals.set_defaults(func=cmd_renewals)

    certificates = sub.add_parser(
        "certificates",
        help="Learner achievement certificates per subject, with download links.",
    )
    certificates.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    certificates.add_argument("--json", action="store_true")
    certificates.add_argument("--csv", action="store_true", help="Format output as CSV.")
    certificates.set_defaults(func=cmd_certificates)

    me = sub.add_parser(
        "me",
        help="One-screen learner dashboard: identity, stats, balance, upcoming lessons, charges, and unread messages.",
    )
    me.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    me.add_argument("--recent", type=_count, default=5, help="How many recent lessons to show.")
    me.add_argument("--json", action="store_true")
    me.add_argument("--csv", action="store_true", help="Format the balance rows as CSV.")
    me.set_defaults(func=cmd_me)

    chat = sub.add_parser(
        "chat",
        help="Full conversation history with one tutor, over GraphQL (no Agora needed).",
    )
    chat.add_argument("who", nargs="?", default="",
                      help="Tutor name (substring, case-insensitive) or numeric Preply user id.")
    chat.add_argument("-f", "--file", help="Path to a saved conversation JSON file to run offline.")
    chat.add_argument("--limit", type=_count, default=50, help="Maximum messages to fetch (paginates into older history).")
    chat.add_argument("--full", action="store_true", help="Print complete message text, with attachment names and URLs.")
    chat.add_argument("--files", action="store_true", help="List only the attachments shared in this conversation.")
    chat.add_argument("--json", action="store_true")
    chat.add_argument("--csv", action="store_true", help="Format output as CSV.")
    chat.set_defaults(func=cmd_chat)

    confirmation = sub.add_parser(
        "confirmation",
        help="Show or explicitly confirm Preply's pending 'Did your lesson happen?' prompt.",
    )
    confirmation.add_argument("--confirm", action="store_true", help="Confirm the pending lesson.")
    confirmation.add_argument("--yes", action="store_true", help="Required with --confirm because this pays the tutor.")
    confirmation.add_argument("--lesson-id", type=int, help="Refuse to act unless the pending lesson id matches.")
    confirmation.add_argument("--expect-tutor", help="Refuse to act unless the pending tutor name contains this text.")
    confirmation.add_argument("--expect-datetime", help="Refuse to act unless the pending lesson datetime contains this text.")
    confirmation.add_argument("--json", action="store_true")
    confirmation.add_argument("--csv", action="store_true", help="Format output as CSV.")
    confirmation.set_defaults(func=cmd_confirmation)

    tutor_reviews = sub.add_parser(
        "tutor-reviews",
        help="Read and summarize public reviews from a Preply tutor profile URL, tutor id, or saved HTML/JSON.",
    )
    tutor_reviews.add_argument("source", help="Preply tutor URL, tutor id, or saved public profile HTML/JSON file.")
    tutor_reviews.add_argument("--limit", type=_count, help="Number of review rows to print. Defaults to all reviews.")
    tutor_reviews.add_argument("--timeout", type=int, default=30, help="Network timeout in seconds for public profile fetch.")
    tutor_reviews.add_argument("--json", action="store_true")
    tutor_reviews.add_argument("--csv", action="store_true", help="Format review rows as CSV.")
    tutor_reviews.set_defaults(func=cmd_tutor_reviews)

    student = sub.add_parser("student", help="Show per-student statistics, lessons, and revenue history by tutoring id.")
    student.add_argument("tutoring_id", type=int)
    student.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    student.add_argument("--past-limit", type=_count, default=20)
    student.add_argument("--lesson-insights", type=int, help="Fetch lesson insight headline for a lesson id.")
    student.add_argument("--json", action="store_true")
    student.add_argument("--csv", action="store_true", help="Format output as CSV.")
    student.set_defaults(func=cmd_student)

    snapshot = sub.add_parser("snapshot", help="Save a local account snapshot for later comparison.")
    snapshot.add_argument("--out", default="data/preply-snapshot.json")
    snapshot.add_argument("--account-label", default="")
    snapshot.add_argument("--limit", type=_count, default=100)
    snapshot.add_argument("--days", type=_count, default=30)
    snapshot.add_argument("--timezone")
    snapshot.set_defaults(func=cmd_snapshot)

    analyze = sub.add_parser("analyze", help="Summarize revenue, classes, prices, and a lesson timeline.")
    analyze.add_argument("-f", "--file", help="Path to a saved snapshot JSON file to run offline.")
    analyze.add_argument("--limit", type=_count, default=100)
    analyze.add_argument("--days", type=_count, default=30)
    analyze.add_argument("--timezone")
    analyze.add_argument("--deep", action="store_true", help="Fetch per-student past lessons for a richer timeline.")
    analyze.add_argument("--past-limit", type=_count, default=10)
    analyze.add_argument("--timeline-limit", type=_count, default=30)
    analyze.add_argument("--json", action="store_true")
    analyze.add_argument("--csv", action="store_true", help="Format output as CSV.")
    analyze.set_defaults(func=cmd_analyze)

    compare = sub.add_parser("compare", help="Compare saved snapshots from different Preply accounts.")
    compare.add_argument("snapshots", nargs="+")
    compare.add_argument("--json", action="store_true")
    compare.add_argument("--csv", action="store_true", help="Format output as CSV.")
    compare.set_defaults(func=cmd_compare)

    session = sub.add_parser(
        "session",
        help="Manage 1Password-stored Preply sessions for unattended direct access.",
    )
    session.add_argument(
        "action",
        choices=["capture", "list", "status"],
        help="capture: extract live Chrome sessions into 1Password; list: show stored sessions; status: probe each stored session for liveness.",
    )
    session.add_argument(
        "--profile",
        action="append",
        help="Restrict capture to specific Chrome profile directory name(s), e.g. 'Profile 2'. Repeatable. Default: all profiles.",
    )
    session.add_argument("--json", action="store_true")
    session.add_argument("--csv", action="store_true", help="Format output as CSV.")
    session.set_defaults(func=cmd_session)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from ..chrome_cookies import ChromeCookieError
    from ..direct import PreplyDirectError
    from ..session_store import SessionStoreError

    try:
        args.func(args)
    except (PreplyBrowserError, PublicProfileError, PreplyDirectError,
            SessionStoreError, ChromeCookieError, SnapshotError) as exc:
        parser.exit(2, f"preply: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "preply: interrupted.\n")
    return 0

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import __version__
from .analysis import build_account_summary, build_payment_summary, build_timeline, payment_nodes, student_nodes
from .browser import BrowserTargetSelector, PreplyBrowserError
from .client import PreplyClient
from .formatting import format_table, money, shorten


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _client(args: argparse.Namespace) -> PreplyClient:
    selector = BrowserTargetSelector(role=args.role, user_id=args.user_id, name=args.name)
    return PreplyClient(selector=selector)


def _account_role(data: dict[str, Any]) -> str:
    account = data.get("_account") or {}
    if account.get("role"):
        return str(account["role"])
    current = (data.get("account") or {}).get("currentUser") or {}
    return "tutor" if current.get("tutor") else "learner"


def _student_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for student in student_nodes(snapshot):
        user = (student.get("client") or {}).get("user") or {}
        subject = (student.get("lead") or {}).get("subject") or {}
        rows.append(
            {
                "id": student.get("id"),
                "student": student.get("clientName") or user.get("fullName"),
                "status": student.get("status"),
                "subject": subject.get("translatedName") or subject.get("alias"),
                "lessons": student.get("confirmedLessonsCount"),
                "hours": student.get("hours"),
                "price": money(student.get("pricePerHourUsd")),
                "earned": money(student.get("totalTutorRevenue")),
                "timezone": ((user.get("profile") or {}).get("timezone") or {}).get("tzname"),
            }
        )
    return rows


def _schedule_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = (
        data.get("schedule", {})
        .get("currentUser", {})
        .get("tutor", {})
        .get("calendar", {})
        .get("nodes", [])
    )
    rows = []
    for node in nodes:
        lesson = node.get("lesson") or {}
        if not lesson.get("id"):
            continue
        user = ((lesson.get("client") or {}).get("user") or {})
        tutoring = lesson.get("tutoring") or {}
        rows.append(
            {
                "start": node.get("dateStart"),
                "end": node.get("dateEnd"),
                "student": user.get("fullName") or tutoring.get("clientName"),
                "status": lesson.get("status"),
                "lesson_id": lesson.get("id"),
                "tutoring_id": tutoring.get("id"),
                "duration": lesson.get("duration"),
            }
        )
    return rows


def _message_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = (
        data.get("messages", {})
        .get("currentUser", {})
        .get("messageThreads", {})
        .get("nodes", [])
    )
    rows = []
    for node in nodes:
        collocutor = node.get("collocutor") or {}
        last = node.get("lastMessage") or {}
        rows.append(
            {
                "thread_id": node.get("id"),
                "student": collocutor.get("fullName") or collocutor.get("firstName"),
                "unread": node.get("unreadCount"),
                "labels": ",".join(node.get("labels") or []),
                "last_author": last.get("authorId"),
                "last_message": shorten(last.get("body"), 90),
            }
        )
    return rows


def _payment_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for payment in payment_nodes(data):
        rows.append(
            {
                "id": payment.get("id"),
                "time": payment.get("time"),
                "subject": payment.get("subject"),
                "tutor": payment.get("tutor"),
                "hours": payment.get("hours"),
                "amount": money(payment.get("amount"), payment.get("currencyCode") or "USD"),
                "refundable": payment.get("studentCanRefund"),
                "receipt": payment.get("receiptUrl"),
            }
        )
    return rows


def _emit(data: Any, rows: list[dict[str, Any]] | None, columns: list[str], as_json: bool) -> None:
    if as_json:
        _print_json(data)
    else:
        print(format_table(rows or [], columns))


def cmd_status(args: argparse.Namespace) -> None:
    client = _client(args)
    data = client.overview(limit=args.limit)
    summary = build_account_summary(data)
    account = data.get("_account") or {}
    if args.json:
        _print_json({"summary": summary, "raw": data})
        return
    rows = [
        {"metric": "account_role", "value": account.get("role")},
        {"metric": "account_name", "value": account.get("name")},
        {"metric": "user_id", "value": account.get("userId")},
        {"metric": "students", "value": summary["student_total"]},
        {"metric": "loaded_students", "value": summary["loaded_students"]},
        {"metric": "confirmed_lessons", "value": summary["confirmed_lessons_total"]},
        {"metric": "student_revenue_total", "value": money(summary["student_revenue_total_usd"])},
        {"metric": "wallet_balance", "value": money(summary["wallet_balance"])},
        {"metric": "price_min", "value": money(summary["price_range_usd"]["min"])},
        {"metric": "price_max", "value": money(summary["price_range_usd"]["max"])},
        {"metric": "statuses", "value": json.dumps(summary["status_counts"], sort_keys=True)},
    ]
    print(format_table(rows, ["metric", "value"]))


def cmd_students(args: argparse.Namespace) -> None:
    data = _client(args).students(limit=args.limit, offset=args.offset)
    rows = _student_rows(data)
    _emit(data, rows, ["id", "student", "status", "subject", "lessons", "hours", "price", "earned", "timezone"], args.json)


def cmd_wallet(args: argparse.Namespace) -> None:
    data = _client(args).wallet()
    wallet = (data.get("wallet") or {}).get("currentUser") or {}
    if args.json:
        _print_json(data)
        return
    rows = [
        {"metric": "user_id", "value": wallet.get("id")},
        {"metric": "tutor_id", "value": (wallet.get("tutor") or {}).get("id")},
        {"metric": "last_payout_method", "value": (wallet.get("tutor") or {}).get("lastPayoutMethod")},
        {"metric": "currency", "value": ((wallet.get("profile") or {}).get("currency") or {}).get("code")},
        {"metric": "balance", "value": money((wallet.get("wallet") or {}).get("balance"))},
    ]
    print(format_table(rows, ["metric", "value"]))


def cmd_schedule(args: argparse.Namespace) -> None:
    data = _client(args).schedule(days=args.days, tzname=args.timezone)
    rows = _schedule_rows(data)
    _emit(data, rows, ["start", "end", "student", "status", "lesson_id", "tutoring_id", "duration"], args.json)


def cmd_messages(args: argparse.Namespace) -> None:
    data = _client(args).messages()
    rows = _message_rows(data)[: args.limit]
    _emit(data, rows, ["thread_id", "student", "unread", "labels", "last_author", "last_message"], args.json)


def cmd_student(args: argparse.Namespace) -> None:
    data = _client(args).student_detail(
        tutoring_id=args.tutoring_id,
        past_limit=args.past_limit,
        include_insights_for_lesson_id=args.lesson_insights,
    )
    if args.json:
        _print_json(data)
        return
    stats = (data.get("statistics") or {}).get("tutoring") or {}
    details = (data.get("details") or {}).get("tutoring") or {}
    rows = [
        {"metric": "student", "value": details.get("clientName")},
        {"metric": "status", "value": details.get("status") or stats.get("status")},
        {"metric": "lessons", "value": stats.get("lessonsCount")},
        {"metric": "hours", "value": stats.get("hours")},
        {"metric": "total_prepaid_hours", "value": stats.get("totalPrepaidHours")},
        {"metric": "total_revenue", "value": money(stats.get("totalTutorRevenue"))},
        {"metric": "price", "value": money(((stats.get("price") or {}).get("value")))},
        {"metric": "month_since_start", "value": stats.get("monthSinceStart")},
    ]
    print(format_table(rows, ["metric", "value"]))


def cmd_snapshot(args: argparse.Namespace) -> None:
    client = _client(args)
    account_probe = client.account()
    role = _account_role(account_probe)
    if role == "learner":
        data = client.payment_history(limit=args.limit)
        data["summary"] = build_payment_summary(data)
    else:
        data = client.overview(limit=args.limit)
        data["schedule"] = client.schedule(days=args.days, tzname=args.timezone).get("schedule")
        data["summary"] = build_account_summary(data)
    data["account_label"] = args.account_label
    data["account_role"] = role
    path = Path(args.out).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    print(str(path))


def cmd_analyze(args: argparse.Namespace) -> None:
    client = _client(args)
    data = client.overview(limit=args.limit)
    data["schedule"] = client.schedule(days=args.days, tzname=args.timezone).get("schedule")
    if args.deep:
        details: dict[str, Any] = {}
        for student in student_nodes(data):
            tutoring_id = student.get("id")
            if tutoring_id:
                details[str(tutoring_id)] = client.student_detail(int(tutoring_id), past_limit=args.past_limit)
        data["student_details"] = details
    summary = build_account_summary(data)
    timeline = build_timeline(data)
    if args.json:
        _print_json({"summary": summary, "timeline": timeline, "raw": data})
        return
    print("Summary")
    print(format_table([{"metric": key, "value": value} for key, value in summary.items()], ["metric", "value"]))
    print()
    print("Timeline")
    print(format_table(timeline[: args.timeline_limit], ["kind", "datetime", "student_name", "status", "lesson_id", "tutoring_id", "duration"]))


def cmd_compare(args: argparse.Namespace) -> None:
    rows = []
    for item in args.snapshots:
        path = Path(item).expanduser().resolve()
        snapshot = json.loads(path.read_text())
        role = snapshot.get("account_role") or _account_role(snapshot)
        summary = snapshot.get("summary") or (
            build_payment_summary(snapshot) if role == "learner" else build_account_summary(snapshot)
        )
        rows.append(
            {
                "account": snapshot.get("account_label") or path.stem,
                "role": role,
                "students": summary.get("student_total", ""),
                "lessons": summary.get("confirmed_lessons_total", ""),
                "payments": summary.get("payment_count", ""),
                "earned": money(summary.get("student_revenue_total_usd")),
                "spent": money(summary.get("spent_total")),
                "wallet": money(summary.get("wallet_balance")),
            }
        )
    if args.json:
        _print_json(rows)
    else:
        print(format_table(rows, ["account", "role", "students", "lessons", "payments", "earned", "spent", "wallet"]))


def cmd_account(args: argparse.Namespace) -> None:
    data = _client(args).account()
    if args.json:
        _print_json(data)
        return
    account = data.get("_account") or {}
    rows = [
        {"metric": "role", "value": account.get("role")},
        {"metric": "name", "value": account.get("name")},
        {"metric": "user_id", "value": account.get("userId")},
        {"metric": "tutor_id", "value": account.get("tutorId")},
    ]
    print(format_table(rows, ["metric", "value"]))


def cmd_history(args: argparse.Namespace) -> None:
    data = _client(args).payment_history(limit=args.limit)
    summary = build_payment_summary(data)
    if args.json:
        _print_json({"summary": summary, "raw": data})
        return
    print("Summary")
    print(format_table([{"metric": key, "value": value} for key, value in summary.items()], ["metric", "value"]))
    print()
    print("Payments")
    print(format_table(_payment_rows(data), ["id", "time", "subject", "tutor", "hours", "amount", "refundable"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="preply", description="Read-only Preply account CLI via logged-in Chrome tabs.")
    parser.add_argument("--version", action="version", version=f"preply {__version__}")
    parser.add_argument("--role", choices=["any", "tutor", "learner"], default="any", help="Choose a matching logged-in Preply tab.")
    parser.add_argument("--user-id", type=int, help="Choose a specific Preply user id when several tabs are open.")
    parser.add_argument("--name", help="Choose a Preply tab whose account name contains this text.")
    sub = parser.add_subparsers(dest="command", required=True)

    account = sub.add_parser("account", help="Show which Preply tab/account the CLI will use.")
    account.add_argument("--json", action="store_true")
    account.set_defaults(func=cmd_account)

    status = sub.add_parser("status", help="Show account totals, wallet balance, and loaded student revenue.")
    status.add_argument("--limit", type=int, default=100)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    students = sub.add_parser("students", help="List tutor students with price, lesson, and revenue fields.")
    students.add_argument("--limit", type=int, default=100)
    students.add_argument("--offset", type=int, default=0)
    students.add_argument("--json", action="store_true")
    students.set_defaults(func=cmd_students)

    wallet = sub.add_parser("wallet", help="Show tutor wallet balance and payout method.")
    wallet.add_argument("--json", action="store_true")
    wallet.set_defaults(func=cmd_wallet)

    schedule = sub.add_parser("schedule", help="Show upcoming class schedule.")
    schedule.add_argument("--days", type=int, default=14)
    schedule.add_argument("--timezone")
    schedule.add_argument("--json", action="store_true")
    schedule.set_defaults(func=cmd_schedule)

    messages = sub.add_parser("messages", help="Show message thread summaries and last message previews.")
    messages.add_argument("--limit", type=int, default=20)
    messages.add_argument("--json", action="store_true")
    messages.set_defaults(func=cmd_messages)

    history = sub.add_parser("history", help="Show learner payment history from settings/history where available.")
    history.add_argument("--limit", type=int, default=100)
    history.add_argument("--json", action="store_true")
    history.set_defaults(func=cmd_history)

    student = sub.add_parser("student", help="Show per-student statistics, lessons, and revenue history by tutoring id.")
    student.add_argument("tutoring_id", type=int)
    student.add_argument("--past-limit", type=int, default=20)
    student.add_argument("--lesson-insights", type=int, help="Fetch lesson insight headline for a lesson id.")
    student.add_argument("--json", action="store_true")
    student.set_defaults(func=cmd_student)

    snapshot = sub.add_parser("snapshot", help="Save a local account snapshot for later comparison.")
    snapshot.add_argument("--out", default="data/preply-snapshot.json")
    snapshot.add_argument("--account-label", default="")
    snapshot.add_argument("--limit", type=int, default=100)
    snapshot.add_argument("--days", type=int, default=30)
    snapshot.add_argument("--timezone")
    snapshot.set_defaults(func=cmd_snapshot)

    analyze = sub.add_parser("analyze", help="Summarize revenue, classes, prices, and a lesson timeline.")
    analyze.add_argument("--limit", type=int, default=100)
    analyze.add_argument("--days", type=int, default=30)
    analyze.add_argument("--timezone")
    analyze.add_argument("--deep", action="store_true", help="Fetch per-student past lessons for a richer timeline.")
    analyze.add_argument("--past-limit", type=int, default=10)
    analyze.add_argument("--timeline-limit", type=int, default=30)
    analyze.add_argument("--json", action="store_true")
    analyze.set_defaults(func=cmd_analyze)

    compare = sub.add_parser("compare", help="Compare saved snapshots from different Preply accounts.")
    compare.add_argument("snapshots", nargs="+")
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PreplyBrowserError as exc:
        parser.exit(2, f"preply: {exc}\n")
    return 0

"""Tutor-side commands.

None of these are verified against a live account: no tutor session exists, so
treat both their shapes and their totals as unconfirmed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..analysis import (
    build_account_summary,
    build_payment_summary,
    build_timeline,
    payment_nodes,
    student_nodes,
)
from ..formatting import format_table, money, shorten
from ._shared import (
    _account_role,
    _client,
    _emit,
    _load_snapshot,
    _money_or_unknown,
    _print_data_warnings,
    _print_json,
    _summary_rows,
)
import sys


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
    schedule_data = data.get("schedule") if isinstance(data.get("schedule"), dict) else data
    current_user = schedule_data.get("currentUser") if isinstance(schedule_data, dict) else {}
    tutor = current_user.get("tutor") if isinstance(current_user, dict) else None
    if not isinstance(tutor, dict):
        return []
    nodes = (tutor.get("calendar") or {}).get("nodes", [])
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


def cmd_status(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        client = _client(args)
        data = client.overview(limit=args.limit)
    summary = data.get("summary") or build_account_summary(data)
    _print_data_warnings(summary, data)
    account = data.get("_account") or (data.get("account") or {}).get("currentUser") or {}
    if getattr(args, "json", False):
        _print_json({"summary": summary, "raw": data})
        return
    rows = [
        {"metric": "account_role", "value": account.get("role") or account.get("preplyCliRole")},
        {"metric": "account_name", "value": account.get("name") or account.get("fullName") or account.get("firstName")},
        {"metric": "user_id", "value": account.get("userId") or account.get("id")},
        {"metric": "students", "value": summary.get("student_total")},
        {"metric": "loaded_students", "value": summary.get("loaded_students")},
        {"metric": "confirmed_lessons", "value": summary.get("confirmed_lessons_total")},
        {"metric": "student_revenue_total", "value": money(summary.get("student_revenue_total_usd"))},
        {"metric": "wallet_balance", "value": money(summary.get("wallet_balance"))},
        {"metric": "price_min", "value": money((summary.get("price_range_usd") or {}).get("min"))},
        {"metric": "price_max", "value": money((summary.get("price_range_usd") or {}).get("max"))},
        {"metric": "statuses", "value": json.dumps(summary.get("status_counts", {}), sort_keys=True)},
    ]
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, ["metric", "value"]), end="")
    else:
        print(format_table(rows, ["metric", "value"]))


def cmd_students(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).students(limit=args.limit, offset=args.offset)
    rows = _student_rows(data)
    _emit(data, rows, ["id", "student", "status", "subject", "lessons", "hours", "price", "earned", "timezone"], args)


def cmd_wallet(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).wallet()
    wallet_user = (data.get("wallet") or {}).get("currentUser") or data.get("currentUser") or {}
    wallet = wallet_user.get("wallet") or {}
    tutor = wallet_user.get("tutor") or {}
    profile = wallet_user.get("profile") or {}
    if getattr(args, "json", False):
        _print_json(data)
        return
    rows = [
        {"metric": "user_id", "value": wallet_user.get("id")},
        {"metric": "tutor_id", "value": tutor.get("id")},
        {"metric": "last_payout_method", "value": tutor.get("lastPayoutMethod")},
        {"metric": "currency", "value": (profile.get("currency") or {}).get("code")},
        {"metric": "balance", "value": money(wallet.get("balance"))},
    ]
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, ["metric", "value"]), end="")
    else:
        print(format_table(rows, ["metric", "value"]))


def cmd_schedule(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).schedule(days=args.days, tzname=args.timezone)
    rows = _schedule_rows(data)
    if not rows and not getattr(args, "json", False) and not getattr(args, "csv", False):
        schedule_data = data.get("schedule") if isinstance(data.get("schedule"), dict) else data
        current_user = schedule_data.get("currentUser") if isinstance(schedule_data, dict) else {}
        if not current_user.get("tutor"):
            print("Current account is a learner (no tutor teaching schedule).")
            print("• For your booked lessons as a learner: run `preply upcoming`")
            print("• For a tutor's public booking schedule: run `preply tutor-schedule <tutor_id_or_url>`")
            return
    _emit(data, rows, ["start", "end", "student", "status", "lesson_id", "tutoring_id", "duration"], args)


def cmd_messages(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).messages()
    rows = _message_rows(data)[: args.limit]
    _emit(data, rows, ["thread_id", "student", "unread", "labels", "last_author", "last_message"], args)


def cmd_student(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        snapshot = _load_snapshot(path)
        if "student_details" in snapshot:
            data = snapshot["student_details"].get(str(args.tutoring_id)) or {}
        else:
            data = snapshot
    else:
        data = _client(args).student_detail(
            tutoring_id=args.tutoring_id,
            past_limit=args.past_limit,
            include_insights_for_lesson_id=args.lesson_insights,
        )
    if getattr(args, "json", False):
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
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, ["metric", "value"]), end="")
    else:
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
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
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
    summary = data.get("summary") or build_account_summary(data)
    _print_data_warnings(summary, data)
    timeline = build_timeline(data)
    if getattr(args, "json", False):
        _print_json({"summary": summary, "timeline": timeline, "raw": data})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(timeline[: args.timeline_limit], ["kind", "datetime", "student_name", "status", "lesson_id", "tutoring_id", "duration"]), end="")
        return
    print("Summary")
    print(format_table(_summary_rows(summary), ["metric", "value"]))
    print()
    print("Timeline")
    print(format_table(timeline[: args.timeline_limit], ["kind", "datetime", "student_name", "status", "lesson_id", "tutoring_id", "duration"]))


def cmd_compare(args: argparse.Namespace) -> None:
    rows = []
    for item in args.snapshots:
        path = Path(item).expanduser().resolve()
        snapshot = _load_snapshot(path)
        role = snapshot.get("account_role") or _account_role(snapshot)
        summary = snapshot.get("summary") or (
            build_payment_summary(snapshot) if role == "learner" else build_account_summary(snapshot)
        )
        label = snapshot.get("account_label") or path.stem
        # Comparing money across accounts is exactly where an unexplained gap
        # misleads, so each snapshot's warnings are surfaced, attributed.
        for warning in summary.get("warnings") or []:
            print(f"warning: [{label}] {warning}", file=sys.stderr)
        # Only name a money field "unknown" when this snapshot's role should
        # have supplied it; a learner legitimately has no wallet balance.
        wallet = summary.get("wallet_balance") if "wallet_balance" in summary else ""
        rows.append(
            {
                "account": label,
                "role": role,
                "students": summary.get("student_total", ""),
                "lessons": summary.get("confirmed_lessons_total", ""),
                "payments": summary.get("payment_count", ""),
                "earned": money(summary.get("student_revenue_total_usd")),
                "spent": money(summary.get("spent_total")),
                "wallet": _money_or_unknown(wallet) if wallet != "" else "",
            }
        )
    if getattr(args, "json", False):
        _print_json(rows)
    elif getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, ["account", "role", "students", "lessons", "payments", "earned", "spent", "wallet"]), end="")
    else:
        print(format_table(rows, ["account", "role", "students", "lessons", "payments", "earned", "spent", "wallet"]))


def cmd_account(args: argparse.Namespace) -> None:
    data = _client(args).account()
    if getattr(args, "json", False):
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



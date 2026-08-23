"""Learner-side commands, each verified against a live learner account."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..analysis import build_payment_summary, payment_nodes
from ..formatting import format_table, money, shorten
from ._shared import (
    BALANCE_COLUMNS,
    PENDING_COLUMNS,
    _client,
    _emit,
    _hours_display,
    _load_snapshot,
    _print_data_warnings,
    _print_json,
    _print_pending,
    _summary_rows,
)


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


def cmd_history(args: argparse.Namespace) -> None:
    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).payment_history(limit=args.limit)
    summary = data.get("summary") or build_payment_summary(data)
    _print_data_warnings(summary, data)
    if getattr(args, "json", False):
        _print_json({"summary": summary, "raw": data})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(_payment_rows(data), ["id", "time", "subject", "tutor", "hours", "amount", "refundable"]), end="")
        return
    print("Summary")
    print(format_table(_summary_rows(summary), ["metric", "value"]))
    print()
    print("Payments")
    print(format_table(_payment_rows(data), ["id", "time", "subject", "tutor", "hours", "amount", "refundable"]))


def cmd_lessons(args: argparse.Namespace) -> None:
    from ..analysis import build_lesson_summary, lesson_rows

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).learner_lessons(limit=args.limit, offset=args.offset)
    summary = data.get("summary") or build_lesson_summary(data)
    _print_data_warnings(summary, data)
    rows = lesson_rows(data)
    columns = ["datetime", "subject", "tutor", "duration", "status", "paid", "rating"]
    if getattr(args, "json", False):
        _print_json({"summary": summary, "rows": rows})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv

        print(format_csv(rows, columns), end="")
        return
    print("Summary")
    print(format_table(_summary_rows(summary), ["metric", "value"]))
    print()
    print("Lessons")
    print(format_table(rows, columns))


def cmd_upcoming(args: argparse.Namespace) -> None:
    from ..analysis import upcoming_rows

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).learner_upcoming_lessons()
    rows = upcoming_rows(data)
    columns = ["datetime", "subject", "tutor", "duration", "status", "paid"]
    if getattr(args, "json", False):
        _print_json({"rows": rows})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv

        print(format_csv(rows, columns), end="")
        return
    print(f"Upcoming lessons ({len(rows)})")
    print(format_table(rows, columns))


def cmd_tutors(args: argparse.Namespace) -> None:
    from ..analysis import tutoring_rows

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).learner_tutorings()
    _print_data_warnings(data)
    rows = tutoring_rows(data)
    columns = ["tutoring_id", "tutor", "subject", "price_usd", "lessons", "subscription", "refill_hours", "since"]
    if getattr(args, "json", False):
        _print_json({"rows": rows})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv

        print(format_csv(rows, columns), end="")
        return
    print(f"Active tutors / subscriptions ({len(rows)})")
    print(format_table(rows, columns))


def cmd_stats(args: argparse.Namespace) -> None:
    from ..analysis import learner_lifetime_stats

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).learner_stats()
    stats = learner_lifetime_stats(data)
    rows = [{"metric": key, "value": value} for key, value in stats.items()]
    if getattr(args, "json", False):
        _print_json(stats)
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv

        print(format_csv(rows, ["metric", "value"]), end="")
        return
    print("Lifetime learning stats")
    print(format_table(rows, ["metric", "value"]))


RENEWAL_COLUMNS = [
    "next_charge", "tutor", "subject", "charge", "currency",
    "refill_hours", "prepaid_hours", "frequency", "status", "price_change",
]
CERTIFICATE_COLUMNS = [
    "subject", "completed_hours", "level", "next_level", "hours_to_next", "download_url",
]


def cmd_renewals(args: argparse.Namespace) -> None:
    """What Preply will charge next, per tutor, and in which currency."""
    from ..analysis import build_renewal_summary, renewal_rows

    if getattr(args, "file", None):
        data = _load_snapshot(Path(args.file).expanduser().resolve())
    else:
        data = _client(args).learner_renewals()

    summary = build_renewal_summary(data)
    rows = renewal_rows(data)
    if not getattr(args, "all", False):
        from ..analysis import _is_upcoming

        # Stopped subscriptions keep their last charge date and amount, so
        # listing them beside real ones reads as a bill. `--all` shows them; the
        # summary counts them either way, so they are never silently dropped.
        rows = [r for r in rows if _is_upcoming(r)]

    _print_data_warnings(summary, data)

    if getattr(args, "json", False):
        _print_json({"summary": summary, "rows": rows})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, RENEWAL_COLUMNS), end="")
        return

    totals = summary["charge_totals"]
    overview = [
        {"metric": "next_charge", "value": summary["next_charge"] or "none scheduled"},
        {"metric": "upcoming_total", "value": _charge_totals_display(totals)},
        {"metric": "active_subscriptions", "value": summary["active_subscriptions"]},
        {"metric": "stopped_subscriptions", "value": summary["stopped_subscriptions"]},
        {"metric": "no_subscription", "value": summary["no_subscription"]},
        {"metric": "pending_price_changes", "value": summary["pending_price_changes"]},
    ]
    if summary["charges_unreadable"]:
        overview.append(
            {"metric": "charges_unreadable", "value": summary["charges_unreadable"]}
        )
    print("Renewals")
    print(format_table(overview, ["metric", "value"]))
    print()
    print(format_table(rows, RENEWAL_COLUMNS))


def _charge_totals_display(totals: dict[str, float]) -> str:
    """Per-currency subtotals, never summed across currencies.

    One number spanning USD and EUR is not a bill, it is a coincidence.
    """
    if not totals:
        return "none"
    return ", ".join(f"{amount:.2f} {code}" for code, amount in sorted(totals.items()))


def cmd_certificates(args: argparse.Namespace) -> None:
    """Achievement certificates per subject, with the download link."""
    from ..analysis import build_certificate_summary, certificate_rows

    if getattr(args, "file", None):
        data = _load_snapshot(Path(args.file).expanduser().resolve())
    else:
        data = _client(args).learner_certificates()

    summary = build_certificate_summary(data)
    rows = certificate_rows(data)
    _print_data_warnings(summary, data)

    if getattr(args, "json", False):
        _print_json({"summary": summary, "rows": rows})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, CERTIFICATE_COLUMNS), end="")
        return

    print("Certificates")
    print(format_table([
        {"metric": "certificates", "value": summary["certificates"]},
        {"metric": "completed_hours_total", "value": _hours_display(summary["completed_hours_total"])},
    ], ["metric", "value"]))
    print()
    print(format_table(rows, CERTIFICATE_COLUMNS))


def cmd_balance(args: argparse.Namespace) -> None:
    from ..analysis import (
        balance_rows,
        build_balance_summary,
        learner_wallet_context,
        pending_payment_rows,
    )

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).learner_balance()

    summary = build_balance_summary(data)
    context = learner_wallet_context(data)
    rows = balance_rows(data)
    pending = pending_payment_rows(data)

    _print_data_warnings(summary, data)

    if getattr(args, "json", False):
        _print_json({"summary": summary, "context": context,
                     "rows": rows, "pending_payment": pending})
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(format_csv(rows, BALANCE_COLUMNS), end="")
        return

    overview = [
        {"metric": "balance_hours", "value": _hours_display(summary["total_balance_hours"])},
        {"metric": "unscheduled_hours", "value": summary["unscheduled_hours"]},
        {"metric": "unavailable_hours", "value": summary["unavailable_hours"]},
        {"metric": "tutorings_with_balance", "value": summary["tutoring_count"]},
        {"metric": "active_subscriptions", "value": summary["active_subscriptions"]},
        {"metric": "without_subscription", "value": summary["without_subscription"]},
        {"metric": "unknown_status", "value": summary["unknown_status"]},
        {"metric": "next_charge", "value": summary["next_charge"] or "none scheduled"},
        {"metric": "lifetime_hours_taken", "value": context.get("passed_hours")},
        {"metric": "currency", "value": context.get("currency") or "USD"},
    ]
    print("Balance")
    print(format_table(overview, ["metric", "value"]))
    print()
    print(f"Per tutor ({len(rows)})")
    print(format_table(rows, BALANCE_COLUMNS))

    if summary["unscheduled_hours"] > 0:
        print()
        print(
            f"note: {summary['unscheduled_hours']:g} paid hour(s) are unscheduled. "
            "Book them or they stay idle."
        )
    _print_pending(pending)


def cmd_me(args: argparse.Namespace) -> None:
    from ..analysis import (
        UNREADABLE_DATE,
        balance_rows,
        build_balance_summary,
        learner_lifetime_stats,
        learner_subscription_state,
        learner_wallet_context,
        lesson_rows,
        pending_payment_rows,
        unread_message_count,
        upcoming_rows,
    )

    if getattr(args, "file", None):
        path = Path(args.file).expanduser().resolve()
        data = _load_snapshot(path)
    else:
        data = _client(args).learner_dashboard(lesson_limit=args.recent)

    account = data.get("_account") or {}
    summary = build_balance_summary(data)
    context = learner_wallet_context(data)
    stats = learner_lifetime_stats(data)
    subscription = learner_subscription_state(data)
    unread = unread_message_count(data)
    upcoming = upcoming_rows(data)
    recent = lesson_rows(data)[: args.recent]
    pending = pending_payment_rows(data)
    rows = balance_rows(data)
    # A "?" charge date is unreadable, not absent: keep it visible here rather
    # than letting the row drop out of the charges list entirely.
    charges = [r for r in rows if r["next_charge"]]
    idle = [r for r in rows if (r["unscheduled"] or 0) > 0]

    _print_data_warnings(summary, data)

    if getattr(args, "json", False):
        _print_json({
            "account": account,
            "balance": summary,
            "context": context,
            "stats": stats,
            "subscription": subscription,
            "unread_messages": unread,
            "upcoming": upcoming,
            "recent_lessons": recent,
            "pending_payment": pending,
            "balance_rows": rows,
        })
        return
    if getattr(args, "csv", False):
        # One command, many tables: export the balance rows, matching how
        # `analyze` and `history` each pick a single primary table for CSV.
        from ..formatting import format_csv
        print(format_csv(rows, BALANCE_COLUMNS), end="")
        return

    headline = [
        {"metric": "name", "value": account.get("name")},
        {"metric": "user_id", "value": account.get("userId")},
        {"metric": "role", "value": account.get("role")},
        {"metric": "lessons_completed", "value": stats.get("lessons_completed")},
        {"metric": "highest_streak", "value": stats.get("highest_lesson_streak")},
        {"metric": "lifetime_hours", "value": context.get("passed_hours")},
        {"metric": "subscriber", "value": subscription.get("is_active_subscriber")},
        {"metric": "subscription_type", "value": subscription.get("subscription_type")},
        {"metric": "unread_messages", "value": unread},
        {"metric": "balance_hours", "value": _hours_display(summary["total_balance_hours"])},
        {"metric": "unscheduled_hours", "value": summary["unscheduled_hours"]},
        {"metric": "next_charge", "value": summary["next_charge"] or "none scheduled"},
    ]
    print(f"Preply · {account.get('name') or 'account'}")
    print(format_table(headline, ["metric", "value"]))

    print()
    print(f"Upcoming lessons ({len(upcoming)})")
    print(format_table(upcoming, ["datetime", "subject", "tutor", "duration", "status"]))

    print()
    print(f"Recent lessons ({len(recent)})")
    print(format_table(recent, ["datetime", "subject", "tutor", "status", "paid", "rating"]))

    print()
    undated = sum(1 for r in charges if r["next_charge"] == UNREADABLE_DATE)
    suffix = f", {undated} with an unreadable date" if undated else ""
    print(f"Upcoming charges ({len(charges)}{suffix})")
    print(format_table(charges, ["next_charge", "tutor", "subject", "frequency", "status"]))

    if idle:
        print()
        print(f"Unscheduled paid hours ({len(idle)})")
        print(format_table(idle, ["tutor", "subject", "unscheduled", "status"]))
    _print_pending(pending)



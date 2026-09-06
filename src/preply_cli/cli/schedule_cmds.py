"""Public tutor schedule CLI commands."""

from __future__ import annotations

import argparse
from datetime import date
from typing import Any

from ..formatting import format_table
from ..public_schedule import (
    DEFAULT_DURATION_HOURS,
    DEFAULT_TIMEZONE,
    PublicScheduleError,
    load_tutor_schedule,
)
from ._shared import _emit, _print_json


def _slot_rows(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for s in slots:
        start = s.get("start_time", "")
        end = s.get("end_time", "")
        time_str = f"{start} - {end}" if start and end else start
        dur_min = s.get("duration_minutes", 50)
        is_night = s.get("is_night", False)
        rows.append(
            {
                "date": s.get("date", ""),
                "time": time_str,
                "duration": f"{dur_min}m",
                "type": s.get("type", ""),
                "student": s.get("student_initials", ""),
                "night": "YES" if is_night else "No",
            }
        )
    return rows


def _summary_rows(daily: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for d_str in sorted(daily.keys()):
        d_rec = daily[d_str]
        try:
            day_name = date.fromisoformat(d_str).strftime("%a")
        except Exception:
            day_name = ""

        earliest = d_rec.get("earliest", "")
        latest = d_rec.get("latest", "")
        window = f"{earliest} - {latest}" if earliest and latest else "None"
        night_cnt = d_rec.get("night_slots", 0)

        rows.append(
            {
                "date": d_str,
                "day": day_name,
                "booked": d_rec.get("booked", 0),
                "free": d_rec.get("free", 0),
                "busy": d_rec.get("busy", 0),
                "night_slots": night_cnt,
                "window": window,
            }
        )
    return rows


def cmd_tutor_schedule(args: argparse.Namespace) -> None:
    source = getattr(args, "file", None) or getattr(args, "source", "")
    if not source:
        raise PublicScheduleError("Must specify tutor ID, profile URL, or a snapshot file path (-f).")

    if getattr(args, "duration", None):
        dur_hours = 0.5 if args.duration <= 30 else 1.0
    else:
        dur_hours = DEFAULT_DURATION_HOURS
    show_booked = not getattr(args, "no_booked", False)
    tzname = getattr(args, "timezone", None) or getattr(args, "tz", None) or DEFAULT_TIMEZONE
    proxy = getattr(args, "proxy", None)
    timeout = getattr(args, "timeout", 30)
    days = getattr(args, "days", 7)
    date_start = getattr(args, "date", None)

    data = load_tutor_schedule(
        source=source,
        date_start=date_start,
        days=days,
        tzname=tzname,
        show_booked=show_booked,
        duration_hours=dur_hours,
        proxy=proxy,
        timeout=timeout,
    )

    if getattr(args, "json", False):
        _print_json(data)
        return

    slots = data.get("slots", [])
    summary = data.get("summary", {})
    daily = summary.get("daily", {})

    if getattr(args, "csv", False):
        from ..formatting import format_csv

        slot_rows = _slot_rows(slots)
        print(
            format_csv(
                slot_rows,
                ["date", "time", "duration", "type", "student", "night"],
            ),
            end="",
        )
        return

    # Table output
    meta_rows = [
        {"metric": "tutor_id", "value": data.get("tutor_id")},
        {"metric": "range", "value": f"{data.get('date_start')} to {data.get('date_end')}"},
        {"metric": "timezone", "value": data.get("timezone")},
        {"metric": "total_slots", "value": summary.get("total_slots", 0)},
        {"metric": "booked_slots", "value": summary.get("booked_slots", 0)},
        {"metric": "free_slots", "value": summary.get("free_slots", 0)},
        {"metric": "night_classes_booked", "value": summary.get("night_booked", 0)},
        {"metric": "night_classes_free", "value": summary.get("night_free", 0)},
        {"metric": "booking_window_interval", "value": f"{data.get('booking_window_interval')} days"},
        {"metric": "egress", "value": data.get("_egress", "direct")},
    ]

    print("Schedule Overview")
    print(format_table(meta_rows, ["metric", "value"]))
    print()

    if daily:
        print("Daily Breakdown")
        daily_rows = _summary_rows(daily)
        print(format_table(daily_rows, ["date", "day", "booked", "free", "busy", "night_slots", "window"]))
        print()

    if slots:
        print(f"Timeslots ({len(slots)} total)")
        slot_rows = _slot_rows(slots)
        print(format_table(slot_rows, ["date", "time", "duration", "type", "student", "night"]))
    else:
        print("No timeslots scheduled or open in the selected date range.")

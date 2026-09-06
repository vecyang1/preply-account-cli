"""Public Preply tutor schedule and booking timeslot reading.

Queries Preply's public BookingTimeslots GraphQL endpoint without requiring
authentication or saved sessions. Supports offline fixtures, date ranges,
timezone conversions, night-class detection, and aggregated daily summaries.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .queries import get_operation
from .transport import PreplyTransportError, post_public_graphql

DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_DURATION_HOURS = 1.0  # 1-hour slot (Preply backend accepts 1.0 or 0.5)
NIGHT_CUTOFF_HOUR = 18  # Evening classes start at or after 18:00 (6 PM)


class PublicScheduleError(RuntimeError):
    """Raised when parsing or processing public tutor schedule fails."""


def extract_tutor_id(source: str) -> int:
    """Extract numeric tutor ID from an ID string, profile URL, or booking URL.

    Examples:
        6558836 -> 6558836
        https://preply.com/en/tutor/6558836 -> 6558836
        https://preply.com/en/tutor/6558836?foo=bar -> 6558836
    """
    trimmed = source.strip()
    if trimmed.isdigit():
        return int(trimmed)

    # Match /tutor/(\d+) pattern
    match = re.search(r"/tutor/(\d+)", trimmed)
    if match:
        return int(match.group(1))

    # Match standalone digits in URL or path if unambiguous
    match_digits = re.findall(r"\b\d{5,10}\b", trimmed)
    if match_digits:
        return int(match_digits[0])

    raise PublicScheduleError(
        f"Could not extract numeric tutor ID from {source!r}. "
        "Expected numeric tutor ID (e.g. 6558836) or tutor URL (e.g. https://preply.com/en/tutor/6558836)."
    )


def _to_local_dt(dt_str: str, tzname: str) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(ZoneInfo(tzname))
    except Exception:
        return None


def _format_time(dt_str: str, tzname: str = DEFAULT_TIMEZONE) -> str:
    """Extract HH:MM from ISO datetime string, converted to target timezone."""
    loc = _to_local_dt(dt_str, tzname)
    if loc:
        return loc.strftime("%H:%M")
    if "T" in dt_str:
        time_part = dt_str.split("T")[1]
        return time_part[:5]
    return dt_str


def _parse_iso_date(dt_str: str, tzname: str = DEFAULT_TIMEZONE) -> str:
    """Extract YYYY-MM-DD from ISO datetime string, converted to target timezone."""
    loc = _to_local_dt(dt_str, tzname)
    if loc:
        return loc.strftime("%Y-%m-%d")
    if not dt_str:
        return ""
    return dt_str.split("T")[0][:10]


def _calc_duration_minutes(start_iso: str, end_iso: str) -> int:
    """Calculate duration in minutes between two ISO datetime strings."""
    try:
        s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        return max(0, int((e - s).total_seconds() // 60))
    except (ValueError, TypeError):
        return 50


def build_schedule_summary(
    slots: list[dict[str, Any]],
    date_start: str,
    date_end: str,
    tzname: str,
) -> dict[str, Any]:
    """Compute aggregate totals, night class counts, and daily breakdown."""
    total_slots = len(slots)
    booked_slots = 0
    free_slots = 0
    busy_slots = 0
    night_booked = 0
    night_free = 0

    daily: dict[str, dict[str, Any]] = {}

    for slot in slots:
        slot_type = (slot.get("type") or "UNKNOWN").upper()
        s_date = slot.get("date") or _parse_iso_date(slot.get("dateStart", ""), tzname)
        s_time = slot.get("start_time") or _format_time(slot.get("dateStart", ""), tzname)
        e_time = slot.get("end_time") or _format_time(slot.get("dateEnd", ""), tzname)

        is_night = False
        if s_time and ":" in s_time:
            try:
                hour = int(s_time.split(":")[0])
                if hour >= NIGHT_CUTOFF_HOUR:
                    is_night = True
            except ValueError:
                pass

        slot["is_night"] = is_night

        if slot_type == "BOOKED":
            booked_slots += 1
            if is_night:
                night_booked += 1
        elif slot_type == "FREE":
            free_slots += 1
            if is_night:
                night_free += 1
        else:
            busy_slots += 1

        if s_date not in daily:
            daily[s_date] = {
                "date": s_date,
                "total": 0,
                "booked": 0,
                "free": 0,
                "busy": 0,
                "earliest": s_time,
                "latest": e_time,
                "has_night_slots": False,
                "night_slots": 0,
                "slots": [],
            }

        day_rec = daily[s_date]
        day_rec["total"] += 1
        if slot_type == "BOOKED":
            day_rec["booked"] += 1
        elif slot_type == "FREE":
            day_rec["free"] += 1
        else:
            day_rec["busy"] += 1

        if is_night:
            day_rec["has_night_slots"] = True
            day_rec["night_slots"] += 1

        if s_time and (not day_rec["earliest"] or s_time < day_rec["earliest"]):
            day_rec["earliest"] = s_time
        if e_time and (not day_rec["latest"] or e_time > day_rec["latest"]):
            day_rec["latest"] = e_time

        day_rec["slots"].append(slot)

    return {
        "timezone": tzname,
        "date_start": date_start,
        "date_end": date_end,
        "total_slots": total_slots,
        "booked_slots": booked_slots,
        "free_slots": free_slots,
        "busy_slots": busy_slots,
        "night_cutoff_hour": NIGHT_CUTOFF_HOUR,
        "night_booked": night_booked,
        "night_free": night_free,
        "daily": daily,
    }


def parse_tutor_schedule(
    raw_payload: dict[str, Any],
    date_start: str,
    date_end: str,
    tzname: str,
) -> dict[str, Any]:
    """Normalize raw BookingTimeslots GraphQL response into structured schedule data."""
    tutor_data = raw_payload.get("tutor") or raw_payload
    tutor_id = tutor_data.get("id")
    raw_slots = tutor_data.get("timeslotsForBooking") or []
    window_interval = tutor_data.get("bookingWindowInterval")

    normalized_slots: list[dict[str, Any]] = []
    for raw in raw_slots:
        ds = raw.get("dateStart", "")
        de = raw.get("dateEnd", "")
        slot_date = _parse_iso_date(ds, tzname)
        start_time = _format_time(ds, tzname)
        end_time = _format_time(de, tzname)
        slot_type = (raw.get("type") or "UNKNOWN").upper()
        initials = raw.get("bookedTimeslotUserInitials")
        duration = _calc_duration_minutes(ds, de)

        normalized_slots.append(
            {
                "date": slot_date,
                "start_time": start_time,
                "end_time": end_time,
                "duration_minutes": duration,
                "type": slot_type,
                "student_initials": initials or "",
                "dateStart": ds,
                "dateEnd": de,
            }
        )

    # Sort slots chronologically
    normalized_slots.sort(key=lambda s: (s.get("dateStart", ""), s.get("start_time", "")))

    summary = build_schedule_summary(normalized_slots, date_start, date_end, tzname)
    summary["tutor_id"] = tutor_id
    summary["booking_window_interval"] = window_interval

    return {
        "tutor_id": tutor_id,
        "booking_window_interval": window_interval,
        "date_start": date_start,
        "date_end": date_end,
        "timezone": tzname,
        "slots": normalized_slots,
        "summary": summary,
        "_egress": raw_payload.get("_egress", "unknown"),
    }


def fetch_tutor_schedule(
    tutor_id: int,
    date_start: str,
    date_end: str,
    tzname: str = DEFAULT_TIMEZONE,
    show_booked: bool = True,
    duration_hours: float = DEFAULT_DURATION_HOURS,
    proxy: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Fetch live public schedule via BookingTimeslots GraphQL query."""
    op = get_operation("BookingTimeslots")
    variables = {
        "tutorId": tutor_id,
        "dateStart": date_start,
        "dateEnd": date_end,
        "tzname": tzname,
        "showBooked": show_booked,
        "durationHours": duration_hours,
    }
    data = post_public_graphql(
        operation_name=op.name,
        query=op.query,
        variables=variables,
        proxy=proxy,
        timeout=timeout,
    )
    return parse_tutor_schedule(data, date_start=date_start, date_end=date_end, tzname=tzname)


def load_tutor_schedule(
    source: str,
    date_start: str | None = None,
    days: int = 7,
    tzname: str | None = None,
    show_booked: bool = True,
    duration_hours: float | None = None,
    proxy: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Load schedule from a file path or live network fetch."""
    resolved_tz = tzname or DEFAULT_TIMEZONE
    dur_hours = duration_hours if duration_hours is not None else DEFAULT_DURATION_HOURS

    # 1. If source is an existing local file, load offline
    path = Path(source).expanduser().resolve()
    if path.exists() and path.is_file():
        try:
            content = path.read_text(encoding="utf-8")
            raw_data = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            raise PublicScheduleError(f"Failed to read JSON schedule from {path}: {exc}") from exc

        # If it contains a wrapped "data" block
        if "data" in raw_data:
            raw_data = raw_data["data"]

        # If already parsed
        if "summary" in raw_data and "slots" in raw_data:
            return raw_data

        d_start = date_start or date.today().isoformat()
        d_end = (date.fromisoformat(d_start) + timedelta(days=days)).isoformat()
        return parse_tutor_schedule(raw_data, date_start=d_start, date_end=d_end, tzname=resolved_tz)

    # 2. Extract numeric tutor ID and compute dates
    tutor_id = extract_tutor_id(source)

    if date_start:
        d_start_obj = date.fromisoformat(date_start)
    else:
        try:
            d_start_obj = datetime.now(ZoneInfo(resolved_tz)).date()
        except Exception:
            d_start_obj = date.today()

    d_start_str = d_start_obj.isoformat()
    d_end_str = (d_start_obj + timedelta(days=days)).isoformat()

    return fetch_tutor_schedule(
        tutor_id=tutor_id,
        date_start=d_start_str,
        date_end=d_end_str,
        tzname=resolved_tz,
        show_booked=show_booked,
        duration_hours=dur_hours,
        proxy=proxy,
        timeout=timeout,
    )

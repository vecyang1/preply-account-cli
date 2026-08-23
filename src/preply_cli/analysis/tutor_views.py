"""Tutor-side aggregates: account totals, students, revenue timeline."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from ._common import _dict_nodes, _number, _opt_number, _sum_or_unknown, student_nodes


def build_account_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    students = student_nodes(snapshot)
    status_counts = Counter(str(student.get("status") or "UNKNOWN") for student in students)
    prices = [_number(student.get("pricePerHourUsd"), default=-1) for student in students]
    prices = [price for price in prices if price >= 0]
    profile = snapshot.get("profile") or {}
    tutor = profile.get("currentUser", {}).get("tutor")
    connection = (tutor or {}).get("studentManagementTutorings", {})
    wallet_user = (snapshot.get("wallet") or {}).get("currentUser") or {}
    wallet = wallet_user.get("wallet") or {}

    lessons_total, lessons_unreadable = _sum_or_unknown(students, "confirmedLessonsCount")
    revenue_total, revenue_unreadable = _sum_or_unknown(students, "totalTutorRevenue")
    balance = _opt_number(wallet, "balance")
    raw_total = connection.get("totalCount")

    warnings: list[str] = []
    if wallet and balance is None:
        warnings.append(
            "Wallet balance could not be read; it is shown as unknown, not zero."
        )
    if lessons_unreadable:
        warnings.append(
            f"{lessons_unreadable} student(s) have an unreadable lesson count; "
            "confirmed_lessons_total is a floor."
        )
    if revenue_unreadable:
        warnings.append(
            f"{revenue_unreadable} student(s) have unreadable revenue; "
            "student_revenue_total_usd is a floor."
        )
    if students and raw_total is None:
        warnings.append(
            "Student totalCount could not be read; student_total falls back to the "
            "number actually loaded and may undercount the account."
        )

    return {
        "student_total": int(raw_total) if raw_total is not None else len(students),
        "loaded_students": len(students),
        "status_counts": dict(sorted(status_counts.items())),
        "confirmed_lessons_total": int(lessons_total),
        "student_revenue_total_usd": round(revenue_total, 2),
        "wallet_balance": balance,
        "price_range_usd": {
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
        },
        "warnings": warnings,
    }


def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
    raw = item.get("datetime") or item.get("dateStart") or ""
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return (0, parsed.isoformat())
    except ValueError:
        return (1, str(raw))


def build_timeline(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    schedule_nodes = _dict_nodes(
        ((((snapshot.get("schedule") or {}).get("currentUser") or {})
           .get("tutor") or {}).get("calendar") or {}).get("nodes")
    )
    for node in schedule_nodes:
        lesson = node.get("lesson") or {}
        if not lesson.get("id"):
            continue
        tutoring = lesson.get("tutoring") or {}
        client = lesson.get("client") or {}
        user = client.get("user") or {}
        items.append(
            {
                "kind": "upcoming_lesson",
                "datetime": node.get("dateStart"),
                "dateStart": node.get("dateStart"),
                "dateEnd": node.get("dateEnd"),
                "lesson_id": lesson.get("id"),
                "tutoring_id": tutoring.get("id"),
                "student_name": user.get("fullName") or tutoring.get("clientName"),
                "status": lesson.get("status"),
                "duration": lesson.get("duration"),
            }
        )

    details_block = snapshot.get("student_details")
    for tutoring_id, detail in (details_block or {}).items():
        if not isinstance(detail, dict):
            continue
        past_nodes = _dict_nodes(
            ((((detail.get("pastLessons") or {}).get("tutoring") or {})
              .get("pastLessons") or {}).get("nodes"))
        )
        student_name = (
            ((detail.get("details") or {}).get("tutoring") or {}).get("clientName")
        )
        for lesson in past_nodes:
            items.append(
                {
                    "kind": "past_lesson",
                    "datetime": lesson.get("datetime"),
                    "lesson_id": lesson.get("id"),
                    "tutoring_id": int(tutoring_id),
                    "student_name": student_name,
                    "status": lesson.get("status"),
                    "duration": lesson.get("duration"),
                    "earnedAmount": lesson.get("earnedAmount"),
                }
            )
    return sorted(items, key=_sort_key)



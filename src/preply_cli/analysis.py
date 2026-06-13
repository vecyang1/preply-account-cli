from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def student_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    profile = snapshot.get("profile") or {}
    tutor = profile.get("currentUser", {}).get("tutor")
    return (tutor or {}).get("studentManagementTutorings", {}).get("nodes", [])


def build_account_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    students = student_nodes(snapshot)
    status_counts = Counter(str(student.get("status") or "UNKNOWN") for student in students)
    prices = [_number(student.get("pricePerHourUsd"), default=-1) for student in students]
    prices = [price for price in prices if price >= 0]
    profile = snapshot.get("profile") or {}
    tutor = profile.get("currentUser", {}).get("tutor")
    total_count = (tutor or {}).get("studentManagementTutorings", {}).get("totalCount", len(students))
    wallet_user = (snapshot.get("wallet") or {}).get("currentUser") or {}
    wallet = wallet_user.get("wallet") or {}
    return {
        "student_total": int(total_count or 0),
        "loaded_students": len(students),
        "status_counts": dict(sorted(status_counts.items())),
        "confirmed_lessons_total": int(sum(_number(s.get("confirmedLessonsCount")) for s in students)),
        "student_revenue_total_usd": round(sum(_number(s.get("totalTutorRevenue")) for s in students), 2),
        "wallet_balance": _number(wallet.get("balance")),
        "price_range_usd": {
            "min": min(prices) if prices else None,
            "max": max(prices) if prices else None,
        },
    }


def payment_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    history = snapshot.get("history") or {}
    return (history.get("paymentsHistory") or {}).get("payments") or []


def build_payment_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    payments = payment_nodes(snapshot)
    subjects: defaultdict[str, float] = defaultdict(float)
    tutors: defaultdict[str, float] = defaultdict(float)
    currencies = set()
    for payment in payments:
        amount = _number(payment.get("amount"))
        subject = str(payment.get("subject") or "UNKNOWN")
        tutor = str(payment.get("tutor") or "UNKNOWN")
        subjects[subject] += amount
        tutors[tutor] += amount
        if payment.get("currencyCode"):
            currencies.add(str(payment["currencyCode"]))
    return {
        "payment_count": len(payments),
        "spent_total": round(sum(_number(payment.get("amount")) for payment in payments), 2),
        "hours_total": round(sum(_number(payment.get("hours")) for payment in payments), 2),
        "subjects": dict(sorted((key, round(value, 2)) for key, value in subjects.items())),
        "tutors": dict(sorted((key, round(value, 2)) for key, value in tutors.items())),
        "currency_codes": sorted(currencies),
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
    schedule_nodes = (
        (snapshot.get("schedule") or {})
        .get("currentUser", {})
        .get("tutor", {})
        .get("calendar", {})
        .get("nodes", [])
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

    for tutoring_id, detail in (snapshot.get("student_details") or {}).items():
        past_nodes = (
            (detail.get("pastLessons") or {})
            .get("tutoring", {})
            .get("pastLessons", {})
            .get("nodes", [])
        )
        student_name = (detail.get("details") or {}).get("tutoring", {}).get("clientName")
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

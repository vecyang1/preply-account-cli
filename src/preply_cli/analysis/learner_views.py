"""Learner-side aggregates: payments, lessons, tutorings, balance, renewals,
and certificates."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from ._common import (
    NO_SUBSCRIPTION,
    UNKNOWN,
    UNREADABLE_DATE,
    _absolute_preply_url,
    _dict_nodes,
    balance_nodes,
    _number,
    _opt_int,
    _opt_number,
    _sum_or_unknown,
)


def payment_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    history = snapshot.get("history") or {}
    return _dict_nodes((history.get("paymentsHistory") or {}).get("payments"))


def build_payment_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    payments = payment_nodes(snapshot)
    subjects: defaultdict[str, float] = defaultdict(float)
    tutors: defaultdict[str, float] = defaultdict(float)
    currencies = set()
    for payment in payments:
        amount = _opt_number(payment, "amount") or 0.0
        subject = str(payment.get("subject") or "UNKNOWN")
        tutor = str(payment.get("tutor") or "UNKNOWN")
        subjects[subject] += amount
        tutors[tutor] += amount
        if payment.get("currencyCode"):
            currencies.add(str(payment["currencyCode"]))

    spent_total, spent_unreadable = _sum_or_unknown(payments, "amount")
    hours_total, hours_unreadable = _sum_or_unknown(payments, "hours")
    warnings: list[str] = []
    if spent_unreadable:
        warnings.append(
            f"{spent_unreadable} payment(s) have an unreadable amount; "
            "spent_total is a floor, not the full spend."
        )
    if hours_unreadable:
        warnings.append(
            f"{hours_unreadable} payment(s) have unreadable hours; "
            "hours_total is a floor."
        )
    return {
        "payment_count": len(payments),
        "spent_total": round(spent_total, 2),
        "hours_total": round(hours_total, 2),
        "subjects": dict(sorted((key, round(value, 2)) for key, value in subjects.items())),
        "tutors": dict(sorted((key, round(value, 2)) for key, value in tutors.items())),
        "currency_codes": sorted(currencies),
        "warnings": warnings,
    }


def _client_block(snapshot: dict[str, Any], op_key: str) -> dict[str, Any]:
    """The currentUser.client block under a given operation result key."""
    root = snapshot.get(op_key) or {}
    return ((root.get("currentUser") or {}).get("client")) or {}


def lesson_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Learner completed-lesson nodes from a CurrentUserPastLessons payload."""
    client = _client_block(snapshot, "lessons")
    return _dict_nodes((client.get("pastLessons") or {}).get("nodes"))


def upcoming_lesson_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Learner upcoming-lesson nodes from a CurrentUserUpcomingLessons payload."""
    client = _client_block(snapshot, "upcoming")
    return _dict_nodes((client.get("upcomingLessons") or {}).get("nodes"))


def _lesson_node_to_row(node: dict[str, Any]) -> dict[str, Any]:
    """Flatten a learner lesson/reservation node into a display row.

    Handles both node shapes: booked lessons carry ``tutor`` at the top level;
    recurrent reservations carry it under ``tutoring.tutor``.
    """
    tutoring = node.get("tutoring") or {}
    tutor = node.get("tutor") or tutoring.get("tutor") or {}
    tutor_user = tutor.get("user") or {}
    subject = ((tutoring.get("lead") or {}).get("subject") or {}).get("translatedName")
    rating = node.get("rating") or {}
    return {
        "datetime": node.get("datetime"),
        "lesson_id": node.get("id"),
        "subject": subject or "",
        "tutor": tutor_user.get("firstName") or "",
        "duration": node.get("duration"),
        # Booked lessons carry an explicit status; recurrent reservations don't,
        # so label them RESERVED, identified by their union type.
        "status": node.get("status")
        or ("RESERVED" if node.get("__typename") == "RecurrentLessonReservationNode" else ""),
        "paid": node.get("paidAmount"),
        "rating": rating.get("amount") if node.get("isRated") else "",
        "first": node.get("isFirstLesson"),
    }


def lesson_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten learner past-lesson nodes into display rows (most recent first)."""
    rows = [_lesson_node_to_row(node) for node in lesson_nodes(snapshot)]
    rows.sort(key=lambda r: str(r.get("datetime") or ""), reverse=True)
    return rows


def upcoming_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten learner upcoming-lesson nodes into display rows (soonest first)."""
    rows = [_lesson_node_to_row(node) for node in upcoming_lesson_nodes(snapshot)]
    rows.sort(key=lambda r: str(r.get("datetime") or ""))
    return rows


def tutoring_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    client = _client_block(snapshot, "tutorings")
    return _dict_nodes((client.get("tutorings") or {}).get("nodes"))


def tutoring_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten learner active tutorings into subscription rows."""
    rows = []
    for node in tutoring_nodes(snapshot):
        tutor_user = ((node.get("tutor") or {}).get("user")) or {}
        subject = ((node.get("lead") or {}).get("subject") or {}).get("translatedName")
        refill = node.get("refill")
        # Same three-valued rule as balance_rows: a null refill is genuinely
        # stopped, a present-but-unreadable one must not render as blank (which
        # reads identically to "no subscription").
        if refill is None:
            subscription = NO_SUBSCRIPTION
            refill_hours = None
        else:
            subscription = refill.get("status") or UNKNOWN
            refill_hours = refill.get("refillHours")
        rows.append({
            "tutoring_id": node.get("id"),
            "tutor": tutor_user.get("firstName") or "",
            "subject": subject or "",
            "price_usd": node.get("pricePerHourUsd"),
            "lessons": node.get("confirmedLessonsCount"),
            "subscription": subscription,
            "refill_hours": refill_hours,
            "since": (node.get("created") or "")[:10],
        })
    rows.sort(key=lambda r: (-int(r.get("lessons") or 0), str(r.get("tutor") or "")))
    return rows


def learner_lifetime_stats(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract learner lifetime stats (streak, lessons, practices)."""
    client = _client_block(snapshot, "stats")
    lifetime = ((client.get("learningActivities") or {}).get("lifetimeStats")) or {}
    return {
        "highest_lesson_streak": lifetime.get("highestLessonStreak"),
        "lessons_completed": lifetime.get("lessonsCompleted"),
        "practices_completed": lifetime.get("practicesCompleted"),
    }


def build_lesson_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Aggregate learner lesson nodes: counts, hours, paid total, per-tutor/subject."""
    nodes = lesson_nodes(snapshot)
    status_counts: defaultdict[str, int] = defaultdict(int)
    subjects: defaultdict[str, int] = defaultdict(int)
    tutors: defaultdict[str, int] = defaultdict(int)
    hours_total, hours_unreadable = _sum_or_unknown(nodes, "duration")
    paid_total, paid_unreadable = _sum_or_unknown(nodes, "paidAmount")
    warnings: list[str] = []
    if hours_unreadable:
        warnings.append(
            f"{hours_unreadable} lesson(s) have an unreadable duration; "
            "hours_total is a floor."
        )
    if paid_unreadable:
        warnings.append(
            f"{paid_unreadable} lesson(s) have an unreadable paid amount; "
            "paid_total is a floor."
        )
    for node in nodes:
        status_counts[str(node.get("status") or "UNKNOWN")] += 1
        subject = (
            (((node.get("tutoring") or {}).get("lead") or {}).get("subject") or {})
            .get("translatedName")
        )
        subjects[str(subject or "UNKNOWN")] += 1
        tutor_user = ((node.get("tutor") or {}).get("user")) or {}
        tutors[str(tutor_user.get("firstName") or "UNKNOWN")] += 1
    return {
        "lesson_count": len(nodes),
        "hours_total": round(hours_total, 2),
        "paid_total": round(paid_total, 2),
        "status_counts": dict(sorted(status_counts.items())),
        "lessons_by_subject": dict(sorted(subjects.items())),
        "lessons_by_tutor": dict(sorted(tutors.items())),
        "warnings": warnings,
    }


# Markers that keep "Preply told us there is nothing" distinct from "we could
# not read what Preply told us". Money decisions hang on the difference: a
# stopped subscription really has no next charge, whereas a moved field means
# the charge is unknown and the totals below it are incomplete.
def balance_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten balance nodes into rows: banked hours, idle hours, next charge.

    Three refill states are kept apart, because collapsing them is how a billing
    subscription gets reported as "no upcoming charges":

    * ``refill`` is null - the subscription really was stopped. Banked hours
      remain and will sit idle until booked. Marked ``NO_SUBSCRIPTION``.
    * ``refill`` is present and readable - normal case.
    * ``refill`` is present but its status or date fields are missing - Preply
      moved something. Marked ``UNKNOWN`` / ``?`` so it is never counted as
      "nothing scheduled".

    Rows sort soonest-charge first, then unscheduled hours descending, so the
    money needing attention is at the top; unreadable rows sort just before the
    stopped ones rather than vanishing.
    """
    rows = []
    for node in balance_nodes(snapshot):
        tutoring = node.get("tutoring") or {}
        tutor_user = ((tutoring.get("tutor") or {}).get("user")) or {}
        subject = (node.get("lead") or {}).get("subject") or {}
        refill = node.get("refill")

        if refill is None:
            status, next_charge, frequency = NO_SUBSCRIPTION, "", ""
        else:
            raw_date = refill.get("nextRefill") or refill.get("nextSubscription")
            next_charge = str(raw_date)[:10] if raw_date else UNREADABLE_DATE
            status = refill.get("status") or UNKNOWN
            frequency = refill.get("billingFrequency") or ""

        rows.append({
            "tutoring_id": tutoring.get("id"),
            "tutor": tutor_user.get("firstName") or "",
            "subject": subject.get("alias") or "",
            "hours": _opt_number(tutoring, "hours"),
            "unscheduled": _opt_number(node, "unscheduledLessons"),
            "unavailable": _opt_number(node, "unavailableLessons"),
            "next_charge": next_charge,
            "frequency": frequency,
            "status": status,
        })
    # "?" sorts after any real ISO date and before the "" of a stopped row, so
    # unreadable entries stay adjacent to the dated ones they belong with.
    rows.sort(key=lambda r: (
        {"": "zz", UNREADABLE_DATE: "zy"}.get(r["next_charge"], r["next_charge"]),
        -(r["unscheduled"] or 0.0),
        str(r["tutor"]),
    ))
    return rows


def build_balance_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Aggregate the learner hour balance into a decision-shaped summary.

    ``total_balance_hours`` is Preply's own ``totalBalance`` and is None when
    that field could not be read. ``summed_row_hours`` is the independent
    per-row sum. ``warnings`` carries any reason the numbers should not be
    trusted at face value; callers are expected to display it.
    """
    root = (snapshot.get("balance") or {}).get("balanceManagementData") or {}
    rows = balance_rows(snapshot)
    charges = sorted(r["next_charge"] for r in rows if r["next_charge"]
                     and r["next_charge"] != UNREADABLE_DATE)

    total = _opt_number(root, "totalBalance")
    summed = round(sum(r["hours"] or 0.0 for r in rows), 2)
    reported_count = _opt_number(root, "totalNodesCount")

    warnings: list[str] = []
    if "totalBalance" in root and total is None:
        warnings.append(
            "Preply's totalBalance field could not be read; the balance shown is "
            "the per-tutor sum instead."
        )
    unknown_status = [r for r in rows if r["status"] == UNKNOWN]
    if unknown_status:
        warnings.append(
            f"{len(unknown_status)} subscription(s) have an unreadable status - "
            "they are NOT counted as stopped, and their charges may be missing."
        )
    undated = [r for r in rows if r["next_charge"] == UNREADABLE_DATE]
    if undated:
        warnings.append(
            f"{len(undated)} active subscription(s) have no readable charge date; "
            "'next charge' is incomplete."
        )
    unreadable_hours = [r for r in rows if r["hours"] is None]
    if unreadable_hours:
        warnings.append(
            f"{len(unreadable_hours)} row(s) have unreadable hours; totals are low."
        )
    if total is not None and abs(total - summed) > 0.01:
        warnings.append(
            f"Preply's reported balance ({total:g}h) does not match the per-tutor "
            f"sum ({summed:g}h). One of those fields may have moved."
        )

    return {
        "total_balance_hours": total,
        "summed_row_hours": summed,
        "tutoring_count": int(reported_count) if reported_count is not None else len(rows),
        "unscheduled_hours": round(sum(r["unscheduled"] or 0.0 for r in rows), 2),
        "unavailable_hours": round(sum(r["unavailable"] or 0.0 for r in rows), 2),
        "active_subscriptions": sum(1 for r in rows if r["status"] == "CONFIGURED"),
        "without_subscription": sum(1 for r in rows if r["status"] == NO_SUBSCRIPTION),
        "unknown_status": len(unknown_status),
        "next_charge": charges[0] if charges else None,
        "upcoming_charges": charges,
        "warnings": warnings,
    }


def pending_payment_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Tutors matched with the learner but awaiting a first payment."""
    client = _client_block(snapshot, "wallet_client")
    nodes = _dict_nodes((client.get("leads") or {}).get("nodes"))
    rows = []
    for node in nodes:
        tutor = node.get("tutor") or {}
        user = tutor.get("user") or {}
        rows.append({
            "lead_id": node.get("id"),
            "tutor": user.get("fullName") or "",
            "country": ((user.get("profile") or {}).get("countryCode")) or "",
            "price_usd": _number(node.get("pricePerHourUsd")),
            "tutor_status": tutor.get("status") or "",
        })
    rows.sort(key=lambda r: (-r["price_usd"], str(r["tutor"])))
    return rows


def learner_wallet_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Lifetime hours, currency, and country from a ClientWallet payload."""
    client = _client_block(snapshot, "wallet_client")
    profile = ((client.get("user") or {}).get("profile")) or {}
    currency = profile.get("currency") or {}
    return {
        "passed_hours": client.get("passedHours"),
        "is_enterprise": client.get("isEnterprise"),
        "currency": currency.get("code"),
        "currency_symbol": currency.get("translatedCode"),
        "country": profile.get("countryCode"),
    }


def learner_subscription_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Subscription posture from a UserSubscriptionsData payload."""
    client = _client_block(snapshot, "subscription")
    return {
        "subscription_type": client.get("subscriptionType"),
        "is_active_subscriber": client.get("isActiveSubscriber"),
    }


def unread_message_count(snapshot: dict[str, Any]) -> int | None:
    """Unread thread count from a ChatUnreadCounter payload."""
    user = (snapshot.get("unread") or {}).get("currentUser") or {}
    threads = user.get("messageThreads") or {}
    return threads.get("unreadCount")


# -- Renewals (money side of a subscription) ------------------------------
def renewal_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Tutoring rows from ``SettingsTutoringList``."""
    client = (
        ((snapshot.get("renewals") or {}).get("currentUser") or {}).get("client") or {}
    )
    return _dict_nodes((client.get("tutorings") or {}).get("nodes"))


def renewal_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per tutoring: what Preply will charge, when, and in what currency.

    ``BalanceManagementData`` (behind ``balance``) reports refill *hours* and
    dates but carries no amount and no currency, so it structurally cannot
    answer "how much". This is the only verified source of ``chargeAmount``.

    The same three refill states as ``balance_rows`` are kept distinct, for the
    same reason: a stopped subscription and an unreadable one both look like
    "no upcoming charge" if they are collapsed, and only one of them is.
    """
    rows = []
    for node in renewal_nodes(snapshot):
        tutor_user = ((node.get("tutor") or {}).get("user")) or {}
        subject = (node.get("lead") or {}).get("subject") or {}
        refill = node.get("refill")
        price_change = node.get("priceChangeRequestStatus") or {}

        if refill is None:
            status, next_charge, frequency = NO_SUBSCRIPTION, "", ""
            charge = None
            currency = ""
        else:
            raw_date = refill.get("nextRefill") or refill.get("nextSubscription")
            next_charge = str(raw_date)[:10] if raw_date else UNREADABLE_DATE
            status = refill.get("status") or UNKNOWN
            frequency = refill.get("billingFrequency") or refill.get("refillFrequency") or ""
            charge = _opt_number(refill, "chargeAmount")
            currency = ((refill.get("currency") or {}).get("code")) or ""

        rows.append({
            "tutoring_id": node.get("id"),
            "tutor": tutor_user.get("firstName") or tutor_user.get("fullName") or "",
            "subject": subject.get("translatedName") or "",
            "next_charge": next_charge,
            "charge": charge,
            "currency": currency,
            "refill_hours": _opt_number(refill or {}, "refillHours"),
            "hours": _opt_number(node, "hours"),
            "prepaid_hours": _opt_number(node, "totalPrepaidHours"),
            "payments": _opt_number(node, "paymentsCount"),
            "frequency": frequency,
            "status": status,
            # Preply returns null here when no price change is pending. A
            # pending one is the field with a deadline attached, so it is
            # surfaced rather than folded into `status`.
            "price_change": price_change.get("status") or "",
        })
    rows.sort(key=lambda r: (
        {"": "zz", UNREADABLE_DATE: "zy"}.get(r["next_charge"], r["next_charge"]),
        -(r["charge"] or 0.0),
        str(r["tutor"]),
    ))
    return rows


STOPPED = "STOPPED"


def _is_upcoming(row: dict[str, Any]) -> bool:
    """Whether this row represents a charge that is actually going to happen.

    Found by live verification of this very function: Preply keeps the *last*
    ``nextRefill`` on a stopped subscription, so 9 of 23 rows carried dates from
    2023-2025 with a real ``chargeAmount``. Counting anything non-null as
    upcoming produced a headline "next charge 2023-06-05" and a total that
    summed money nobody will ever be charged.

    A status this code has never seen is treated as upcoming and warned about,
    not as stopped: over-reporting a bill is a visible surprise, under-reporting
    one is an invisible surprise later.
    """
    return row["status"] not in (NO_SUBSCRIPTION, STOPPED, UNKNOWN, "")


def build_renewal_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Totals for upcoming subscription charges, with the gaps named.

    Charges in different currencies are never summed into one number: a total
    that silently mixes USD and EUR is worse than no total. Each currency gets
    its own subtotal, and rows whose amount could not be read are counted, not
    treated as zero.
    """
    rows = renewal_rows(snapshot)
    warnings: list[str] = []
    active = [r for r in rows if _is_upcoming(r)]
    today = datetime.now().date().isoformat()
    stale_dates = sum(
        1 for r in active
        if r["next_charge"] not in ("", UNREADABLE_DATE) and r["next_charge"] < today
    )
    unfamiliar = sorted({
        r["status"] for r in active if r["status"] not in ("CONFIGURED",)
    })

    by_currency: dict[str, float] = {}
    unreadable_charges = 0
    for row in active:
        if row["charge"] is None:
            unreadable_charges += 1
            continue
        by_currency[row["currency"] or UNKNOWN] = round(
            by_currency.get(row["currency"] or UNKNOWN, 0.0) + row["charge"], 2
        )

    undated = sum(1 for r in active if r["next_charge"] == UNREADABLE_DATE)
    unknown_status = sum(1 for r in rows if r["status"] == UNKNOWN)
    pending_price_changes = sum(1 for r in rows if r["price_change"])

    if unreadable_charges:
        warnings.append(
            f"{unreadable_charges} active subscription(s) have no readable charge "
            "amount - the per-currency totals below are a floor, not the full bill."
        )
    if undated:
        warnings.append(
            f"{undated} active subscription(s) have no readable next-charge date; "
            "they are NOT counted as 'no upcoming charge'."
        )
    if unknown_status:
        warnings.append(
            f"{unknown_status} subscription(s) have an unreadable status - excluded "
            "from the upcoming total, and NOT counted as stopped either."
        )
    if unfamiliar:
        warnings.append(
            f"unrecognised subscription status(es) {', '.join(unfamiliar)} counted as "
            "upcoming; only CONFIGURED has been verified against a live account."
        )
    if stale_dates:
        warnings.append(
            f"{stale_dates} upcoming charge(s) are dated in the past; Preply may be "
            "reporting a stale refill date."
        )

    next_charge_dates = sorted(
        r["next_charge"] for r in active
        if r["next_charge"] and r["next_charge"] != UNREADABLE_DATE
    )
    return {
        "tutorings": len(rows),
        "active_subscriptions": len(active),
        # Both non-charging states, kept apart: `refill: null` means the
        # tutoring never had (or lost) a subscription object, `STOPPED` means it
        # has one that was switched off. Preply models them separately.
        "stopped_subscriptions": sum(1 for r in rows if r["status"] == STOPPED),
        "no_subscription": sum(1 for r in rows if r["status"] == NO_SUBSCRIPTION),
        "charge_totals": by_currency,
        "charges_unreadable": unreadable_charges,
        "next_charge": next_charge_dates[0] if next_charge_dates else "",
        "pending_price_changes": pending_price_changes,
        "warnings": warnings,
    }


# -- Achievement certificates ---------------------------------------------
def certificate_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per subject certificate: hours done, level, and download link.

    ``completedHours`` arrives as a *string* while the level fields are ints, so
    it goes through ``_opt_number`` rather than being trusted as numeric.
    """
    rows = []
    for node in _dict_nodes((snapshot.get("certificates") or {}).get("allAchievementCertificates")):
        subject = node.get("subject") or {}
        rows.append({
            "subject": subject.get("translatedName") or subject.get("alias") or "",
            "completed_hours": _opt_number(node, "completedHours"),
            "level": _opt_int(node, "currentLevel"),
            "next_level": _opt_int(node, "nextLevel"),
            "hours_to_next": _opt_int(node, "hoursToNextLevel"),
            "download_url": _absolute_preply_url(node.get("downloadUrl")),
        })
    rows.sort(key=lambda r: -(r["completed_hours"] or 0.0))
    return rows


def build_certificate_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    rows = certificate_rows(snapshot)
    total, unreadable = _sum_or_unknown(rows, "completed_hours")
    warnings: list[str] = []
    if unreadable:
        warnings.append(
            f"{unreadable} certificate(s) have no readable completed-hours value; "
            "the total is a floor."
        )
    missing_links = sum(1 for r in rows if not r["download_url"])
    if missing_links:
        warnings.append(f"{missing_links} certificate(s) have no download URL.")
    return {
        "certificates": len(rows),
        "completed_hours_total": total,
        "subjects": sorted(r["subject"] for r in rows if r["subject"]),
        "warnings": warnings,
    }

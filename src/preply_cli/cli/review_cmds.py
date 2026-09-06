"""Public tutor profile reading. Needs no login and no stored session."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from ..formatting import format_table, money, shorten
from ..public_profile import PublicProfileError, load_tutor_profile
from ._shared import _emit, _print_json


def _tutor_review_rows(data: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    rows = []
    reviews = data.get("reviews") or []
    for review in reviews[:limit]:
        rows.append(
            {
                "date": review.get("date"),
                "reviewer": review.get("reviewer_name"),
                "score": review.get("score"),
                "lessons": review.get("reviewer_lesson_count"),
                "last_lesson": review.get("reviewer_last_lesson_at"),
                "language": review.get("language"),
                "review": shorten(review.get("content"), 120),
                "reply": shorten(review.get("tutor_reply"), 90),
            }
        )
    return rows


def cmd_tutor_reviews(args: argparse.Namespace) -> None:
    data = load_tutor_profile(args.source, timeout=args.timeout, proxy=getattr(args, "proxy", None))
    rows = _tutor_review_rows(data, limit=args.limit)
    if getattr(args, "json", False):
        _print_json(data)
        return
    if getattr(args, "csv", False):
        from ..formatting import format_csv
        print(
            format_csv(
                rows,
                ["date", "reviewer", "score", "lessons", "last_lesson", "language", "review", "reply"],
            ),
            end="",
        )
        return

    for warning in data.get("warnings") or []:
        print(f"warning: {warning}", file=sys.stderr)

    tutor = data.get("tutor") or {}
    analysis = data.get("analysis") or {}
    distribution = data.get("review_distribution") or {}
    tutor_summary = tutor.get("tutor_summary") or {}
    retention = analysis.get("retention") or {}

    is_accepting = tutor.get("is_accepting_new_students")
    if is_accepting is True:
        accepting_str = "Yes"
    elif is_accepting is False:
        accepting_str = "No (Overbooked/Paused)"
    else:
        accepting_str = "Unknown"

    hourly_rate = (tutor.get("hourly_rate") or {}).get("formatted")
    trial_rate = (tutor.get("trial_rate") or {}).get("formatted")

    rating_rows = [
        {"metric": "name", "value": tutor.get("name")},
        {"metric": "headline", "value": tutor.get("headline")},
        {"metric": "status", "value": tutor.get("status")},
        {"metric": "accepting_new_students", "value": accepting_str},
        {"metric": "hourly_rate", "value": hourly_rate or "-"},
        {"metric": "trial_rate", "value": trial_rate or "-"},
        {"metric": "rating", "value": tutor.get("average_score")},
        {"metric": "public_reviews", "value": tutor.get("number_reviews")},
        {"metric": "total_lessons", "value": tutor.get("total_lessons")},
        {"metric": "active_students", "value": tutor.get("active_students_count")},
        {"metric": "lessons_booked_last_48h", "value": tutor.get("lessons_booked_last_48h")},
        {"metric": "is_super_tutor", "value": "Yes" if tutor.get("is_super_tutor") else "No"},
        {"metric": "latest_student_lesson", "value": retention.get("most_recent_reviewer_lesson")},
        {"metric": "anonymous_lesson_reviews", "value": tutor.get("reviewed_lessons_count")},
        {"metric": "5_star_reviews", "value": distribution.get("5")},
        {"metric": "recent_review", "value": analysis.get("recent_review_date")},
        {"metric": "public_url", "value": tutor.get("public_url") or data.get("source_url")},
    ]
    reasoning_rows = [
        {"metric": "public_proof", "value": analysis.get("public_proof")},
        {"metric": "sentiment", "value": analysis.get("sentiment")},
        {"metric": "recommendation", "value": analysis.get("recommendation")},
        {"metric": "reviews_summary", "value": tutor.get("reviews_summary")},
        {"metric": "strengths", "value": tutor_summary.get("strengths")},
        {"metric": "teaching_style", "value": tutor_summary.get("teaching_style")},
        {"metric": "students_feedback", "value": tutor_summary.get("students_feedback")},
        {"metric": "cautions", "value": "; ".join(analysis.get("cautions") or [])},
    ]
    theme_counts = analysis.get("theme_counts") or {}
    theme_rows = [
        {"theme": theme, "hits": theme_counts.get(theme, "")}
        for theme in analysis.get("themes") or []
    ]
    print("Tutor")
    print(format_table(rating_rows, ["metric", "value"]))
    if is_accepting is False:
        print()
        print("⚠️  Notice: Tutor isn’t accepting new students. (This can happen when tutors get overbooked or temporarily paused.)")
    print()
    print("Review reasoning")
    print(format_table(reasoning_rows, ["metric", "value"]))
    if theme_rows:
        print()
        print("Themes")
        print(format_table(theme_rows, ["theme", "hits"]))

    recent_active = retention.get("recent_active_students") or []
    if recent_active:
        print()
        print(f"Recent student lessons (top {min(5, len(recent_active))} by last lesson date)")
        print(format_table(recent_active[:5], ["reviewer", "lessons", "last_lesson_at", "learning_goal", "review_date"]))

    retained = retention.get("long_term_reviewers") or []
    if retained:
        print()
        print(
            f"Long-term students ({retention.get('long_term_threshold')}+ lessons, "
            f"{retention.get('reviewers_with_lesson_counts')} of "
            f"{len(data.get('reviews') or [])} reviewers report a count)"
        )
        print(format_table(retained, ["reviewer", "lessons", "last_lesson_at", "learning_goal"]))
    print()
    print("Recent reviews")
    print(format_table(rows, ["date", "reviewer", "score", "lessons", "last_lesson", "review", "reply"]))



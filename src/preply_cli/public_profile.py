from __future__ import annotations

import json
import os
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen


class PublicProfileError(RuntimeError):
    pass


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_next_data = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self._in_next_data = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_next_data:
            self._in_next_data = False

    def handle_data(self, data: str) -> None:
        if self._in_next_data:
            self.parts.append(data)


def extract_next_data(html: str) -> dict[str, Any]:
    parser = _NextDataParser()
    parser.feed(html)
    raw = "".join(parser.parts).strip()
    if not raw:
        raise PublicProfileError("Could not find __NEXT_DATA__ on the Preply tutor profile page.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PublicProfileError(f"Could not parse Preply __NEXT_DATA__: {exc}") from exc


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_only(value: Any) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return str(value)[:10]


def _review_distribution(distribution: dict[str, Any]) -> dict[str, int]:
    return {
        "1": int(distribution.get("nr1Stars") or 0),
        "2": int(distribution.get("nr2Stars") or 0),
        "3": int(distribution.get("nr3Stars") or 0),
        "4": int(distribution.get("nr4Stars") or 0),
        "5": int(distribution.get("nr5Stars") or 0),
    }


def _normalize_tutor_summary(summary: dict[str, Any] | None) -> dict[str, str | None]:
    summary = summary or {}
    return {
        "strengths": summary.get("strengths"),
        "teaching_style": summary.get("teachingStyle"),
        "students_feedback": summary.get("studentsFeedback"),
        "user_learning_goal": summary.get("userLearningGoal"),
    }


def _normalize_subcategory_ratings(subcategories: dict[str, Any] | None) -> tuple[int | None, list[dict[str, Any]]]:
    subcategories = subcategories or {}
    ratings = []
    for rating in subcategories.get("ratings") or []:
        ratings.append(
            {
                "name": rating.get("name"),
                "rating": _float_or_none(rating.get("rating")),
                "type": rating.get("type"),
            }
        )
    return _int_or_none(subcategories.get("reviewedLessonsCount")), ratings


def _first_reply(review: dict[str, Any]) -> dict[str, Any]:
    replies = review.get("replies") or []
    return replies[0] if replies else {}


def _reviewer_info(review: dict[str, Any]) -> dict[str, Any]:
    """How many lessons this reviewer took, and when they last took one.

    Preply moved this. It used to be a flat `reviewerLessonCount` on the review (verified
    2026-06-13); by 2026-08-12 it lives at `reviewerInfo.lessonCount`, alongside a new
    `lastLessonAt` and `learningGoal`. A grep for the old key name finds nothing and reads as
    deletion, which is how this got recorded as "no longer exposed" on 2026-08-09 while the
    data was in fact still on the page. Read the new home first, keep the old one as a fallback,
    and let `_drift_warnings()` speak up if both ever go quiet.
    """
    info = review.get("reviewerInfo")
    info = info if isinstance(info, dict) else {}
    lesson_count = _int_or_none(info.get("lessonCount"))
    if lesson_count is None:
        lesson_count = _int_or_none(review.get("reviewerLessonCount"))
    return {
        "reviewer_lesson_count": lesson_count,
        "reviewer_last_lesson_at": _date_only(info.get("lastLessonAt")),
        "reviewer_learning_goal": info.get("learningGoal"),
    }


def _normalize_review(review: dict[str, Any]) -> dict[str, Any]:
    user = review.get("user") or {}
    reply = _first_reply(review)
    return {
        "id": review.get("id"),
        "score": _float_or_none(review.get("score")),
        "created": review.get("created"),
        "date": _date_only(review.get("created")),
        "language": review.get("language"),
        "content": (review.get("content") or "").strip(),
        "reviewer_name": user.get("firstName") or user.get("fullName"),
        **_reviewer_info(review),
        "tags": review.get("tags") or [],
        "tutor_reply": (reply.get("content") or "").strip(),
        "tutor_reply_created": reply.get("created"),
        "tutor_reply_language": reply.get("language"),
    }


# A reviewer at or above this many lessons is treated as a retained student rather than a
# trial-and-a-bit. It is a reporting cutoff, not a Preply concept: the ranked list is the real
# output and this only decides who gets counted in `long_term_reviewers`.
_LONG_TERM_LESSON_THRESHOLD = 20


def _retention(profile: dict[str, Any]) -> dict[str, Any]:
    """What the reviewer roster says about students who stayed.

    Each public review carries the reviewer's own lesson count, so the review list doubles as a
    (biased, reviewers-only) sample of the tutor's retention. `last_lesson_at` is the useful half:
    a 60-lesson student who stopped a year ago and one who sat a lesson yesterday are very
    different signals and the count alone cannot tell them apart.
    """
    reviews = profile.get("reviews") or []
    known = [review for review in reviews if _int_or_none(review.get("reviewer_lesson_count")) is not None]
    ranked = sorted(
        (
            {
                "reviewer": review.get("reviewer_name"),
                "lessons": _int_or_none(review.get("reviewer_lesson_count")),
                "last_lesson_at": review.get("reviewer_last_lesson_at") or "",
                "learning_goal": review.get("reviewer_learning_goal"),
                "review_date": review.get("date"),
            }
            for review in known
        ),
        key=lambda row: (-(row["lessons"] or 0), row["reviewer"] or ""),
    )
    lessons_represented = sum(row["lessons"] or 0 for row in ranked)
    total_lessons = _int_or_none((profile.get("tutor") or {}).get("total_lessons"))
    last_lesson_dates = sorted(row["last_lesson_at"] for row in ranked if row["last_lesson_at"])
    return {
        "reviewers_with_lesson_counts": len(ranked),
        "reviewers_missing_lesson_counts": len(reviews) - len(ranked),
        "long_term_reviewers": [
            row for row in ranked if (row["lessons"] or 0) >= _LONG_TERM_LESSON_THRESHOLD
        ],
        "long_term_threshold": _LONG_TERM_LESSON_THRESHOLD,
        "ranked_reviewers": ranked,
        "lessons_represented_by_reviewers": lessons_represented,
        # Reviewers are self-selected, so this is a floor on how concentrated the tutor's
        # teaching is among repeat students, never a population estimate.
        "reviewer_share_of_total_lessons": (
            round(lessons_represented / total_lessons, 4) if total_lessons else None
        ),
        "most_recent_reviewer_lesson": last_lesson_dates[-1] if last_lesson_dates else "",
        "earliest_reviewer_lesson": last_lesson_dates[0] if last_lesson_dates else "",
    }


def _drift_warnings(profile: dict[str, Any]) -> list[str]:
    """Say so when a field the parser depends on has gone quiet.

    `.get()` returning None is indistinguishable from "this tutor has no data", which is exactly
    how the reviewer lesson count stayed broken and undetected. Absent-for-everyone is the
    decidable version of "the payload shape moved", so it is worth an explicit line.
    """
    warnings: list[str] = []
    reviews = profile.get("reviews") or []
    if reviews and all(review.get("reviewer_lesson_count") is None for review in reviews):
        warnings.append(
            f"No reviewer lesson count on any of {len(reviews)} reviews. This field has moved once "
            "before (flat reviewerLessonCount -> reviewerInfo.lessonCount). Re-inspect the keys of "
            "props.pageProps.reviews[0] before concluding Preply stopped publishing it."
        )
    return warnings


def parse_tutor_profile_html(html: str, source_url: str = "") -> dict[str, Any]:
    next_data = extract_next_data(html)
    page_props = ((next_data.get("props") or {}).get("pageProps") or {})
    tutor = page_props.get("tutor") or {}
    reviewed_lessons_count, subcategory_ratings = _normalize_subcategory_ratings(
        tutor.get("subcategoriesRatings")
    )
    profile = {
        "source_url": source_url or tutor.get("publicUrl") or "",
        "tutor": {
            "id": tutor.get("id"),
            "name": tutor.get("fullName"),
            "headline": tutor.get("headline"),
            "public_url": tutor.get("publicUrl") or source_url,
            "average_score": _float_or_none(tutor.get("averageScore")),
            "number_reviews": _int_or_none(tutor.get("numberReviews")),
            "total_lessons": _int_or_none(tutor.get("totalLessons")),
            "active_students_count": _int_or_none(tutor.get("activeStudentsCount")),
            "years_of_experience": _int_or_none(tutor.get("yearsOfExperience")),
            "reviewed_lessons_count": reviewed_lessons_count,
            "reviews_summary": tutor.get("reviewsSummary"),
            "tutor_summary": _normalize_tutor_summary(page_props.get("tutorSummary")),
            "subcategory_ratings": subcategory_ratings,
        },
        "review_distribution": _review_distribution(page_props.get("reviewDistribution") or {}),
        "reviews": [_normalize_review(review) for review in page_props.get("reviews") or []],
    }
    profile["analysis"] = build_tutor_review_analysis(profile)
    profile["warnings"] = _drift_warnings(profile)
    return profile


def _theme_counts(profile: dict[str, Any]) -> dict[str, int]:
    texts = [
        profile.get("tutor", {}).get("reviews_summary") or "",
        *((profile.get("tutor", {}).get("tutor_summary") or {}).values()),
        *(review.get("content") or "" for review in profile.get("reviews") or []),
    ]
    corpus = "\n".join(str(text).lower() for text in texts if text)
    theme_keywords = {
        "clear explanations": ["clear", "clarity", "explain", "explaining", "simple", "steps", "breaks"],
        "patience": ["patient", "patience", "kind"],
        "beginner-friendly": ["beginner", "first lesson", "complete beginner", "new songs"],
        "adaptive lessons": ["adapt", "custom", "customizes", "needs", "interests"],
        "engaging lessons": ["engaged", "engaging", "enjoyable", "friendly", "fun", "groove"],
        "music theory and technique": ["theory", "technique", "chords", "guitar", "playing", "music"],
    }
    counts: dict[str, int] = {}
    for theme, keywords in theme_keywords.items():
        count = sum(corpus.count(keyword) for keyword in keywords)
        if count:
            counts[theme] = count
    return counts


def build_tutor_review_analysis(profile: dict[str, Any]) -> dict[str, Any]:
    tutor = profile.get("tutor") or {}
    reviews = profile.get("reviews") or []
    distribution = profile.get("review_distribution") or {}
    # These gate the public_proof verdict below. Substituting 0 (or the length
    # of whatever review page happened to load) for a field Preply moved would
    # downgrade a strong tutor to "limited" and read as evidence of weakness
    # rather than of missing data - so track unreadability explicitly.
    raw_review_count = _int_or_none(tutor.get("number_reviews"))
    raw_total_lessons = _int_or_none(tutor.get("total_lessons"))
    proof_inputs_unreadable = raw_review_count is None or raw_total_lessons is None
    review_count = raw_review_count if raw_review_count is not None else len(reviews)
    total_lessons = raw_total_lessons or 0
    reviewed_lessons_count = int(tutor.get("reviewed_lessons_count") or 0)
    average_score = _float_or_none(tutor.get("average_score")) or 0.0
    five_star_count = int(distribution.get("5") or 0)
    negative_count = sum(int(distribution.get(str(stars)) or 0) for stars in range(1, 4))
    theme_counts = _theme_counts(profile)
    themes = [
        theme
        for theme, _count in sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    dates = [_date_only(review.get("created")) for review in reviews if review.get("created")]
    recent_review_date = max(dates) if dates else ""
    if proof_inputs_unreadable:
        # A fourth bucket: we cannot classify, which is not the same as weak.
        public_proof = "unknown"
    elif review_count >= 50 and total_lessons >= 1000 and average_score >= 4.8:
        public_proof = "strong"
    elif review_count >= 10 and total_lessons >= 100 and average_score >= 4.5:
        public_proof = "moderate"
    else:
        public_proof = "limited"
    if average_score >= 4.8 and negative_count == 0 and review_count:
        sentiment = "overwhelmingly positive"
    elif average_score >= 4.5:
        sentiment = "positive"
    else:
        sentiment = "mixed"
    if public_proof == "strong":
        recommendation = (
            "Strong candidate if the learner wants patient, structured guitar coaching with clear explanations."
        )
    elif public_proof == "moderate":
        recommendation = "Promising candidate; inspect recent reviews and schedule fit before choosing."
    else:
        recommendation = "Review evidence is limited; use a trial lesson or compare with more-reviewed tutors."
    cautions: list[str] = []
    if negative_count:
        cautions.append(f"{negative_count} public reviews are below 4 stars.")
    if review_count < 10:
        cautions.append("Small public review sample.")
    if not cautions:
        cautions.append("No negative public-review pattern found in the fetched reviews.")
    return {
        "public_proof": public_proof,
        "sentiment": sentiment,
        "themes": themes,
        "theme_counts": theme_counts,
        "recommendation": recommendation,
        "cautions": cautions,
        "recent_review_date": recent_review_date,
        "five_star_share": round(five_star_count / review_count, 4) if review_count else None,
        "reviewed_lessons_count": reviewed_lessons_count,
        "retention": _retention(profile),
    }


def _source_url(source: str) -> str:
    if source.isdigit():
        return f"https://preply.com/en/tutor/{source}"
    return source


def fetch_tutor_profile(source: str, timeout: int = 30, proxy: str | None = None) -> dict[str, Any]:
    from . import __version__
    from .transport import resolve_proxy_url

    url = _source_url(source)
    resolved_proxy = resolve_proxy_url(proxy)

    request = Request(
        url,
        headers={
            "User-Agent": f"Mozilla/5.0 (compatible; preply-account-cli/{__version__}; +https://preply.com)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    custom_proxy = proxy or os.environ.get("PREPLY_PROXY_URL") or os.environ.get("DATAIMPULSE_PROXY_URL")
    try:
        if custom_proxy:
            resolved_proxy = resolve_proxy_url(custom_proxy)
            opener = build_opener(ProxyHandler({"http": resolved_proxy, "https": resolved_proxy}))
            with opener.open(request, timeout=timeout) as response:
                html = response.read().decode("utf-8")
        else:
            with urlopen(request, timeout=timeout) as response:
                html = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            raise PublicProfileError(
                f"No public Preply profile at {url} (HTTP 404). Check the tutor id or URL."
            ) from exc
        if exc.code in (403, 429):
            raise PublicProfileError(
                f"Preply refused the request for {url} (HTTP {exc.code}). This is usually "
                "bot protection on the public site rather than a problem with the tutor id; "
                "open the page in a browser to confirm it exists, then retry later."
            ) from exc
        raise PublicProfileError(f"Could not fetch {url}: HTTP {exc.code} {exc.reason}.") from exc
    except URLError as exc:
        raise PublicProfileError(f"Could not reach {url}: {exc.reason}.") from exc
    except TimeoutError as exc:
        raise PublicProfileError(f"Timed out after {timeout}s fetching {url}.") from exc
    return parse_tutor_profile_html(html, url)


def _looks_like_host(source: str) -> bool:
    """Whether `source` starts with something shaped like a hostname."""
    head = source.split("/", 1)[0]
    return "." in head and " " not in head and not head.startswith(".")


def load_tutor_profile(source: str, timeout: int = 30, proxy: str | None = None) -> dict[str, Any]:
    if source.startswith(("http://", "https://")) or source.isdigit():
        return fetch_tutor_profile(source, timeout=timeout, proxy=proxy)
    # A scheme-less URL ("preply.com/en/tutor/123") is a URL the user forgot to
    # prefix, not a filename. Treating it as a path produced a FileNotFoundError
    # naming a nonsensical path under the current directory.
    if "/" in source and not Path(source).expanduser().exists() and _looks_like_host(source):
        return fetch_tutor_profile(f"https://{source}", timeout=timeout, proxy=proxy)
    path = Path(source).expanduser().resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublicProfileError(
            f"cannot read {str(path)!r}: {exc.strerror}. Pass a tutor URL, a numeric "
            "tutor id, or the path of a saved profile page."
        ) from exc
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PublicProfileError(
                f"{str(path)!r} is not valid JSON ({exc.msg}, line {exc.lineno})."
            ) from exc
        if "props" in data:
            page_props = (data.get("props") or {}).get("pageProps") or {}
            html = (
                "<script id=\"__NEXT_DATA__\" type=\"application/json\">"
                + json.dumps({"props": {"pageProps": page_props}})
                + "</script>"
            )
            return parse_tutor_profile_html(html, str(path))
        if "tutor" in data and "reviews" in data:
            data["analysis"] = build_tutor_review_analysis(data)
            data["warnings"] = _drift_warnings(data)
            return data
    return parse_tutor_profile_html(text, str(path))

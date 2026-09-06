import json
import unittest
from pathlib import Path

from preply_cli.public_profile import (
    build_tutor_review_analysis,
    load_tutor_profile,
    parse_tutor_profile_html,
)

FIXTURES = Path(__file__).parent / "fixtures"
# A structurally faithful capture of a real public tutor profile (2026-08-12).
# Real nesting, real counts, scores and dates -- that is what makes it a useful
# regression: it is what caught `reviewerInfo.lessonCount` moving.
#
# Identities are scrubbed. The tutor id, names, avatar URLs and free-text review
# bodies are replaced with placeholders; every structural field is untouched. The
# page is public, but republishing a scrape of a dozen named strangers inside a
# public repo is a different act from linking to it, and no assertion here needs
# a real name. If these tests ever start depending on one, that is the bug.
REAL_CAPTURE = FIXTURES / "public_tutor_anon_2026-08-12.json"


def _html_with_next_data(page_props):
    payload = {
        "props": {"pageProps": page_props},
        "page": "/public-tutor-profile",
        "query": {"tutorId": "2807691"},
    }
    return (
        "<html><head></head><body>"
        f"<script id=\"__NEXT_DATA__\" type=\"application/json\">{json.dumps(payload)}</script>"
        "</body></html>"
    )


class PublicProfileTests(unittest.TestCase):
    def test_parse_tutor_profile_html_extracts_stats_reviews_and_replies(self):
        html = _html_with_next_data(
            {
                "tutor": {
                    "id": 2807691,
                    "fullName": "Andres R.",
                    "headline": "More than 10 years of experience teaching Guitar",
                    "totalLessons": 2680,
                    "activeStudentsCount": 18,
                    "lessonsBookedLast48h": 5,
                    "isSuperTutor": True,
                    "numberReviews": 56,
                    "averageScore": 5,
                    "publicUrl": "https://preply.com/en/tutor/2807691",
                    "reviewsSummary": "Students broadly praise Andres for clear, patient guitar teaching.",
                    "subcategoriesRatings": {
                        "reviewedLessonsCount": 105,
                        "ratings": [{"name": "Clarity", "rating": "4.8", "type": "CLARITY"}],
                    },
                },
                "tutorSummary": {
                    "strengths": "Andres customizes lessons for all skill levels.",
                    "teachingStyle": "He uses real music as backing tracks.",
                    "studentsFeedback": "Students say Andres is kind and patient.",
                },
                "reviewDistribution": {"nr1Stars": 0, "nr2Stars": 0, "nr3Stars": 0, "nr4Stars": 0, "nr5Stars": 56},
                "reviews": [
                    {
                        "id": 2709067,
                        "score": 5,
                        "content": "Amazing and engaged teacher for my son -- Highly recommend!",
                        "created": "2026-06-12T00:56:24.253919+00:00",
                        "language": "en",
                        "reviewerLessonCount": 49,
                        "user": {"firstName": "Prinon"},
                        "replies": [
                            {
                                "content": "Thanks, Mr. Prinon!! Keep rocking!!",
                                "created": "2026-06-12T00:57:15.923611+00:00",
                                "language": "en",
                            }
                        ],
                    }
                ],
            }
        )

        profile = parse_tutor_profile_html(html, "https://preply.com/en/tutor/2807691")

        self.assertEqual(profile["tutor"]["name"], "Andres R.")
        self.assertEqual(profile["tutor"]["total_lessons"], 2680)
        self.assertEqual(profile["tutor"]["active_students_count"], 18)
        self.assertEqual(profile["tutor"]["lessons_booked_last_48h"], 5)
        self.assertTrue(profile["tutor"]["is_super_tutor"])
        self.assertEqual(profile["tutor"]["number_reviews"], 56)
        self.assertEqual(profile["tutor"]["reviewed_lessons_count"], 105)
        self.assertEqual(profile["review_distribution"]["5"], 56)
        self.assertEqual(profile["reviews"][0]["reviewer_name"], "Prinon")
        self.assertEqual(profile["reviews"][0]["tutor_reply"], "Thanks, Mr. Prinon!! Keep rocking!!")

    def test_build_tutor_review_analysis_highlights_evidence_and_fit(self):
        profile = {
            "tutor": {
                "name": "Andres R.",
                "average_score": 5,
                "number_reviews": 56,
                "total_lessons": 2680,
                "reviewed_lessons_count": 105,
                "reviews_summary": "Students broadly praise Andres for clear, patient guitar teaching that adapts lessons.",
                "tutor_summary": {
                    "strengths": "Andres customizes lessons for beginners and advanced students.",
                    "teaching_style": "He uses real music and simple steps.",
                    "students_feedback": "Students say Andres is kind, patient, and excellent.",
                },
            },
            "review_distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 56},
            "reviews": [
                {
                    "score": 5,
                    "content": "He is very patient with my mistakes and explains things clearly.",
                    "created": "2026-05-22T18:29:11.934323+00:00",
                    "reviewer_lesson_count": 3,
                },
                {
                    "score": 5,
                    "content": "Great first lesson for a complete beginner learning guitar.",
                    "created": "2026-06-09T02:22:19.199144+00:00",
                    "reviewer_lesson_count": 2,
                },
            ],
        }

        analysis = build_tutor_review_analysis(profile)

        self.assertEqual(analysis["public_proof"], "strong")
        self.assertIn("clear explanations", analysis["themes"])
        self.assertIn("patience", analysis["themes"])
        self.assertIn("beginner-friendly", analysis["themes"])
        self.assertIn("Strong candidate", analysis["recommendation"])
        self.assertEqual(analysis["recent_review_date"], "2026-06-09")


class ReviewerLessonCountContractTests(unittest.TestCase):
    """Locks where the per-reviewer lesson count lives in Preply's public payload.

    Scope: this pins the parser against a real capture. It proves the code reads today's shape;
    it cannot prove Preply has not moved the field again since the capture date. `_drift_warnings`
    is what covers the live case, and it is asserted in both directions below.
    """

    def test_real_capture_yields_a_lesson_count_for_every_reviewer(self):
        profile = load_tutor_profile(str(REAL_CAPTURE))

        counts = [review["reviewer_lesson_count"] for review in profile["reviews"]]
        self.assertEqual(len(counts), 10)
        self.assertTrue(
            all(isinstance(count, int) for count in counts),
            f"reviewerInfo.lessonCount stopped parsing; got {counts}",
        )
        self.assertEqual(sorted(counts, reverse=True)[:3], [67, 62, 49])
        self.assertEqual(profile["warnings"], [])

    def test_real_capture_dates_each_reviewer_last_lesson(self):
        profile = load_tutor_profile(str(REAL_CAPTURE))

        last_lessons = [review["reviewer_last_lesson_at"] for review in profile["reviews"]]
        self.assertTrue(all(last_lessons), f"reviewerInfo.lastLessonAt stopped parsing; got {last_lessons}")
        self.assertEqual(max(last_lessons), "2026-08-11")

    def test_retention_ranks_long_term_students_ahead_of_short_ones(self):
        profile = load_tutor_profile(str(REAL_CAPTURE))

        retention = profile["analysis"]["retention"]
        self.assertEqual(retention["reviewers_with_lesson_counts"], 10)
        self.assertEqual(retention["reviewers_missing_lesson_counts"], 0)
        self.assertEqual(retention["ranked_reviewers"][0]["lessons"], 67)
        self.assertEqual(retention["lessons_represented_by_reviewers"], 319)
        # 6 of 10 reviewers are at or above the 20-lesson cutoff.
        self.assertEqual(len(retention["long_term_reviewers"]), 6)
        recent_active = retention["recent_active_students"]
        self.assertEqual(len(recent_active), 10)
        self.assertEqual(recent_active[0]["last_lesson_at"], "2026-08-11")

    def test_legacy_flat_reviewer_lesson_count_still_parses(self):
        """Captures taken before Preply nested the field must keep working."""
        html = _html_with_next_data(
            {
                "tutor": {"id": 1, "fullName": "Legacy T.", "totalLessons": 10},
                "reviews": [{"id": 1, "score": 5, "content": "ok", "reviewerLessonCount": 49}],
            }
        )

        profile = parse_tutor_profile_html(html, "https://preply.com/en/tutor/1")

        self.assertEqual(profile["reviews"][0]["reviewer_lesson_count"], 49)
        self.assertEqual(profile["warnings"], [])

    def test_missing_from_both_locations_warns_with_the_remedy(self):
        """The guard must go RED when the field moves again, not return a quiet None."""
        html = _html_with_next_data(
            {
                "tutor": {"id": 1, "fullName": "Moved T.", "totalLessons": 10},
                "reviews": [{"id": 1, "score": 5, "content": "ok", "reviewerInfo": {"somethingElse": 3}}],
            }
        )

        profile = parse_tutor_profile_html(html, "https://preply.com/en/tutor/1")

        self.assertEqual(profile["reviews"][0]["reviewer_lesson_count"], None)
        self.assertEqual(len(profile["warnings"]), 1)
        self.assertIn("reviewerInfo.lessonCount", profile["warnings"][0])


if __name__ == "__main__":
    unittest.main()

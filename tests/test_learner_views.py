"""Tests for the learner lesson/subscription/stats extractors.

Payload shapes mirror live 2026-08-13 responses (redacted names).
"""
import unittest

from preply_cli import analysis as A
from preply_cli.queries import operation_names


def past_lessons_payload():
    return {"lessons": {"currentUser": {"id": 1, "client": {"id": 2, "pastLessons": {
        "hasNext": False,
        "nodes": [
            {"id": 10, "datetime": "2026-08-11T07:00:00+00:00", "duration": 1.0,
             "status": "COMPLETED", "paidAmount": "14.0000", "isRated": True,
             "isFirstLesson": False,
             "tutor": {"id": 9, "user": {"id": 8, "firstName": "Mai"}},
             "tutoring": {"id": 5, "lead": {"subject": {"translatedName": "Vietnamese"}}},
             "rating": {"id": 1, "amount": 5}},
            {"id": 11, "datetime": "2026-06-20T08:00:00+00:00", "duration": 1.0,
             "status": "COMPLETED", "paidAmount": "10.0000", "isRated": False,
             "tutor": {"id": 7, "user": {"id": 6, "firstName": "Victor"}},
             "tutoring": {"id": 4, "lead": {"subject": {"translatedName": "Music"}}},
             "rating": None},
        ],
    }}}}}


class LessonRowsTest(unittest.TestCase):
    def test_rows_sorted_recent_first_and_fields(self):
        rows = A.lesson_rows(past_lessons_payload())
        self.assertEqual([r["lesson_id"] for r in rows], [10, 11])
        self.assertEqual(rows[0]["subject"], "Vietnamese")
        self.assertEqual(rows[0]["tutor"], "Mai")
        self.assertEqual(rows[0]["rating"], 5)  # isRated True
        self.assertEqual(rows[1]["rating"], "")  # isRated False -> blank

    def test_summary_totals(self):
        summary = A.build_lesson_summary(past_lessons_payload())
        self.assertEqual(summary["lesson_count"], 2)
        self.assertEqual(summary["hours_total"], 2.0)
        self.assertEqual(summary["paid_total"], 24.0)
        self.assertEqual(summary["status_counts"], {"COMPLETED": 2})
        self.assertEqual(summary["lessons_by_subject"], {"Music": 1, "Vietnamese": 1})

    def test_empty_snapshot_safe(self):
        self.assertEqual(A.lesson_rows({}), [])
        self.assertEqual(A.build_lesson_summary({})["lesson_count"], 0)


class UpcomingRowsTest(unittest.TestCase):
    def test_handles_both_node_shapes_sorted_soonest_first(self):
        payload = {"upcoming": {"currentUser": {"client": {"upcomingLessons": {"nodes": [
            {"__typename": "LessonNode", "id": 20,
             "datetime": "2026-10-02T09:00:00+00:00", "duration": 1.0,
             "status": "BOOKED", "paidAmount": "10.0000",
             "tutor": {"user": {"firstName": "Victor"}},
             "tutoring": {"lead": {"subject": {"translatedName": "Music"}}}},
            # reservation node: tutor under tutoring.tutor, no top-level status,
            # conflictReason present-but-null (the normal, non-conflicting case).
            {"__typename": "RecurrentLessonReservationNode", "id": 21,
             "datetime": "2026-08-14T07:00:00+00:00", "duration": 1.0,
             "conflictReason": None,
             "tutoring": {"lead": {"subject": {"translatedName": "Music"}},
                          "tutor": {"user": {"firstName": "Andres"}}}},
        ]}}}}}
        rows = A.upcoming_rows(payload)
        self.assertEqual([r["lesson_id"] for r in rows], [21, 20])  # soonest first
        self.assertEqual(rows[0]["tutor"], "Andres")  # from tutoring.tutor
        self.assertEqual(rows[0]["status"], "RESERVED")  # non-conflicting reservation
        self.assertEqual(rows[1]["status"], "BOOKED")


class TutoringRowsTest(unittest.TestCase):
    def test_rows_sorted_by_lessons_desc(self):
        payload = {"tutorings": {"currentUser": {"client": {"tutorings": {"nodes": [
            {"id": 1, "pricePerHourUsd": 6.0, "confirmedLessonsCount": 43,
             "created": "2023-03-25T00:00:00+00:00",
             "tutor": {"user": {"firstName": "Tomas"}},
             "lead": {"subject": {"translatedName": "Spanish"}},
             "refill": None},
            {"id": 2, "pricePerHourUsd": 14.0, "confirmedLessonsCount": 52,
             "created": "2024-10-06T00:00:00+00:00",
             "tutor": {"user": {"firstName": "Mai"}},
             "lead": {"subject": {"translatedName": "Vietnamese"}},
             "refill": {"status": "CONFIGURED", "refillHours": 1.0}},
        ]}}}}}
        rows = A.tutoring_rows(payload)
        self.assertEqual([r["tutor"] for r in rows], ["Mai", "Tomas"])  # 52 > 43
        self.assertEqual(rows[0]["subscription"], "CONFIGURED")
        self.assertEqual(rows[0]["since"], "2024-10-06")
        # A null refill means the subscription really stopped. It must not render
        # as a blank cell, which is indistinguishable from a status we failed to
        # read (that case is UNKNOWN - see test_unreadable_status_is_distinct).
        self.assertEqual(rows[1]["subscription"], "NO_SUBSCRIPTION")

    def test_unreadable_status_is_distinct_from_a_stopped_subscription(self):
        payload = {"tutorings": {"currentUser": {"client": {"tutorings": {"nodes": [
            {"id": 1, "confirmedLessonsCount": 5,
             "tutor": {"user": {"firstName": "Ada"}},
             "lead": {"subject": {"translatedName": "Spanish"}},
             # refill present and billing, but `status` moved
             "refill": {"refillHours": 1.0}},
        ]}}}}}
        self.assertEqual(A.tutoring_rows(payload)[0]["subscription"], "UNKNOWN")


class StatsTest(unittest.TestCase):
    def test_lifetime_stats(self):
        payload = {"stats": {"currentUser": {"client": {"learningActivities": {
            "lifetimeStats": {"highestLessonStreak": 33, "lessonsCompleted": 249,
                              "practicesCompleted": 0}}}}}}
        stats = A.learner_lifetime_stats(payload)
        self.assertEqual(stats["highest_lesson_streak"], 33)
        self.assertEqual(stats["lessons_completed"], 249)

    def test_empty_safe(self):
        self.assertEqual(A.learner_lifetime_stats({})["lessons_completed"], None)


class QueriesRegisteredTest(unittest.TestCase):
    def test_new_operations_present(self):
        names = operation_names()
        for name in ("CurrentUserPastLessons", "CurrentUserUpcomingLessons",
                     "UserActiveTutorings", "ClientLifetimeStats"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()

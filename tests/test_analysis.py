import unittest

from preply_cli.analysis import build_account_summary, build_payment_summary, build_timeline


class AnalysisTests(unittest.TestCase):
    def test_build_account_summary_counts_statuses_and_revenue(self):
        snapshot = {
            "profile": {
                "currentUser": {
                    "tutor": {
                        "studentManagementTutorings": {
                            "totalCount": 3,
                            "nodes": [
                                {
                                    "status": "ACTIVE_SUBSCRIPTION",
                                    "confirmedLessonsCount": 4,
                                    "totalTutorRevenue": 100.5,
                                    "pricePerHourUsd": 25,
                                },
                                {
                                    "status": "TRIAL",
                                    "confirmedLessonsCount": 1,
                                    "totalTutorRevenue": 0,
                                    "pricePerHourUsd": 20,
                                },
                                {
                                    "status": "PACKAGE",
                                    "confirmedLessonsCount": 2,
                                    "totalTutorRevenue": "50.25",
                                    "pricePerHourUsd": "18.50",
                                },
                            ],
                        }
                    }
                }
            },
            "wallet": {"currentUser": {"wallet": {"balance": 12.3}}},
        }

        summary = build_account_summary(snapshot)

        self.assertEqual(summary["student_total"], 3)
        self.assertEqual(summary["status_counts"]["ACTIVE_SUBSCRIPTION"], 1)
        self.assertEqual(summary["status_counts"]["TRIAL"], 1)
        self.assertEqual(summary["confirmed_lessons_total"], 7)
        self.assertAlmostEqual(summary["student_revenue_total_usd"], 150.75)
        self.assertAlmostEqual(summary["wallet_balance"], 12.3)
        self.assertEqual(summary["price_range_usd"], {"min": 18.5, "max": 25.0})

    def test_build_timeline_sorts_schedule_and_past_lessons(self):
        snapshot = {
            "schedule": {
                "currentUser": {
                    "tutor": {
                        "calendar": {
                            "nodes": [
                                {
                                    "dateStart": "2026-05-28T11:30:00+00:00",
                                    "dateEnd": "2026-05-28T12:20:00+00:00",
                                    "lesson": {
                                        "id": 22,
                                        "status": "BOOKED",
                                        "duration": 50,
                                        "client": {"user": {"fullName": "B"}},
                                        "tutoring": {"id": 2, "clientName": "B"},
                                    },
                                }
                            ]
                        }
                    }
                }
            },
            "student_details": {
                "1": {
                    "pastLessons": {
                        "tutoring": {
                            "pastLessons": {
                                "nodes": [
                                    {
                                        "id": 11,
                                        "datetime": "2026-05-20T10:00:00+00:00",
                                        "status": "COMPLETED",
                                        "duration": 50,
                                        "earnedAmount": 15,
                                    }
                                ]
                            }
                        }
                    }
                }
            },
        }

        timeline = build_timeline(snapshot)

        self.assertEqual([item["kind"] for item in timeline], ["past_lesson", "upcoming_lesson"])
        self.assertEqual(timeline[0]["lesson_id"], 11)
        self.assertEqual(timeline[1]["student_name"], "B")

    def test_build_payment_summary_totals_learner_history(self):
        snapshot = {
            "history": {
                "paymentsHistory": {
                    "payments": [
                        {"subject": "Music", "amount": 8.3, "hours": 1, "currencyCode": "USD"},
                        {"subject": "Music", "amount": "15.30", "hours": 1, "currencyCode": "USD"},
                        {"subject": "Spanish", "amount": 13.65, "hours": 1, "currencyCode": "USD"},
                    ],
                    "hasNext": False,
                }
            }
        }

        summary = build_payment_summary(snapshot)

    def test_student_nodes_with_none_tutor(self):
        # When tutor is None (e.g. learner account)
        snapshot = {
            "profile": {
                "currentUser": {
                    "tutor": None
                }
            }
        }
        from preply_cli.analysis import student_nodes
        nodes = student_nodes(snapshot)
        self.assertEqual(nodes, [])

    def test_build_account_summary_with_none_wallet(self):
        snapshot = {
            "profile": {
                "currentUser": {
                    "tutor": None
                }
            },
            "wallet": {
                "currentUser": {
                    "wallet": None
                }
            }
        }
        summary = build_account_summary(snapshot)
        self.assertEqual(summary["wallet_balance"], 0.0)
        self.assertEqual(summary["student_total"], 0)


if __name__ == "__main__":
    unittest.main()

"""Structural robustness: no extractor may crash on a malformed payload.

A CLI that raises `TypeError: 'NoneType' object is not subscriptable` at the
user is only marginally better than one that prints a wrong number. Preply can
return null at any level (a learner has no `tutor`, a stopped subscription has
no `refill`, a cold account has no `client`), and a partially-typed response is
exactly what a mid-deploy fetch looks like.

Every extractor is fed the same hostile matrix: missing keys, explicit nulls at
each nesting level, wrong container types, and wrong scalar types. The contract
is only that it returns *something* without raising — correctness of the values
is covered by the payload-shape tests elsewhere.
"""
import unittest

from preply_cli import analysis as A

# Values chosen to break naive `x["k"]` / `x.get("k").get("j")` / arithmetic.
HOSTILE = [
    {},
    {"balance": None},
    {"balance": {}},
    {"balance": {"balanceManagementData": None}},
    {"balance": {"balanceManagementData": {"nodes": None}}},
    {"balance": {"balanceManagementData": {"nodes": [None]}}},
    {"balance": {"balanceManagementData": {"nodes": [{}]}}},
    {"balance": {"balanceManagementData": {"nodes": [{"tutoring": None, "refill": None}]}}},
    {"balance": {"balanceManagementData": {"totalBalance": "not-a-number", "nodes": []}}},
    {"balance": {"balanceManagementData": {"totalBalance": [1, 2], "nodes": []}}},
    {"lessons": None},
    {"lessons": {"currentUser": None}},
    {"lessons": {"currentUser": {"client": None}}},
    {"lessons": {"currentUser": {"client": {"pastLessons": {"nodes": [None]}}}}},
    {"lessons": {"currentUser": {"client": {"pastLessons": {"nodes": [{"duration": "x"}]}}}}},
    {"upcoming": {"currentUser": {"client": {"upcomingLessons": {"nodes": [{}]}}}}},
    {"tutorings": {"currentUser": {"client": {"tutorings": {"nodes": [{"refill": None}]}}}}},
    {"tutorings": {"currentUser": {"client": {"tutorings": {"nodes": [{"lessons": None}]}}}}},
    {"stats": {"currentUser": {"client": {"learningActivities": None}}}},
    {"wallet_client": {"currentUser": {"client": {"leads": None}}}},
    {"wallet_client": {"currentUser": {"client": {"leads": {"nodes": [None]}}}}},
    {"wallet_client": {"currentUser": {"client": {"user": None}}}},
    {"subscription": {"currentUser": {"client": None}}},
    {"unread": {"currentUser": {"messageThreads": None}}},
    {"chat": None},
    {"chat": {"chat": None}},
    {"chat": {"chat": {"messages": None}}},
    {"chat": {"chat": {"messages": {"nodes": [None]}}}},
    {"chat": {"chat": {"messages": {"nodes": [{"files": None}]}}}},
    {"chat": {"currentUser": None, "chat": {"collocutorUser": None,
                                            "messages": {"nodes": [{"authorId": 1}]}}}},
    {"profile": {"currentUser": {"tutor": None}}},
    {"history": {"paymentsHistory": None}},
    {"history": {"paymentsHistory": {"payments": [None]}}},
    {"history": {"paymentsHistory": {"payments": [{"amount": {}}]}}},
    {"schedule": {"currentUser": {"tutor": None}}},
]

ROW_EXTRACTORS = [
    A.balance_rows, A.pending_payment_rows, A.lesson_rows, A.upcoming_rows,
    A.tutoring_rows, A.chat_rows, A.student_nodes, A.payment_nodes,
    A.balance_nodes, A.chat_message_nodes, A.lesson_nodes,
    A.upcoming_lesson_nodes, A.tutoring_nodes, A.build_timeline,
]

DICT_EXTRACTORS = [
    A.build_balance_summary, A.learner_wallet_context, A.learner_subscription_state,
    A.learner_lifetime_stats, A.build_lesson_summary, A.build_account_summary,
    A.build_payment_summary, A.chat_context, A.build_chat_summary,
]


class MalformedPayloadTest(unittest.TestCase):
    def test_row_extractors_return_a_list_and_never_raise(self):
        for payload in HOSTILE:
            for fn in ROW_EXTRACTORS:
                with self.subTest(fn=fn.__name__, payload=payload):
                    result = fn(payload)
                    self.assertIsInstance(result, list)

    def test_dict_extractors_return_a_dict_and_never_raise(self):
        for payload in HOSTILE:
            for fn in DICT_EXTRACTORS:
                with self.subTest(fn=fn.__name__, payload=payload):
                    self.assertIsInstance(fn(payload), dict)

    def test_unread_count_never_raises(self):
        for payload in HOSTILE:
            with self.subTest(payload=payload):
                A.unread_message_count(payload)

    def test_summaries_always_expose_a_warnings_list(self):
        """Callers print summary['warnings'] unconditionally."""
        for payload in HOSTILE:
            for fn in (A.build_balance_summary, A.build_account_summary,
                       A.build_payment_summary, A.build_lesson_summary):
                with self.subTest(fn=fn.__name__):
                    self.assertIsInstance(fn(payload).get("warnings"), list)

    def test_balance_rows_stay_sortable_when_numbers_are_unreadable(self):
        """Sorting on a None hour count must not raise a TypeError."""
        payload = {"balance": {"balanceManagementData": {"nodes": [
            {"tutoring": {"hours": None}, "refill": None},
            {"tutoring": {"hours": 2.0}, "unscheduledLessons": 2.0,
             "refill": {"status": "CONFIGURED", "nextRefill": "2026-09-01T00:00:00+00:00"}},
            {"tutoring": {"hours": "bad"}, "refill": {"status": "CONFIGURED"}},
        ]}}}
        rows = A.balance_rows(payload)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["next_charge"], "2026-09-01")


if __name__ == "__main__":
    unittest.main()

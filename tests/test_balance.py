"""Tests for the learner balance / dashboard extractors.

Payload shapes mirror live 2026-08-13 responses (names redacted). The important
shape is the one Preply actually returns: a balance node whose ``refill`` is
null because the subscription was stopped, while the tutoring still holds paid
hours. Those rows must survive with a NO_SUBSCRIPTION marker rather than being
dropped or crashing on the missing dict.
"""
import unittest

from preply_cli import analysis as A
from preply_cli.queries import operation_names


def balance_payload():
    return {"balance": {"balanceManagementData": {
        "totalBalance": 3.0,
        "totalNodesCount": 3,
        "nodes": [
            # Active monthly subscription, hour already tied to a booked lesson.
            {"unavailableLessons": 1.0, "unscheduledLessons": 0.0,
             "lead": {"subject": {"alias": "music"}},
             "refill": {"status": "CONFIGURED", "billingFrequency": "MONTHLY",
                        "nextRefill": "2026-08-15T07:02:47.966581+00:00",
                        "nextSubscription": "2026-08-15T07:02:47.966581+00:00"},
             "tutoring": {"id": 9909441, "hours": 0.0,
                          "tutor": {"user": {"firstName": "Victor"}}}},
            # Active subscription with an idle paid hour.
            {"unavailableLessons": 0.0, "unscheduledLessons": 1.0,
             "lead": {"subject": {"alias": "music"}},
             "refill": {"status": "CONFIGURED", "billingFrequency": "MONTHLY",
                        "nextRefill": "2026-08-22T03:13:40.283394+00:00",
                        "nextSubscription": "2026-08-22T03:13:40.283394+00:00"},
             "tutoring": {"id": 9909569, "hours": 1.0,
                          "tutor": {"user": {"firstName": "Andres"}}}},
            # Stopped subscription: refill is null, hours still banked.
            {"unavailableLessons": 0.0, "unscheduledLessons": 2.0,
             "lead": {"subject": {"alias": "spanish"}},
             "refill": None,
             "tutoring": {"id": 3113005, "hours": 2.0,
                          "tutor": {"user": {"firstName": "Diana"}}}},
        ],
    }}}


def wallet_payload():
    return {"wallet_client": {"currentUser": {"client": {
        "isEnterprise": False,
        "passedHours": 254.0,
        "user": {"profile": {"countryCode": "VN",
                             "currency": {"code": "USD", "translatedCode": "$"}}},
        "leads": {"nodes": [
            {"id": 12961634, "pricePerHourUsd": 19.5,
             "tutor": {"status": "APPROVED",
                       "user": {"fullName": "Song Won L.",
                                "profile": {"countryCode": "AU"}}}},
            {"id": 10696480, "pricePerHourUsd": 7.0,
             "tutor": {"status": "APPROVED",
                       "user": {"fullName": "Anthony M.",
                                "profile": {"countryCode": "VE"}}}},
        ]},
    }}}}


class BalanceRowsTest(unittest.TestCase):
    def test_null_refill_becomes_no_subscription_not_a_crash(self):
        rows = A.balance_rows(balance_payload())
        stopped = next(r for r in rows if r["tutor"] == "Diana")
        self.assertEqual(stopped["status"], "NO_SUBSCRIPTION")
        self.assertEqual(stopped["next_charge"], "")
        self.assertEqual(stopped["hours"], 2.0)
        self.assertEqual(stopped["unscheduled"], 2.0)

    def test_sorted_soonest_charge_first_then_unsubscribed_last(self):
        rows = A.balance_rows(balance_payload())
        self.assertEqual([r["tutor"] for r in rows], ["Victor", "Andres", "Diana"])

    def test_next_charge_is_date_only(self):
        rows = A.balance_rows(balance_payload())
        self.assertEqual(rows[0]["next_charge"], "2026-08-15")

    def test_empty_snapshot_safe(self):
        self.assertEqual(A.balance_rows({}), [])


class BalanceSummaryTest(unittest.TestCase):
    def test_totals_and_counts(self):
        summary = A.build_balance_summary(balance_payload())
        self.assertEqual(summary["total_balance_hours"], 3.0)
        self.assertEqual(summary["unscheduled_hours"], 3.0)
        self.assertEqual(summary["unavailable_hours"], 1.0)
        self.assertEqual(summary["active_subscriptions"], 2)
        self.assertEqual(summary["without_subscription"], 1)
        self.assertEqual(summary["next_charge"], "2026-08-15")
        self.assertEqual(summary["upcoming_charges"], ["2026-08-15", "2026-08-22"])

    def test_summed_rows_kept_separate_from_reported_total(self):
        """A server/row mismatch must stay visible, not be reconciled away."""
        payload = balance_payload()
        payload["balance"]["balanceManagementData"]["totalBalance"] = 99.0
        summary = A.build_balance_summary(payload)
        self.assertEqual(summary["total_balance_hours"], 99.0)
        self.assertEqual(summary["summed_row_hours"], 3.0)

    def test_empty_snapshot_reports_unknown_not_a_confident_zero(self):
        """An absent balance is unknown. Reporting 0.0 would be a false fact."""
        summary = A.build_balance_summary({})
        self.assertIsNone(summary["total_balance_hours"])
        self.assertIsNone(summary["next_charge"])
        self.assertEqual(summary["summed_row_hours"], 0.0)


class SilentFailureRegressionTest(unittest.TestCase):
    """Guards for four failure modes reproduced live on 2026-08-14.

    Each previously produced a confident, plausible, wrong answer about money.
    The shared shape: Preply moves a field, the payload stays GraphQL-valid, and
    a `.get(...) or default` turns the absence into a specific wrong number.
    """

    def _one_node(self, refill, hours=1.0):
        return {"balance": {"balanceManagementData": {
            "totalBalance": 1.0, "totalNodesCount": 1, "nodes": [
                {"unavailableLessons": 0.0, "unscheduledLessons": 0.0,
                 "lead": {"subject": {"alias": "music"}},
                 "refill": refill,
                 "tutoring": {"id": 1, "hours": hours,
                              "tutor": {"user": {"firstName": "Victor"}}}},
            ]}}}

    def test_moved_status_field_is_not_reported_as_stopped(self):
        # `status` gone but nextRefill present => actively billing.
        payload = self._one_node(
            {"billingFrequency": "MONTHLY", "nextRefill": "2026-09-01T00:00:00+00:00"})
        row = A.balance_rows(payload)[0]
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertNotEqual(row["status"], "NO_SUBSCRIPTION")
        self.assertEqual(row["next_charge"], "2026-09-01")
        summary = A.build_balance_summary(payload)
        self.assertEqual(summary["without_subscription"], 0)
        self.assertEqual(summary["unknown_status"], 1)
        self.assertTrue(any("unreadable status" in w for w in summary["warnings"]))

    def test_moved_date_fields_do_not_claim_nothing_is_scheduled(self):
        payload = self._one_node({"status": "CONFIGURED", "billingFrequency": "MONTHLY"})
        summary = A.build_balance_summary(payload)
        self.assertEqual(A.balance_rows(payload)[0]["next_charge"], "?")
        self.assertTrue(any("no readable charge date" in w for w in summary["warnings"]))

    def test_restructured_total_balance_is_unknown_not_zero(self):
        payload = self._one_node(None)
        payload["balance"]["balanceManagementData"]["totalBalance"] = {
            "amount": 3.0, "unit": "HOUR"}
        summary = A.build_balance_summary(payload)
        self.assertIsNone(summary["total_balance_hours"])
        self.assertTrue(any("could not be read" in w for w in summary["warnings"]))

    def test_divergence_between_reported_total_and_row_sum_is_warned(self):
        payload = self._one_node(None, hours=1.0)
        payload["balance"]["balanceManagementData"]["totalBalance"] = 99.0
        summary = A.build_balance_summary(payload)
        self.assertEqual(summary["total_balance_hours"], 99.0)
        self.assertEqual(summary["summed_row_hours"], 1.0)
        self.assertTrue(any("does not match" in w for w in summary["warnings"]))

    def test_healthy_payload_produces_no_warnings(self):
        """The warning channel must stay quiet when nothing is wrong."""
        summary = A.build_balance_summary(balance_payload())
        self.assertEqual(summary["warnings"], [])

    def test_unreadable_hours_do_not_silently_shrink_the_total(self):
        payload = self._one_node(None, hours=None)
        summary = A.build_balance_summary(payload)
        self.assertTrue(any("unreadable hours" in w for w in summary["warnings"]))

    def test_zero_totalNodesCount_is_not_replaced_by_row_count(self):
        payload = self._one_node(None)
        payload["balance"]["balanceManagementData"]["totalNodesCount"] = 0
        self.assertEqual(A.build_balance_summary(payload)["tutoring_count"], 0)


class WalletContextTest(unittest.TestCase):
    def test_pending_payment_rows_sorted_by_price_desc(self):
        rows = A.pending_payment_rows(wallet_payload())
        self.assertEqual([r["tutor"] for r in rows], ["Song Won L.", "Anthony M."])
        self.assertEqual(rows[0]["country"], "AU")
        self.assertEqual(rows[0]["price_usd"], 19.5)

    def test_wallet_context(self):
        context = A.learner_wallet_context(wallet_payload())
        self.assertEqual(context["passed_hours"], 254.0)
        self.assertEqual(context["currency"], "USD")
        self.assertEqual(context["country"], "VN")
        self.assertIs(context["is_enterprise"], False)

    def test_empty_safe(self):
        self.assertEqual(A.pending_payment_rows({}), [])
        self.assertIsNone(A.learner_wallet_context({})["currency"])


class SubscriptionAndUnreadTest(unittest.TestCase):
    def test_subscription_state(self):
        payload = {"subscription": {"currentUser": {"client": {
            "subscriptionType": "SUBSCRIBE_TO_TUTOR", "isActiveSubscriber": True}}}}
        state = A.learner_subscription_state(payload)
        self.assertEqual(state["subscription_type"], "SUBSCRIBE_TO_TUTOR")
        self.assertIs(state["is_active_subscriber"], True)

    def test_unread_count(self):
        payload = {"unread": {"currentUser": {"messageThreads": {"unreadCount": 3}}}}
        self.assertEqual(A.unread_message_count(payload), 3)

    def test_empty_safe(self):
        self.assertIsNone(A.unread_message_count({}))
        self.assertIsNone(A.learner_subscription_state({})["subscription_type"])


class QueriesRegisteredTest(unittest.TestCase):
    def test_new_operations_present(self):
        names = operation_names()
        for name in ("BalanceManagementData", "UserSubscriptionsData",
                     "ChatUnreadCounter", "ClientWallet"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()

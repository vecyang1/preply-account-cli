"""Renewals (the money side of a subscription) and achievement certificates.

Payload shapes mirror live 2026-08-14 responses from `SettingsTutoringList` and
`AllAchievementCertificate` (names and ids replaced). The distribution that
matters is the real one: of 23 tutorings, 11 had `refill: null`, 9 were
`STOPPED`, and only 3 were `CONFIGURED`.
"""
from datetime import datetime, timedelta
import unittest

from preply_cli import analysis as A
from preply_cli.queries import operation_names

FUTURE_DATE = (datetime.now().date() + timedelta(days=30)).isoformat()
FUTURE_REFILL = f"{FUTURE_DATE}T00:00:00+00:00"


def renewal_node(
    *, tutoring_id, tutor, subject, status="CONFIGURED", charge=10.5,
    next_refill=FUTURE_REFILL, currency="USD", refill=True,
    price_change=None, prepaid=0.0,
):
    node = {
        "id": tutoring_id,
        "hours": 1.0,
        "totalPrepaidHours": prepaid,
        "paymentsCount": 26,
        "lead": {"id": 1, "subject": {"id": 2, "translatedName": subject}},
        "tutor": {"id": 9, "user": {"id": 9, "fullName": tutor, "firstName": tutor}},
        "priceChangeRequestStatus": price_change,
        "refill": None,
    }
    if refill:
        node["refill"] = {
            "id": 3,
            "hours": 1.0,
            "chargeAmount": charge,
            "nextRefill": next_refill,
            "nextSubscription": next_refill,
            "status": status,
            "type": "SUBSCRIBE_TO_TUTOR",
            "currency": {"id": 1, "code": currency},
            "refillFrequency": "MONTHLY",
            "refillHours": 1.0,
            "billingFrequency": "MONTHLY",
        }
    return node


def renewals_payload(nodes):
    return {"renewals": {"currentUser": {"id": 1, "client": {"id": 2, "tutorings": {"nodes": nodes}}}}}


class UpcomingVsStopped(unittest.TestCase):
    """The bug live verification caught: STOPPED rows keep a real old date."""

    def setUp(self):
        self.payload = renewals_payload([
            renewal_node(tutoring_id=1, tutor="Active", subject="Music",
                         charge=10.5, next_refill=FUTURE_REFILL),
            # Preply keeps the last refill date and amount after a stop. Summing
            # these produced a headline "next charge 2023-06-05" and a total of
            # 436.80 USD that nobody would ever be charged.
            renewal_node(tutoring_id=2, tutor="Stopped", subject="Japanese",
                         status="STOPPED", charge=46.2,
                         next_refill="2023-06-05T00:00:00+00:00"),
            renewal_node(tutoring_id=3, tutor="NoSub", subject="French", refill=False),
        ])

    def test_stopped_rows_do_not_set_the_next_charge_date(self):
        summary = A.build_renewal_summary(self.payload)
        self.assertEqual(FUTURE_DATE, summary["next_charge"])

    def test_stopped_rows_are_not_added_to_the_bill(self):
        summary = A.build_renewal_summary(self.payload)
        self.assertEqual({"USD": 10.5}, summary["charge_totals"])

    def test_stopped_and_no_subscription_are_counted_separately(self):
        summary = A.build_renewal_summary(self.payload)
        self.assertEqual(1, summary["active_subscriptions"])
        self.assertEqual(1, summary["stopped_subscriptions"])
        self.assertEqual(1, summary["no_subscription"])
        self.assertEqual(3, summary["tutorings"])

    def test_healthy_payload_warns_about_nothing(self):
        self.assertEqual([], A.build_renewal_summary(self.payload)["warnings"])


class CurrencyHandling(unittest.TestCase):
    def test_currencies_are_never_summed_together(self):
        payload = renewals_payload([
            renewal_node(tutoring_id=1, tutor="A", subject="S", charge=10.0, currency="USD"),
            renewal_node(tutoring_id=2, tutor="B", subject="S", charge=20.0, currency="EUR"),
        ])
        totals = A.build_renewal_summary(payload)["charge_totals"]
        self.assertEqual({"USD": 10.0, "EUR": 20.0}, totals)


class RenewalFieldDrift(unittest.TestCase):
    def test_a_moved_chargeAmount_is_counted_as_unreadable_not_zero(self):
        node = renewal_node(tutoring_id=1, tutor="A", subject="S")
        del node["refill"]["chargeAmount"]
        summary = A.build_renewal_summary(renewals_payload([node]))
        self.assertIsNone(A.renewal_rows(renewals_payload([node]))[0]["charge"])
        self.assertEqual({}, summary["charge_totals"])
        self.assertEqual(1, summary["charges_unreadable"])
        self.assertTrue(any("floor" in w for w in summary["warnings"]))

    def test_a_moved_status_is_excluded_from_the_bill_but_not_called_stopped(self):
        node = renewal_node(tutoring_id=1, tutor="A", subject="S")
        del node["refill"]["status"]
        payload = renewals_payload([node])
        self.assertEqual("UNKNOWN", A.renewal_rows(payload)[0]["status"])
        summary = A.build_renewal_summary(payload)
        self.assertEqual(0, summary["active_subscriptions"])
        self.assertEqual(0, summary["stopped_subscriptions"])
        self.assertTrue(any("NOT counted as stopped" in w for w in summary["warnings"]))

    def test_a_moved_date_does_not_read_as_no_upcoming_charge(self):
        node = renewal_node(tutoring_id=1, tutor="A", subject="S")
        del node["refill"]["nextRefill"]
        del node["refill"]["nextSubscription"]
        payload = renewals_payload([node])
        self.assertEqual("?", A.renewal_rows(payload)[0]["next_charge"])
        summary = A.build_renewal_summary(payload)
        self.assertEqual("", summary["next_charge"])
        self.assertTrue(any("no readable next-charge date" in w for w in summary["warnings"]))

    def test_an_unfamiliar_status_counts_toward_the_bill_and_warns(self):
        # Under-reporting a bill is an invisible surprise later; over-reporting
        # is a visible one now. Unknown-but-present statuses go in, loudly.
        payload = renewals_payload([
            renewal_node(tutoring_id=1, tutor="A", subject="S", status="PAUSED", charge=7.0)
        ])
        summary = A.build_renewal_summary(payload)
        self.assertEqual(1, summary["active_subscriptions"])
        self.assertEqual({"USD": 7.0}, summary["charge_totals"])
        self.assertTrue(any("PAUSED" in w for w in summary["warnings"]))

    def test_a_past_dated_active_charge_is_flagged(self):
        payload = renewals_payload([
            renewal_node(tutoring_id=1, tutor="A", subject="S",
                         next_refill="2020-01-01T00:00:00+00:00")
        ])
        summary = A.build_renewal_summary(payload)
        self.assertTrue(any("dated in the past" in w for w in summary["warnings"]))

    def test_null_nodes_do_not_crash(self):
        self.assertEqual([], A.renewal_rows(renewals_payload([None, None])))
        self.assertEqual([], A.renewal_rows({}))


class Certificates(unittest.TestCase):
    def payload(self, nodes):
        return {"certificates": {"allAchievementCertificates": nodes}}

    def node(self, subject="Spanish", hours="94.50", level=90, nxt=100, to_next=5,
             url="/en/achievement-certificate/1"):
        return {
            "currentLevel": level,
            "nextLevel": nxt,
            "hoursToNextLevel": to_next,
            "downloadUrl": url,
            "subject": {"id": 1, "alias": subject.lower(), "translatedName": subject},
            "completedHours": hours,
        }

    def test_string_hours_are_parsed_and_levels_stay_integers(self):
        # Live shape: completedHours is a *string* while the levels are ints.
        row = A.certificate_rows(self.payload([self.node()]))[0]
        self.assertEqual(94.5, row["completed_hours"])
        self.assertEqual(90, row["level"])
        self.assertIsInstance(row["level"], int)

    def test_root_relative_download_url_is_made_absolute(self):
        row = A.certificate_rows(self.payload([self.node()]))[0]
        self.assertEqual("https://preply.com/en/achievement-certificate/1", row["download_url"])

    def test_protocol_relative_url_is_made_absolute(self):
        row = A.certificate_rows(self.payload([self.node(url="//cdn.preply.com/c/1")]))[0]
        self.assertEqual("https://cdn.preply.com/c/1", row["download_url"])

    def test_absolute_url_is_left_alone(self):
        url = "https://preply.com/en/achievement-certificate/1"
        row = A.certificate_rows(self.payload([self.node(url=url)]))[0]
        self.assertEqual(url, row["download_url"])

    def test_rows_sort_by_hours_descending(self):
        rows = A.certificate_rows(self.payload([
            self.node(subject="French", hours="43.0"),
            self.node(subject="Spanish", hours="94.5"),
        ]))
        self.assertEqual(["Spanish", "French"], [r["subject"] for r in rows])

    def test_unreadable_hours_are_not_summed_as_zero(self):
        node = self.node()
        del node["completedHours"]
        summary = A.build_certificate_summary(self.payload([node, self.node(hours="10.0")]))
        self.assertEqual(10.0, summary["completed_hours_total"])
        self.assertTrue(any("floor" in w for w in summary["warnings"]))

    def test_missing_download_url_is_reported(self):
        node = self.node()
        del node["downloadUrl"]
        summary = A.build_certificate_summary(self.payload([node]))
        self.assertTrue(any("no download URL" in w for w in summary["warnings"]))

    def test_healthy_payload_is_silent(self):
        self.assertEqual([], A.build_certificate_summary(self.payload([self.node()]))["warnings"])

    def test_null_nodes_do_not_crash(self):
        self.assertEqual([], A.certificate_rows(self.payload([None])))
        self.assertEqual([], A.certificate_rows({}))


class OperationsRegistered(unittest.TestCase):
    def test_new_operations_are_in_the_registry(self):
        names = operation_names()
        for name in ("SettingsTutoringList", "AllAchievementCertificate", "UnconfirmedLessons"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()

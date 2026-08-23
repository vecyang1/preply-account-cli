"""Regression guards for the "a moved Preply field became a wrong number" class.

An audit on 2026-08-14 demonstrated seven instances where a renamed or moved
GraphQL field was silently converted into a confident, plausible, wrong value.
The response stays GraphQL-valid, so nothing raises; the user simply reads a
different number than the truth. The project has been bitten by this in
production before (commit 4f3df3f).

Each test below reconstructs one demonstrated failure and asserts the value is
now reported as unknown, as a floor, or with a warning - never as a confident
fact. Payloads deliberately omit the moved key rather than setting it to None,
which is how a rename actually presents.
"""
import unittest
from unittest import mock

from preply_cli import analysis as A
from preply_cli.client import PreplyClient
from preply_cli.public_profile import build_tutor_review_analysis


def tutor_snapshot(students, total_count=..., wallet=...):
    connection = {"nodes": students}
    if total_count is not ...:
        connection["totalCount"] = total_count
    wallet_block = {} if wallet is ... else wallet
    return {
        "profile": {"currentUser": {"tutor": {"studentManagementTutorings": connection}}},
        "wallet": {"currentUser": {"wallet": wallet_block}},
    }


class AccountSummaryDriftTest(unittest.TestCase):
    def test_moved_wallet_balance_is_unknown_not_zero(self):
        snapshot = tutor_snapshot([], wallet={"amount": 1234.56})  # `balance` moved
        summary = A.build_account_summary(snapshot)
        self.assertIsNone(summary["wallet_balance"])
        self.assertTrue(any("Wallet balance" in w for w in summary["warnings"]))

    def test_moved_revenue_and_lesson_fields_are_warned_as_a_floor(self):
        students = [
            {"id": 1, "earnings": 1200.0, "lessons": 55},  # both fields moved
            {"id": 2, "totalTutorRevenue": 100.0, "confirmedLessonsCount": 5},
        ]
        summary = A.build_account_summary(tutor_snapshot(students, total_count=2))
        self.assertEqual(summary["student_revenue_total_usd"], 100.0)
        self.assertEqual(summary["confirmed_lessons_total"], 5)
        self.assertTrue(any("unreadable revenue" in w for w in summary["warnings"]))
        self.assertTrue(any("unreadable lesson count" in w for w in summary["warnings"]))

    def test_moved_total_count_warns_instead_of_reporting_the_page_as_the_account(self):
        students = [{"id": i} for i in range(20)]
        summary = A.build_account_summary(tutor_snapshot(students))  # totalCount absent
        self.assertEqual(summary["student_total"], 20)
        self.assertTrue(any("totalCount" in w for w in summary["warnings"]))

    def test_healthy_account_payload_is_silent(self):
        students = [{"id": 1, "totalTutorRevenue": 10.0, "confirmedLessonsCount": 2}]
        summary = A.build_account_summary(
            tutor_snapshot(students, total_count=1, wallet={"balance": 5.0})
        )
        self.assertEqual(summary["warnings"], [])
        self.assertEqual(summary["wallet_balance"], 5.0)


class PaymentSummaryDriftTest(unittest.TestCase):
    def test_moved_amount_is_a_warned_floor_not_zero_spend(self):
        snapshot = {"history": {"paymentsHistory": {"payments": [
            {"id": 1, "value": 50.0},   # `amount` moved
            {"id": 2, "amount": 75.0},
        ]}}}
        summary = A.build_payment_summary(snapshot)
        self.assertEqual(summary["spent_total"], 75.0)
        self.assertTrue(any("unreadable amount" in w for w in summary["warnings"]))

    def test_healthy_payments_are_silent(self):
        snapshot = {"history": {"paymentsHistory": {"payments": [
            {"id": 1, "amount": 50.0, "hours": 1.0},
        ]}}}
        self.assertEqual(A.build_payment_summary(snapshot)["warnings"], [])


class LessonSummaryDriftTest(unittest.TestCase):
    def test_moved_duration_and_paid_are_warned(self):
        snapshot = {"lessons": {"currentUser": {"client": {"pastLessons": {"nodes": [
            {"id": 1, "minutes": 60, "price": 40.0},  # both moved
            {"id": 2, "duration": 1.0, "paidAmount": 14.0},
        ]}}}}}
        summary = A.build_lesson_summary(snapshot)
        self.assertEqual(summary["hours_total"], 1.0)
        self.assertEqual(summary["paid_total"], 14.0)
        self.assertTrue(any("unreadable duration" in w for w in summary["warnings"]))
        self.assertTrue(any("unreadable paid amount" in w for w in summary["warnings"]))


class PaginationDriftTest(unittest.TestCase):
    """A renamed continuation flag must never be reported as 'nothing more'."""

    def _client(self, pages, drop_keys=0):
        """Fake transport that honours EVERY OperationCall in a batch.

        The first version of this fake answered only ``operation_calls[0]``,
        which made it structurally incapable of noticing that
        ``_extend_student_pages`` bundles many calls into one ``_fetch``. A
        batch-response defect passed it silently. ``drop_keys`` deliberately
        omits N responses so the under-fetch path can be exercised.
        """
        batches = []

        def fake_fetch(operation_calls):
            batches.append(list(operation_calls))
            index = len(batches) - 1
            answered = operation_calls[: len(operation_calls) - drop_keys] \
                if drop_keys else operation_calls
            return {
                call.key: pages[min(index, len(pages) - 1)]
                for call in answered
            }

        client = PreplyClient(browser=mock.Mock())
        client._fetch = fake_fetch  # type: ignore[method-assign]
        client.batches = batches
        client.calls = batches  # backwards-compatible alias
        return client

    def test_lessons_moved_has_next_reports_more_may_exist(self):
        """The whole point of 'unknown': do not claim the data ended.

        This previously asserted `hasNext is False` and rationalised it as
        "truncation is not claimed either way" - locking the defect in as
        expected behaviour. With limit 50 and a 20-row page the old expression
        `(has_next or unknown) and len(nodes) >= limit` evaluated to False, i.e.
        exactly the confident "nothing more" it was meant to prevent.
        """
        page = {"currentUser": {"client": {"pastLessons": {
            # `hasNext` renamed to `has_more`
            "has_more": True,
            "nodes": [{"id": i, "duration": 1.0} for i in range(20)],
        }}}}
        client = self._client([page])
        data = client.learner_lessons(limit=50)
        connection = data["lessons"]["currentUser"]["client"]["pastLessons"]
        self.assertIs(connection["hasNext"], True)
        self.assertTrue(any("hasNext" in w for w in data["_warnings"]))

    def test_drift_on_a_later_page_is_not_swallowed(self):
        """Page 1 healthy, page 2 drifted: previously silent with hasNext False."""
        healthy = {"currentUser": {"client": {"pastLessons": {
            "hasNext": True,
            "nodes": [{"id": i, "duration": 1.0} for i in range(20)],
        }}}}
        drifted = {"currentUser": {"client": {"pastLessons": {
            "has_more": True,  # renamed on the follow-up page
            "nodes": [{"id": i, "duration": 1.0} for i in range(20, 40)],
        }}}}
        client = self._client([healthy, drifted])
        data = client.learner_lessons(limit=100)
        connection = data["lessons"]["currentUser"]["client"]["pastLessons"]
        self.assertIs(connection["hasNext"], True)
        self.assertTrue(any("follow-up page" in w for w in data["_warnings"]))

    def test_payments_drift_on_a_later_page_is_not_swallowed(self):
        healthy = {"paymentsHistory": {"hasNext": True,
                                       "payments": [{"id": 1, "amount": 5.0}]}}
        drifted = {"paymentsHistory": {"has_more": True,
                                       "payments": [{"id": 2, "amount": 6.0}]}}
        client = self._client([healthy, drifted])
        data = client.payment_history(limit=100)
        self.assertTrue(any("follow-up page" in w for w in data["_warnings"]))

    def test_payments_moved_has_next_warns(self):
        page = {"paymentsHistory": {"payments": [{"id": 1, "amount": 5.0}]}}
        client = self._client([page])
        data = client.payment_history(limit=100)
        self.assertTrue(any("hasNext" in w for w in data["_warnings"]))

    def test_healthy_pagination_emits_no_warning(self):
        page = {"currentUser": {"client": {"pastLessons": {
            "hasNext": False,
            "nodes": [{"id": 1, "duration": 1.0}],
        }}}}
        data = self._client([page]).learner_lessons(limit=50)
        self.assertEqual(data.get("_warnings", []), [])

    def test_students_moved_total_count_still_pages(self):
        """Falling back to len(nodes) made target_count equal page one, so
        pagination stopped immediately and reported that page as the account."""
        page = {"currentUser": {"tutor": {"studentManagementTutorings": {
            "nodes": [{"id": i} for i in range(20)],  # no totalCount
        }}}}
        client = self._client([page])
        data = client.students(limit=100)
        self.assertGreater(len(client.calls), 1, "must keep paging when total is unknown")
        self.assertTrue(any("totalCount" in w for w in data["_warnings"]))


class PublicProofDriftTest(unittest.TestCase):
    def test_moved_counts_yield_unknown_not_limited(self):
        """A strong tutor must not be downgraded to 'limited' by missing data."""
        profile = {
            "tutor": {"average_score": 4.95, "reviewed_lessons_count": 100},
            "reviews": [{"created": "2026-08-01", "content": "great"}],
            "review_distribution": {"5": 480},
        }
        analysis = build_tutor_review_analysis(profile)
        self.assertEqual(analysis["public_proof"], "unknown")

    def test_readable_counts_still_classify_strong(self):
        profile = {
            "tutor": {"average_score": 4.95, "number_reviews": 500,
                      "total_lessons": 12000, "reviewed_lessons_count": 100},
            "reviews": [{"created": "2026-08-01", "content": "great"}],
            "review_distribution": {"5": 480},
        }
        self.assertEqual(build_tutor_review_analysis(profile)["public_proof"], "strong")


if __name__ == "__main__":
    unittest.main()


class BatchAmplificationTest(unittest.TestCase):
    """A drifted totalCount must not turn --limit into thousands of aliased
    sub-operations in one live request, and a partial batch response must not
    pass as a complete account."""

    def _client(self, responder):
        batches = []

        def fake_fetch(operation_calls):
            batches.append(list(operation_calls))
            return responder(list(operation_calls), len(batches))

        client = PreplyClient(browser=mock.Mock())
        client._fetch = fake_fetch  # type: ignore[method-assign]
        client.batches = batches
        return client

    @staticmethod
    def _students(nodes):
        return {"currentUser": {"tutor": {"studentManagementTutorings": {"nodes": nodes}}}}

    def test_unknown_total_caps_the_batch_size(self):
        def responder(calls, _n):
            return {c.key: self._students([]) for c in calls}

        client = self._client(responder)
        client.students(limit=100_000)  # totalCount absent from every page
        biggest = max(len(b) for b in client.batches)
        self.assertLessEqual(biggest, client.max_unknown_total_pages)

    def test_partial_batch_response_is_warned_not_reported_as_complete(self):
        def responder(calls, n):
            if n == 1:
                return {calls[0].key: self._students([{"id": i} for i in range(20)])}
            return {c.key: self._students([]) for c in calls[:-1]}  # drop one page

        data = self._client(responder).students(limit=100)
        self.assertTrue(
            any("did not come back" in w for w in data.get("_warnings", [])),
            "a silently dropped page must not pass as the whole account",
        )

    def test_known_total_needs_no_cap_and_emits_no_warning(self):
        def responder(calls, n):
            if n == 1:
                page = self._students([{"id": i} for i in range(20)])
                page["currentUser"]["tutor"]["studentManagementTutorings"]["totalCount"] = 40
                return {calls[0].key: page}
            return {c.key: self._students([{"id": i} for i in range(20, 40)]) for c in calls}

        data = self._client(responder).students(limit=100)
        self.assertEqual(data.get("_warnings", []), [])


class WarningPrecisionTest(unittest.TestCase):
    """A channel that cries wolf gets ignored, so silence must be meaningful."""

    def _client(self, payload):
        client = PreplyClient(browser=mock.Mock())
        client._fetch = lambda calls: {calls[0].key: payload}  # type: ignore[method-assign]
        return client

    def test_learner_account_does_not_warn_about_a_student_total(self):
        """Caught live: a learner has no tutor block, so totalCount is
        legitimately absent - that is not drift."""
        data = self._client({"currentUser": {"tutor": None}}).students(limit=10)
        self.assertEqual(data.get("_warnings", []), [])

    def test_tutor_with_students_but_no_total_still_warns(self):
        payload = {"currentUser": {"tutor": {"studentManagementTutorings": {
            "nodes": [{"id": 1}],  # loaded rows but no totalCount => real drift
        }}}}
        data = self._client(payload).students(limit=10)
        self.assertTrue(any("totalCount" in w for w in data.get("_warnings", [])))

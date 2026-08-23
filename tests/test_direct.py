import json
import unittest

from preply_cli.browser import OperationCall
from preply_cli.direct import DirectHttpClient, PreplyDirectError
from preply_cli.queries import get_operation


def make_http(responses):
    """Return a fake http_post that maps operationName -> (status, payload)."""
    calls = []

    def http_post(url, headers, body, timeout):
        calls.append((url, headers, body))
        name = body["operationName"]
        status, payload = responses[name]
        return status, json.dumps(payload)

    http_post.calls = calls
    return http_post


IDENTITY_OK = {
    "data": {"currentUser": {"id": "42", "firstName": "Ada", "fullName": "Ada Lovelace",
                             "tutor": {"id": "9"}}}
}


class DirectHttpClientTest(unittest.TestCase):
    def test_fetch_keys_by_call_key_and_injects_account(self):
        http = make_http({
            "PreplyCliAccountIdentity": (200, IDENTITY_OK),
            "TutorWallet": (200, {"data": {"currentUser": {"wallet": {"balance": 12}}}}),
        })
        client = DirectHttpClient(sessionid="s", csrftoken="c", http_post=http)
        result = client.fetch_graphql(
            [OperationCall("wallet", get_operation("TutorWallet"), {})]
        )
        self.assertEqual(result["wallet"], {"currentUser": {"wallet": {"balance": 12}}})
        self.assertEqual(result["_account"]["userId"], "42")
        self.assertEqual(result["_account"]["role"], "tutor")
        self.assertEqual(result["_account"]["tutorId"], "9")
        self.assertEqual(result["_account"]["name"], "Ada Lovelace")

    def test_learner_role_when_no_tutor(self):
        identity = {"data": {"currentUser": {"id": "7", "fullName": "Bo", "tutor": None}}}
        http = make_http({
            "PreplyCliAccountIdentity": (200, identity),
            "ChatThreadSummaries": (200, {"data": {"currentUser": {"messageThreads": {"nodes": []}}}}),
        })
        client = DirectHttpClient(sessionid="s", http_post=http)
        result = client.fetch_graphql(
            [OperationCall("messages", get_operation("ChatThreadSummaries"), {})]
        )
        self.assertEqual(result["_account"]["role"], "learner")
        self.assertIsNone(result["_account"]["tutorId"])

    def test_sends_csrf_header_and_cookie(self):
        http = make_http({"PreplyCliAccountIdentity": (200, IDENTITY_OK)})
        client = DirectHttpClient(sessionid="sess", csrftoken="tok", http_post=http)
        client.resolve_account()
        _url, headers, _body = http.calls[0]
        self.assertIn("sessionid=sess", headers["cookie"])
        self.assertIn("csrftoken=tok", headers["cookie"])
        self.assertEqual(headers["x-csrftoken"], "tok")

    def test_null_current_user_raises(self):
        http = make_http({"PreplyCliAccountIdentity": (200, {"data": {"currentUser": None}})})
        client = DirectHttpClient(sessionid="s", http_post=http)
        with self.assertRaises(PreplyDirectError):
            client.resolve_account()

    def test_graphql_errors_raise(self):
        http = make_http({
            "PreplyCliAccountIdentity": (200, IDENTITY_OK),
            "TutorWallet": (200, {"errors": [{"message": "nope"}]}),
        })
        client = DirectHttpClient(sessionid="s", http_post=http)
        with self.assertRaises(PreplyDirectError):
            client.fetch_graphql([OperationCall("wallet", get_operation("TutorWallet"), {})])

    def test_empty_sessionid_rejected(self):
        with self.assertRaises(PreplyDirectError):
            DirectHttpClient(sessionid="", http_post=lambda *a: (200, "{}"))

    def test_repr_does_not_leak_secrets(self):
        client = DirectHttpClient(sessionid="SECRET_SID", csrftoken="SECRET_CSRF",
                                  http_post=lambda *a: (200, "{}"))
        text = repr(client)
        self.assertNotIn("SECRET_SID", text)
        self.assertNotIn("SECRET_CSRF", text)

    def test_precomputed_account_skips_identity_call(self):
        http = make_http({"TutorWallet": (200, {"data": {"ok": 1}})})
        account = {"userId": "1", "name": "X", "role": "tutor", "tutorId": None,
                   "targetUrl": "direct-https"}
        client = DirectHttpClient(sessionid="s", account=account, http_post=http)
        result = client.fetch_graphql([OperationCall("wallet", get_operation("TutorWallet"), {})])
        self.assertEqual(result["_account"], account)
        # Only the wallet call was made; no identity round-trip.
        self.assertEqual(len(http.calls), 1)


if __name__ == "__main__":
    unittest.main()

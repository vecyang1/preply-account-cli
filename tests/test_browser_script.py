"""Execute the script `browser.py` generates, with a simulated CDP.

The script is a Python program that `browser-harness` runs with a `cdp()`
builtin injected. Reviewing it by reading is how the account-ambiguity bug
survived: the selection logic lives in generated source that no test touched.
Here it is compiled and run for real, so the branches are exercised rather than
eyeballed. Only `cdp` is faked; every line of the selection logic is the shipped
one.
"""
import json
import unittest

from preply_cli.browser import BrowserHarnessClient, BrowserTargetSelector


def account(user_id, name, role="learner"):
    return {"id": user_id, "firstName": name, "fullName": name,
            "tutor": {"id": 5} if role == "tutor" else None}


class FakeChrome:
    """Minimal CDP stand-in: tabs, attach, and a fetch that returns identities.

    `tabs` is a list of (url, identity-or-Exception). The identity is what the
    page's `PreplyCliAccountIdentity` fetch resolves to.
    """

    def __init__(self, tabs, data=None):
        self.tabs = tabs
        self.data = data if data is not None else {}
        self.session_of = {}

    def __call__(self, method, **kwargs):
        if method == "Target.getTargets":
            return {"targetInfos": [
                {"targetId": f"t{i}", "url": url, "type": "page", "attached": False}
                for i, (url, _identity) in enumerate(self.tabs)
            ]}
        if method == "Target.attachToTarget":
            index = int(kwargs["targetId"][1:])
            self.session_of[f"s{index}"] = index
            return {"sessionId": f"s{index}"}
        if method == "Runtime.evaluate":
            index = self.session_of[kwargs["session_id"]]
            _url, identity = self.tabs[index]
            if isinstance(identity, Exception):
                return {"result": {"value": json.dumps({"errors": [str(identity)]})}}
            if "PreplyCliAccountIdentity" in kwargs["expression"]:
                return {"result": {"value": json.dumps({"data": {"currentUser": identity}})}}
            return {"result": {"value": json.dumps(self.data)}}
        raise AssertionError(f"unexpected CDP method {method}")


def run_script(tabs, selector=None, operations=None, data=None):
    """Run the generated script and return (payload, printed_marker_lines)."""
    client = BrowserHarnessClient(selector=selector or BrowserTargetSelector())
    script = client._script(operations or [], (selector or BrowserTargetSelector()).as_payload())
    printed = []
    namespace = {
        "cdp": FakeChrome(tabs, data),
        "print": lambda text: printed.append(text),
        "__name__": "harness_script",
    }
    exec(compile(script, "<generated>", "exec"), namespace)
    marker = BrowserHarnessClient.marker
    payloads = [json.loads(line[len(marker):]) for line in printed if line.startswith(marker)]
    assert payloads, f"script emitted no CLI payload; printed={printed}"
    return payloads[-1], printed


class AmbiguousAccounts(unittest.TestCase):
    def test_two_accounts_and_no_selector_is_refused(self):
        # Previously: the tab on /home won the sort and was used silently, so
        # one account's data was shown while another was equally logged in.
        payload, _ = run_script([
            ("https://preply.com/en/home", account(111222, "First Learner")),
            ("https://preply.com/en/messages", account(555666, "Second Learner")),
        ])
        self.assertFalse(payload["ok"])
        self.assertIn("ambiguous", payload["error"])
        self.assertIn("111222", payload["error"])
        self.assertIn("555666", payload["error"])
        self.assertIn("--user-id", payload["error"])

    def test_same_account_in_several_tabs_is_not_ambiguous(self):
        payload, _ = run_script(
            [
                ("https://preply.com/en/home", account(111222, "Only Learner")),
                ("https://preply.com/en/messages", account(111222, "Only Learner")),
            ],
            data={"data": {"ok": True}},
        )
        self.assertTrue(payload["ok"], payload)

    def test_a_selector_resolves_the_ambiguity(self):
        payload, _ = run_script(
            [
                ("https://preply.com/en/home", account(111222, "First Learner")),
                ("https://preply.com/en/messages", account(555666, "Second Learner")),
            ],
            selector=BrowserTargetSelector(user_id=555666),
            data={"data": {"ok": True}},
        )
        self.assertTrue(payload["ok"], payload)

    def test_role_selector_separates_tutor_from_learner(self):
        payload, _ = run_script(
            [
                ("https://preply.com/en/home", account(111222, "A Learner", "learner")),
                ("https://preply.com/en/home", account(555666, "A Tutor", "tutor")),
            ],
            selector=BrowserTargetSelector(role="tutor"),
            data={"data": {"ok": True}},
        )
        self.assertTrue(payload["ok"], payload)


class LoggedOutTabs(unittest.TestCase):
    def test_all_tabs_unauthenticated_says_log_in(self):
        # Was reported as a selector problem, sending the user to fix a flag
        # when the actual fix is to log in.
        payload, _ = run_script([
            ("https://preply.com/en/home",
             RuntimeError("Authentication credentials were not provided.")),
        ])
        self.assertFalse(payload["ok"])
        self.assertIn("Log in to Preply", payload["error"])

    def test_no_preply_tab_at_all(self):
        payload, _ = run_script([("https://example.com/", account(1, "X"))])
        self.assertFalse(payload["ok"])
        self.assertIn("Open a logged-in Preply tab", payload["error"])

    def test_a_genuine_selector_miss_still_reports_the_selector(self):
        payload, _ = run_script(
            [("https://preply.com/en/home", account(111222, "First Learner"))],
            selector=BrowserTargetSelector(user_id=999999),
        )
        self.assertFalse(payload["ok"])
        self.assertIn("No Preply tab matched selector", payload["error"])


if __name__ == "__main__":
    unittest.main()

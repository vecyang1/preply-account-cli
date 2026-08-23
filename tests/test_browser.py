import unittest

from preply_cli.browser import BrowserTargetSelector


class BrowserTargetSelectorTests(unittest.TestCase):
    def test_selector_serializes_role_user_and_name_filters(self):
        selector = BrowserTargetSelector(role="learner", user_id=123456, name="Example Learner")

        payload = selector.as_payload()

        self.assertEqual(payload["role"], "learner")
        self.assertEqual(payload["user_id"], 123456)
        self.assertEqual(payload["name"], "Example Learner")

    def test_default_selector_prefers_any_attached_preply_account(self):
        selector = BrowserTargetSelector()

        payload = selector.as_payload()

        self.assertEqual(payload["role"], "any")
        self.assertIsNone(payload["user_id"])
        self.assertIsNone(payload["name"])

    def test_browser_script_accepts_string_or_parsed_identity_payload(self):
        from preply_cli.browser import BrowserHarnessClient

        script = BrowserHarnessClient()._script([], BrowserTargetSelector().as_payload())

        self.assertIn("json.loads(raw) if isinstance(raw, str) else raw", script)


if __name__ == "__main__":
    unittest.main()

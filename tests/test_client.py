import unittest

from preply_cli.client import PreplyClient


class FakeBrowser:
    def __init__(self):
        self.calls = []

    def fetch_graphql(self, calls):
        self.calls.append(calls)
        return {"ok": True}


class PreplyClientTests(unittest.TestCase):
    def test_next_lesson_confirmation_fetches_prompt_query(self):
        browser = FakeBrowser()
        client = PreplyClient(browser=browser)

        result = client.next_lesson_confirmation()

        self.assertEqual(result, {"ok": True})
        self.assertEqual(browser.calls[0][0].key, "confirmation")
        self.assertEqual(browser.calls[0][0].operation.name, "NextLessonForConfirmation")
        self.assertEqual(browser.calls[0][0].variables, {})

    def test_confirm_lesson_sends_confirm_past_lesson_mutation(self):
        browser = FakeBrowser()
        client = PreplyClient(browser=browser)

        result = client.confirm_lesson(161421617)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(browser.calls[0][0].key, "confirm")
        self.assertEqual(browser.calls[0][0].operation.name, "ConfirmPastLesson")
        self.assertEqual(browser.calls[0][0].variables, {"lessonId": 161421617})


if __name__ == "__main__":
    unittest.main()

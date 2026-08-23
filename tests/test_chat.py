"""Tests for chat transcript extraction and pagination.

Message bodies here are synthetic. Real conversations are private and must never
be committed as fixtures; only the payload *shape* is reproduced, which was
measured live on 2026-08-14 against a 50-message sample and an 85-message thread.

The authorship buckets encoded below are the measured ones:
authored-by-me, authored-by-collocutor, null-author-with-systemMessageType, and
null-author-with-an-action-button. Anything else must degrade to "unknown"
rather than being attributed to a person.
"""
import unittest
from unittest import mock

from preply_cli import analysis as A
from preply_cli.client import PreplyClient
from preply_cli.queries import operation_names

ME = 4200001
THEM = 4200002


def chat_payload(nodes=None, has_next=False, has_older=False):
    return {"chat": {
        "currentUser": {"id": ME, "messageThread": {"id": 1, "unreadCount": 2}},
        "chat": {
            "id": 55,
            "collocutorUser": {"id": THEM, "firstName": "Mai",
                               "profile": {"timezone": {"tzname": "Asia/Ho_Chi_Minh"}}},
            "lead": {"subject": {"translatedName": "Vietnamese"}},
            "tutoring": {"id": 5688485},
            "messages": {
                "hasNext": has_next,
                "hasOlder": has_older,
                "nodes": nodes if nodes is not None else default_nodes(),
            },
        },
    }}


def default_nodes():
    return [
        {"id": 3, "body": "see you then", "authorId": ME,
         "timePosted": "2026-08-06T06:06:05+00:00", "files": []},
        {"id": 2, "body": "lesson notes attached", "authorId": THEM,
         "timePosted": "2026-08-05T06:06:05+00:00",
         "files": [{"id": 1, "name": "notes.pdf"}]},
        {"id": 1, "body": "Your short-term goals", "authorId": None,
         "systemMessageType": "SYSTEM_MESSAGE_ABOUT_SHORT_TERM_GOALS",
         "timePosted": "2026-08-04T06:06:05+00:00", "files": []},
    ]


class SenderAttributionTest(unittest.TestCase):
    def test_all_four_measured_buckets(self):
        nodes = default_nodes() + [
            # null author carrying an action button: a platform card, not a person
            {"id": 4, "body": "Book your next lesson", "authorId": None,
             "button": {"text": "Book", "type": "PRIMARY", "url": "/x"},
             "timePosted": "2026-08-07T00:00:00+00:00", "files": []},
        ]
        rows = A.chat_rows(chat_payload(nodes))
        by_id = {r["message_id"]: r["from"] for r in rows}
        self.assertEqual(by_id[3], "me")
        self.assertEqual(by_id[2], "Mai")
        self.assertEqual(by_id[1], "system")
        self.assertEqual(by_id[4], "system")

    def test_unrecognised_author_is_never_attributed_to_a_person(self):
        """A null author with no system marker must read 'unknown', not 'me'."""
        nodes = [{"id": 9, "body": "?", "authorId": None,
                  "timePosted": "2026-08-08T00:00:00+00:00", "files": []}]
        rows = A.chat_rows(chat_payload(nodes))
        self.assertEqual(rows[0]["from"], "unknown")
        self.assertEqual(A.build_chat_summary(chat_payload(nodes))["unknown_sender"], 1)

    def test_third_party_author_is_labelled_not_guessed(self):
        nodes = [{"id": 9, "body": "hi", "authorId": 999999,
                  "timePosted": "2026-08-08T00:00:00+00:00", "files": []}]
        self.assertEqual(A.chat_rows(chat_payload(nodes))[0]["from"], "user:999999")


class ChatRowsTest(unittest.TestCase):
    def test_rows_are_oldest_first_reading_order(self):
        rows = A.chat_rows(chat_payload())
        self.assertEqual([r["message_id"] for r in rows], [1, 2, 3])

    def test_attachment_count_and_context(self):
        summary = A.build_chat_summary(chat_payload())
        self.assertEqual(summary["attachments"], 1)
        self.assertEqual(summary["collocutor"], "Mai")
        self.assertEqual(summary["subject"], "Vietnamese")
        self.assertEqual(summary["message_count"], 3)
        self.assertEqual(summary["by_sender"], {"Mai": 1, "me": 1, "system": 1})
        self.assertEqual(summary["unread"], 2)

    def test_empty_snapshot_safe(self):
        self.assertEqual(A.chat_rows({}), [])
        self.assertEqual(A.build_chat_summary({})["message_count"], 0)


class ChatPaginationTest(unittest.TestCase):
    """Guards the stale-flag bug found live: page 1 said hasOlder=True, the
    final page said False, and the summary kept reporting True on a fully
    fetched conversation."""

    def _client(self, pages):
        calls = []

        def fake_fetch(operation_calls):
            calls.append(operation_calls[0].variables)
            key = operation_calls[0].key
            return {key: pages[len(calls) - 1]}

        client = PreplyClient(browser=mock.Mock())
        client._fetch = fake_fetch  # type: ignore[method-assign]
        client.calls = calls
        return client

    def _page(self, ids, has_next, has_older):
        return {"chat": {"messages": {
            "hasNext": has_next, "hasOlder": has_older,
            "nodes": [{"id": i, "body": "x", "authorId": ME,
                       "timePosted": f"2026-08-{i:02d}T00:00:00+00:00", "files": []}
                      for i in ids],
        }}}

    def test_final_page_flags_replace_first_page_flags(self):
        client = self._client([
            self._page([50, 49], has_next=True, has_older=True),
            self._page([48, 47], has_next=False, has_older=False),
        ])
        data = client.chat_thread(THEM, limit=100)
        self.assertIs(A.chat_context(data)["has_older"], False)
        self.assertEqual(len(A.chat_rows(data)), 4)

    def test_stops_when_a_page_returns_nothing_new(self):
        """A server that keeps claiming hasNext must not spin forever."""
        client = self._client([
            self._page([3, 2], has_next=True, has_older=True),
            self._page([3, 2], has_next=True, has_older=True),  # same ids again
        ])
        data = client.chat_thread(THEM, limit=100)
        self.assertEqual(len(A.chat_rows(data)), 2)
        self.assertEqual(len(client.calls), 2)

    def test_limit_is_respected_and_reported_as_truncated(self):
        client = self._client([self._page([5, 4, 3], has_next=False, has_older=False)])
        data = client.chat_thread(THEM, limit=2)
        self.assertEqual(len(A.chat_rows(data)), 2)
        self.assertIs(A.chat_context(data)["has_older"], True)

    def test_pages_backwards_using_the_oldest_id_seen(self):
        client = self._client([
            self._page([50, 49], has_next=True, has_older=True),
            self._page([48], has_next=False, has_older=False),
        ])
        client.chat_thread(THEM, limit=100)
        self.assertIsNone(client.calls[0].get("lastId"))
        self.assertEqual(client.calls[1]["lastId"], 49)


class QueriesRegisteredTest(unittest.TestCase):
    def test_chat_operation_registered(self):
        self.assertIn("ChatAndMessages", operation_names())


if __name__ == "__main__":
    unittest.main()


class CollocutorResolutionTest(unittest.TestCase):
    """Resolving the wrong contact shows the wrong person's private messages,
    so an ambiguous match must be an error, never a silent pick."""

    THREADS = {"messages": {"currentUser": {"messageThreads": {"nodes": [
        {"collocutor": {"id": 111, "fullName": "Ana Lima"}, "unreadCount": 2},
        {"collocutor": {"id": 222, "fullName": "Ana Ruiz"}, "unreadCount": 0},
        {"collocutor": {"id": 333, "fullName": "Bo Chen"}, "unreadCount": 1},
    ]}}}}

    def _client(self):
        client = PreplyClient(browser=mock.Mock())
        client.chat_collocutors = lambda: self.THREADS  # type: ignore[method-assign]
        return client

    def test_numeric_id_is_used_directly_without_a_lookup(self):
        from preply_cli.cli.chat_cmds import _resolve_collocutor

        client = PreplyClient(browser=mock.Mock())
        client.chat_collocutors = mock.Mock(side_effect=AssertionError("no lookup"))
        self.assertEqual(_resolve_collocutor(client, "98765")[0], 98765)

    def test_unique_substring_resolves(self):
        from preply_cli.cli.chat_cmds import _resolve_collocutor

        self.assertEqual(_resolve_collocutor(self._client(), "lima")[0], 111)

    def test_ambiguous_match_raises_and_lists_candidates(self):
        from preply_cli.browser import PreplyBrowserError
        from preply_cli.cli.chat_cmds import _resolve_collocutor

        with self.assertRaises(PreplyBrowserError) as ctx:
            _resolve_collocutor(self._client(), "Ana")
        message = str(ctx.exception)
        self.assertIn("111", message)
        self.assertIn("222", message)

    def test_unknown_name_raises_and_lists_known_contacts(self):
        from preply_cli.browser import PreplyBrowserError
        from preply_cli.cli.chat_cmds import _resolve_collocutor

        with self.assertRaises(PreplyBrowserError) as ctx:
            _resolve_collocutor(self._client(), "Zoltan")
        self.assertIn("Bo Chen", str(ctx.exception))

    def test_contact_rows_sort_unread_first(self):
        from preply_cli.cli.chat_cmds import _contact_rows

        rows = _contact_rows(self._client())
        self.assertEqual([r["user_id"] for r in rows], [111, 333, 222])


class ButtonAttributionObservabilityTest(unittest.TestCase):
    """The rule "null author + action button => system" is an inference from a
    single conversation. Counting it keeps the assumption falsifiable."""

    def test_button_attributed_messages_are_counted(self):
        nodes = [
            {"id": 1, "body": "Book a lesson", "authorId": None,
             "button": {"text": "Book"}, "timePosted": "2026-08-01T00:00:00+00:00",
             "files": []},
            {"id": 2, "body": "hi", "authorId": THEM,
             "timePosted": "2026-08-02T00:00:00+00:00", "files": []},
            {"id": 3, "body": "goal set", "authorId": None,
             "systemMessageType": "SYSTEM_MESSAGE_ABOUT_SHORT_TERM_GOALS",
             "timePosted": "2026-08-03T00:00:00+00:00", "files": []},
        ]
        summary = A.build_chat_summary(chat_payload(nodes))
        self.assertEqual(summary["system_by_button"], 1)
        self.assertEqual(summary["by_sender"]["system"], 2)

    def test_a_real_author_with_a_button_is_still_the_person(self):
        """authorId must win over the button heuristic."""
        nodes = [{"id": 1, "body": "here", "authorId": THEM,
                  "button": {"text": "Open"},
                  "timePosted": "2026-08-01T00:00:00+00:00", "files": []}]
        self.assertEqual(A.chat_rows(chat_payload(nodes))[0]["from"], "Mai")
        self.assertEqual(A.build_chat_summary(chat_payload(nodes))["system_by_button"], 0)


class AttachmentExposureTest(unittest.TestCase):
    """Attachments are the part of a thread worth revisiting, so they must be
    enumerable with usable URLs - not just counted."""

    def _payload(self, files):
        return chat_payload([
            {"id": 1, "body": "materials", "authorId": THEM,
             "timePosted": "2026-08-01T10:00:00+00:00", "files": files},
        ])

    def test_root_relative_download_url_is_made_absolute(self):
        """Measured live: downloadUrl is '/files/<id>?download=true'."""
        rows = A.chat_file_rows(self._payload([
            {"id": 7, "name": "lesson.pdf", "mimeType": "application/pdf",
             "size": 1234, "downloadUrl": "/files/7?download=true"},
        ]))
        self.assertEqual(rows[0]["url"], "https://preply.com/files/7?download=true")
        self.assertEqual(rows[0]["name"], "lesson.pdf")
        self.assertEqual(rows[0]["from"], "Mai")

    def test_protocol_relative_url_is_made_absolute(self):
        rows = A.chat_file_rows(self._payload([
            {"id": 8, "name": "a.jpg", "url": "//cdn.preply.com/a.jpg"},
        ]))
        self.assertEqual(rows[0]["url"], "https://cdn.preply.com/a.jpg")

    def test_absolute_url_is_left_alone(self):
        rows = A.chat_file_rows(self._payload([
            {"id": 9, "name": "b.pdf", "downloadUrl": "https://x.test/b.pdf"},
        ]))
        self.assertEqual(rows[0]["url"], "https://x.test/b.pdf")

    def test_null_file_entries_do_not_crash(self):
        rows = A.chat_file_rows(self._payload([None, {"id": 1, "name": "ok.pdf"}]))
        self.assertEqual([r["name"] for r in rows], ["ok.pdf"])

    def test_message_rows_expose_names_and_count(self):
        rows = A.chat_rows(self._payload([
            {"id": 1, "name": "one.pdf"}, {"id": 2, "name": "two.mp3"},
        ]))
        self.assertEqual(rows[0]["attachments"], 2)
        self.assertEqual(rows[0]["file_names"], "one.pdf, two.mp3")

    def test_thread_with_no_attachments_yields_no_file_rows(self):
        text_only = chat_payload([
            {"id": 1, "body": "no files here", "authorId": THEM,
             "timePosted": "2026-08-01T10:00:00+00:00", "files": []},
        ])
        self.assertEqual(A.chat_file_rows(text_only), [])

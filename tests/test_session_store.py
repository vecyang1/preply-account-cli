import json
import unittest
from unittest import mock

from preply_cli import session_store as S
from preply_cli.session_store import SessionMeta, SessionStoreError


class SessionMetaMatchTest(unittest.TestCase):
    def _meta(self, **kw):
        base = dict(item_id="i", title="t", account_id="100", role="tutor", name="Ada")
        base.update(kw)
        return SessionMeta(**base)

    def test_role_any_matches_all(self):
        self.assertTrue(self._meta().matches("any", None, None))

    def test_role_mismatch(self):
        self.assertFalse(self._meta(role="learner").matches("tutor", None, None))

    def test_user_id_match(self):
        self.assertTrue(self._meta(account_id="100").matches("any", 100, None))
        self.assertFalse(self._meta(account_id="100").matches("any", 999, None))

    def test_name_substring_case_insensitive(self):
        self.assertTrue(self._meta(name="Ada Lovelace").matches("any", None, "lovel"))
        self.assertFalse(self._meta(name="Ada").matches("any", None, "bob"))


class TitleAndTagParsingTest(unittest.TestCase):
    def test_parse_name_from_title(self):
        self.assertEqual(
            S._parse_name_from_title("Preply Session · Rivera · learner · 4200001"),
            "Rivera",
        )

    def test_parse_name_from_bad_title(self):
        self.assertIsNone(S._parse_name_from_title("Random note"))

    def test_tag_value(self):
        tags = ["preply-session", "preply-role:tutor", "preply-account:55"]
        self.assertEqual(S._tag_value(tags, S.ROLE_TAG_PREFIX), "tutor")
        self.assertEqual(S._tag_value(tags, S.ACCOUNT_TAG_PREFIX), "55")
        self.assertIsNone(S._tag_value(tags, "missing:"))


class ListAndSelectTest(unittest.TestCase):
    ITEMS = [
        {"id": "a", "title": "Preply Session · Ada · tutor · 1",
         "tags": ["preply-session", "preply-role:tutor", "preply-account:1"]},
        {"id": "b", "title": "Preply Session · Bo · learner · 2",
         "tags": ["preply-session", "preply-role:learner", "preply-account:2"]},
    ]

    def test_list_sessions_parses_tags(self):
        with mock.patch.object(S, "_op", return_value=json.dumps(self.ITEMS)):
            sessions = S.list_sessions()
        self.assertEqual({s.account_id for s in sessions}, {"1", "2"})
        ada = next(s for s in sessions if s.account_id == "1")
        self.assertEqual(ada.role, "tutor")
        self.assertEqual(ada.name, "Ada")

    def test_select_session_unique(self):
        with mock.patch.object(S, "_op", return_value=json.dumps(self.ITEMS)):
            meta = S.select_session("learner", None, None)
        self.assertEqual(meta.account_id, "2")

    def test_select_session_none_raises(self):
        with mock.patch.object(S, "_op", return_value=json.dumps(self.ITEMS)):
            with self.assertRaises(SessionStoreError):
                S.select_session("tutor", 999, None)

    def test_select_session_ambiguous_raises(self):
        items = [
            {"id": "a", "title": "Preply Session · Ada · tutor · 1",
             "tags": ["preply-session", "preply-role:tutor", "preply-account:1"]},
            {"id": "b", "title": "Preply Session · Bo · tutor · 2",
             "tags": ["preply-session", "preply-role:tutor", "preply-account:2"]},
        ]
        with mock.patch.object(S, "_op", return_value=json.dumps(items)):
            with self.assertRaises(SessionStoreError):
                S.select_session("tutor", None, None)

    def test_resolve_session_reads_credential(self):
        item_get = json.dumps({"id": "a", "fields": [
            {"id": "credential", "label": "credential", "value": "SECRET_SESSION"},
            {"id": "csrftoken", "label": "csrftoken", "value": "CSRF"},
        ]})

        def fake_op(args, **kw):
            if args[:2] == ["item", "list"]:
                return json.dumps(self.ITEMS)
            if args[:2] == ["item", "get"]:
                return item_get
            raise AssertionError(f"unexpected op {args}")

        with mock.patch.object(S, "_op", side_effect=fake_op):
            meta, sessionid, csrftoken = S.resolve_session("tutor", None, None)
        self.assertEqual(meta.account_id, "1")
        self.assertEqual(sessionid, "SECRET_SESSION")
        self.assertEqual(csrftoken, "CSRF")

    def test_read_item_secrets_single_call(self):
        item_get = json.dumps({"id": "a", "fields": [
            {"id": "credential", "label": "credential", "value": "S"},
            {"id": "csrftoken", "label": "csrftoken", "value": "C"},
            {"id": "account_id", "label": "preply_account_id", "value": "1"},
        ]})
        with mock.patch.object(S, "_op", return_value=item_get) as m:
            secrets = S.read_item_secrets("a")
        self.assertEqual(secrets["credential"], "S")
        self.assertEqual(secrets["csrftoken"], "C")
        self.assertEqual(m.call_count, 1)  # one bridge round-trip


class BuildTemplateTest(unittest.TestCase):
    def test_template_shape_no_epoch_dates(self):
        tpl = S._build_item_template(
            account_id="7", account_name="Bo", role="learner",
            sessionid="sid", csrftoken="csrf", source_profile="Profile 2",
            sessionid_expiry="2027-07-18T07:17:34+00:00",
        )
        self.assertEqual(tpl["category"], "API_CREDENTIAL")
        self.assertIn("preply-session", tpl["tags"])
        self.assertIn("preply-role:learner", tpl["tags"])
        self.assertIn("preply-account:7", tpl["tags"])
        cred = next(f for f in tpl["fields"] if f["id"] == "credential")
        self.assertEqual(cred["type"], "CONCEALED")
        self.assertEqual(cred["value"], "sid")
        # No DATE-typed fields (avoids the epoch-1970 trap).
        self.assertTrue(all(f["type"] in ("CONCEALED", "STRING") for f in tpl["fields"]))


if __name__ == "__main__":
    unittest.main()

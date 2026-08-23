"""Failure paths a real user hits, and what they are told when they do.

Every case here was reproduced against the shipped CLI before it was fixed. The
theme is the repo's standing rule applied to *messages* rather than to numbers:
a failure to look is not evidence for the negative answer, and an error that
names the wrong cause is worse than one that admits it does not know.
"""
import argparse
import io
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from urllib.error import HTTPError, URLError

from preply_cli import capture, cli
from preply_cli.browser import BrowserHarnessClient, PreplyBrowserError
from preply_cli.direct import PreplyDirectError, PreplySessionExpired, _tls_client_note
from preply_cli.public_profile import PublicProfileError, fetch_tutor_profile
from preply_cli.session_store import SessionMeta, SessionStoreError


class LoadSnapshot(unittest.TestCase):
    """`-f` used to answer every malformed input with zeros or a traceback."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_missing_file_is_a_cli_error_not_a_traceback(self):
        with self.assertRaises(cli.SnapshotError) as caught:
            cli._load_snapshot(self.tmp / "nope.json")
        self.assertIn("cannot read snapshot", str(caught.exception))

    def test_directory_is_a_cli_error(self):
        with self.assertRaises(cli.SnapshotError):
            cli._load_snapshot(self.tmp)

    def test_invalid_json_names_the_position(self):
        path = self.write("bad.json", "{oops}")
        with self.assertRaises(cli.SnapshotError) as caught:
            cli._load_snapshot(path)
        self.assertIn("not valid JSON", str(caught.exception))

    def test_json_array_is_refused(self):
        path = self.write("arr.json", "[]")
        with self.assertRaises(cli.SnapshotError) as caught:
            cli._load_snapshot(path)
        self.assertIn("not a snapshot object", str(caught.exception))

    def test_wellformed_json_that_is_not_a_snapshot_is_refused(self):
        # THE case: this used to render `spent_total 0.0` at exit 0.
        path = self.write("other.json", json.dumps({"hello": "world", "z": 1}))
        with self.assertRaises(cli.SnapshotError) as caught:
            cli._load_snapshot(path)
        message = str(caught.exception)
        self.assertIn("not a Preply snapshot", message)
        # It must show what it *did* find, or the user cannot tell which file
        # they passed by mistake.
        self.assertIn("hello", message)

    def test_a_real_snapshot_still_loads(self):
        # The guard has to stay quiet on healthy input, or it is just a new
        # failure mode. Both marker styles are accepted: current snapshots carry
        # `_account`, v0.6-era ones only `account`.
        for payload in ({"_account": {"role": "learner"}}, {"account": {"currentUser": {}}}):
            path = self.write("snap.json", json.dumps(payload))
            self.assertEqual(payload, cli._load_snapshot(path))


class CountArgument(unittest.TestCase):
    def test_zero_and_negative_are_rejected(self):
        for bad in ("0", "-1", "-100"):
            with self.assertRaises(argparse.ArgumentTypeError):
                cli._count(bad)

    def test_non_integer_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cli._count("ten")

    def test_positive_passes_through(self):
        self.assertEqual(50, cli._count("50"))


class ConfirmationGateOrdering(unittest.TestCase):
    """`--confirm` without `--yes` must cost nothing.

    Asserted with a trap rather than a stub return value: a stub that hands back
    a client would let the wrong order keep passing, since the refusal happens
    either way. Only an exploding `_client` can observe that it was called.
    """

    def test_refusal_happens_before_any_client_is_built(self):
        args = argparse.Namespace(
            confirm=True, yes=False, json=False, csv=False,
            role="any", user_id=None, name=None, transport="auto",
            lesson_id=None, expect_tutor=None, expect_datetime=None,
        )
        with mock.patch.object(
            cli, "_client", side_effect=AssertionError("no client may be built")
        ):
            with self.assertRaises(PreplyBrowserError) as caught:
                cli.cmd_confirmation(args)
        self.assertIn("--yes", str(caught.exception))


class SessionStatusVerdicts(unittest.TestCase):
    """`live` is three-valued: live / stale / unknown."""

    def _run(self, resolve_error=None, probe_error=None):
        meta = SessionMeta(item_id="i", title="t", account_id="1", role="learner", name="N")
        resolve = (
            mock.patch.object(capture, "resolve_session", side_effect=resolve_error)
            if resolve_error
            else mock.patch.object(capture, "resolve_session", return_value=(meta, "s", "c"))
        )
        client = mock.Mock()
        client.resolve_account.side_effect = probe_error
        if probe_error is None:
            client.resolve_account.side_effect = None
            client.resolve_account.return_value = {"name": "N"}
        with mock.patch.object(capture, "list_sessions", return_value=[meta]), resolve, \
                mock.patch.object(capture, "DirectHttpClient", return_value=client):
            return capture.session_status()[0]

    def test_preply_rejecting_the_session_is_stale(self):
        row = self._run(probe_error=PreplySessionExpired("currentUser is null"))
        self.assertEqual("stale", row["live"])

    def test_never_reaching_preply_is_unknown_not_stale(self):
        # A TLS failure, a 500, or a Cloudflare challenge tested nothing about
        # the session. Calling it `stale` sends the user to `session capture`,
        # which needs them physically present for a Keychain prompt.
        row = self._run(probe_error=PreplyDirectError("transport error: SSLError"))
        self.assertEqual("unknown", row["live"])
        self.assertIn("could not reach Preply", row["detail"])

    def test_a_1password_failure_is_unknown_not_stale(self):
        row = self._run(resolve_error=SessionStoreError("op item get failed: rate-limited"))
        self.assertEqual("unknown", row["live"])
        self.assertIn("could not read the stored credential", row["detail"])

    def test_a_working_session_is_live(self):
        self.assertEqual("live", self._run()["live"])


class BrowserTransportErrors(unittest.TestCase):
    def test_timeout_becomes_a_cli_error(self):
        with mock.patch("preply_cli.browser.harness_available", return_value=True), \
             mock.patch("preply_cli.browser.subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="browser-harness", timeout=90)):
            with self.assertRaises(PreplyBrowserError) as caught:
                BrowserHarnessClient().fetch_graphql([])
        self.assertIn("did not respond within 90s", str(caught.exception))

    def test_fallback_note_is_appended_when_auto_chose_this_route(self):
        # The residual half of the transport bug: with browser-harness present,
        # the direct-side reason was still discarded.
        client = BrowserHarnessClient(fallback_note="1Password bridge is down")
        with mock.patch("preply_cli.browser.harness_available", return_value=False):
            with self.assertRaises(PreplyBrowserError) as caught:
                client.fetch_graphql([])
        message = str(caught.exception)
        self.assertIn("is not on PATH", message)
        self.assertIn("1Password bridge is down", message)

    def test_no_note_when_the_browser_route_was_chosen_outright(self):
        with mock.patch("preply_cli.browser.harness_available", return_value=False):
            with self.assertRaises(PreplyBrowserError) as caught:
                BrowserHarnessClient().fetch_graphql([])
        self.assertNotIn("direct transport was skipped", str(caught.exception))


class PublicProfileErrors(unittest.TestCase):
    def _fail_with(self, error):
        if isinstance(error, HTTPError):
            # Give it a real fp and close it here; an HTTPError left without one
            # is cleaned up by tempfile at GC time and emits a ResourceWarning
            # into the test output.
            self.addCleanup(error.close)
        return mock.patch("preply_cli.public_profile.urlopen", side_effect=error)

    def _http_error(self, code, reason):
        return HTTPError("u", code, reason, {}, io.BytesIO(b""))

    def test_404_names_the_tutor_id_as_the_suspect(self):
        with self._fail_with(self._http_error(404, "Not Found")):
            with self.assertRaises(PublicProfileError) as caught:
                fetch_tutor_profile("999999999")
        self.assertIn("404", str(caught.exception))

    def test_403_is_named_as_bot_protection_not_a_bad_id(self):
        with self._fail_with(self._http_error(403, "Forbidden")):
            with self.assertRaises(PublicProfileError) as caught:
                fetch_tutor_profile("2807691")
        self.assertIn("bot protection", str(caught.exception))

    def test_unreachable_host_is_a_cli_error(self):
        with self._fail_with(URLError("Connection refused")):
            with self.assertRaises(PublicProfileError):
                fetch_tutor_profile("2807691")

    def test_user_agent_tracks_the_package_version(self):
        from preply_cli import __version__

        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["ua"] = request.get_header("User-agent")
            raise URLError("stop here")

        with mock.patch("preply_cli.public_profile.urlopen", fake_urlopen):
            with self.assertRaises(PublicProfileError):
                fetch_tutor_profile("2807691")
        self.assertIn(__version__, captured["ua"])


class TlsClientNote(unittest.TestCase):
    def test_note_appears_only_when_curl_cffi_is_missing(self):
        with mock.patch("preply_cli.direct.curl_cffi_available", return_value=False):
            self.assertIn("curl_cffi", _tls_client_note())
        with mock.patch("preply_cli.direct.curl_cffi_available", return_value=True):
            self.assertEqual("", _tls_client_note())


if __name__ == "__main__":
    unittest.main()

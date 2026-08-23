"""Which transport `auto` picks, and what it says when it cannot pick one.

The regression these cover: under the default ``--transport auto`` the reason
the direct route was unavailable used to be swallowed, so a first-time user with
nothing configured was told only ``browser-harness is not on PATH``. That names
one route's dependency as though it were the entire problem, and points away
from `preply session capture`, which is the documented setup path.
"""
import argparse
import unittest
from unittest import mock

from preply_cli.cli import _shared as cli
from preply_cli.browser import PreplyBrowserError
from preply_cli.session_store import SessionStoreError


def args(transport="auto", role="any", user_id=None, name=None):
    return argparse.Namespace(
        transport=transport, role=role, user_id=user_id, name=name
    )


def no_session(message="No stored Preply session matches the selector."):
    return mock.patch(
        "preply_cli.session_store.resolve_session",
        side_effect=SessionStoreError(message),
    )


def a_session():
    return mock.patch(
        "preply_cli.session_store.resolve_session",
        return_value=(mock.Mock(), "sessionid-value", "csrf-value"),
    )


def harness(present):
    # Patch where it is looked up. `preply_cli.cli` re-exports the name, but
    # `_client` resolves it in `_shared`'s own globals, so patching the
    # re-export would leave the real function running -- a test that passes
    # while testing nothing.
    return mock.patch("preply_cli.cli._shared.harness_available", return_value=present)


class TransportChoice(unittest.TestCase):
    def test_auto_with_neither_route_names_both_routes(self):
        with no_session(), harness(False):
            with self.assertRaises(PreplyBrowserError) as caught:
                cli._client(args())
        message = str(caught.exception)
        self.assertIn("direct", message)
        self.assertIn("browser", message)
        # The actionable next step for the unattended route.
        self.assertIn("preply session capture", message)

    def test_auto_reports_why_direct_was_skipped(self):
        # The whole point: the direct-side reason must survive the fallback.
        with no_session("Selector is ambiguous across 2 sessions"), harness(False):
            with self.assertRaises(PreplyBrowserError) as caught:
                cli._client(args())
        self.assertIn("Selector is ambiguous across 2 sessions", str(caught.exception))

    def test_auto_falls_back_to_browser_when_the_harness_exists(self):
        # A missing stored session is not fatal under `auto` -- the browser
        # route may still work, and building the client must not raise.
        with no_session(), harness(True):
            client = cli._client(args())
        self.assertIsNotNone(client)

    def test_auto_prefers_direct_when_a_session_resolves(self):
        # harness_available must not even be consulted: if it were, a machine
        # with a stored session but no harness could still take the browser path.
        with a_session(), harness(False) as which:
            client = cli._client(args())
        self.assertIsNotNone(client)
        which.assert_not_called()

    def test_explicit_direct_raises_the_store_error_unchanged(self):
        # Naming a transport means asking for that transport's own diagnosis;
        # the combined two-route message would bury it.
        with no_session("bridge is down"), harness(False):
            with self.assertRaises(SessionStoreError) as caught:
                cli._client(args(transport="direct"))
        self.assertEqual("bridge is down", str(caught.exception))
        self.assertNotIn("neither transport", str(caught.exception))

    def test_explicit_browser_does_not_consult_the_session_store(self):
        # Asking for the browser route must not trigger a 1Password unlock.
        with mock.patch(
            "preply_cli.session_store.resolve_session",
            side_effect=AssertionError("the session store must not be touched"),
        ), harness(False):
            client = cli._client(args(transport="browser"))
        self.assertIsNotNone(client)


class HarnessMissingMessage(unittest.TestCase):
    def test_single_route_message_still_names_the_command(self):
        from preply_cli.browser import HARNESS_COMMAND, BrowserHarnessClient

        with mock.patch("preply_cli.browser.harness_available", return_value=False):
            with self.assertRaises(PreplyBrowserError) as caught:
                BrowserHarnessClient().fetch_graphql([])
        self.assertIn(HARNESS_COMMAND, str(caught.exception))


if __name__ == "__main__":
    unittest.main()

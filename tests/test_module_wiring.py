"""Names that resolve at import time but blow up when a command actually runs.

Splitting `cli.py` and `analysis.py` into packages moved function bodies away
from the imports they relied on. Python does not notice: a module-level name is
looked up when the line executes, so `cmd_history` imported fine and raised
`NameError: build_payment_summary` only against a live account. The 207 tests
passing at that moment is the point -- unit tests exercise extractors, not every
command's module globals.

`main()`'s own `except` clause had the same hole: it referenced
`PublicProfileError`, which the new header did not import, so *any* error in
*any* command would have surfaced as a NameError instead of a clean message.
That one is only reachable when something fails, which is exactly when a
traceback is least useful.

These two tests are cheap and catch the whole class.
"""
import ast
import builtins
import pathlib
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
PACKAGE = SRC / "preply_cli"

# The project's own standard (see the coding-style rules): files stay focused.
MAX_LINES = 800


def undefined_globals(path: pathlib.Path) -> list[str]:
    """Names a module reads without ever binding them.

    Deliberately simple and slightly over-strict on comprehension scopes; if it
    ever produces a false positive, add the import rather than loosening it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound: set[str] = set()
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, ast.Store) else used).add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Global):
            bound.update(node.names)
    return sorted(used - bound - set(dir(builtins)))


class NoUndefinedNames(unittest.TestCase):
    def test_no_module_reads_a_name_it_never_binds(self):
        offenders = {
            str(path.relative_to(SRC)): missing
            for path in sorted(PACKAGE.rglob("*.py"))
            if (missing := undefined_globals(path))
        }
        self.assertEqual({}, offenders)


class FileSize(unittest.TestCase):
    def test_no_module_exceeds_the_project_line_limit(self):
        oversized = {
            str(path.relative_to(SRC)): len(path.read_text(encoding="utf-8").splitlines())
            for path in sorted(PACKAGE.rglob("*.py"))
            if len(path.read_text(encoding="utf-8").splitlines()) > MAX_LINES
        }
        self.assertEqual({}, oversized)


class CommandsAreWired(unittest.TestCase):
    def test_every_subcommand_resolves_to_a_callable(self):
        from preply_cli.cli import build_parser

        parser = build_parser()
        actions = [a for a in parser._actions if getattr(a, "choices", None)
                   and hasattr(a, "_name_parser_map")]
        self.assertTrue(actions, "no subparser action found")
        names = sorted(actions[0]._name_parser_map)
        self.assertGreaterEqual(len(names), 20)
        for name in names:
            sub = actions[0]._name_parser_map[name]
            func = sub.get_default("func")
            self.assertTrue(callable(func), f"{name} has no callable func")


class MainMapsErrorsToExitTwo(unittest.TestCase):
    """Exercise main()'s except clause for every type it claims to handle."""

    def _errors(self):
        from preply_cli.browser import PreplyBrowserError
        from preply_cli.chrome_cookies import ChromeCookieError
        from preply_cli.cli import SnapshotError
        from preply_cli.direct import PreplyDirectError, PreplySessionExpired
        from preply_cli.public_profile import PublicProfileError
        from preply_cli.session_store import SessionStoreError

        return [
            PreplyBrowserError("browser"),
            PublicProfileError("profile"),
            PreplyDirectError("direct"),
            PreplySessionExpired("expired"),
            SessionStoreError("store"),
            ChromeCookieError("cookies"),
            SnapshotError("snapshot"),
        ]

    # Patch the transport, not the command. `build_parser` binds each `func` as
    # a parser default when the parser is built, so patching
    # `learner_cmds.cmd_stats` leaves the already-bound original in place -- the
    # first draft of this test silently ran the real command against the real
    # account. `_client` is resolved inside the command body at call time, so
    # patching it there both works and guarantees no network is touched.
    TRANSPORT = "preply_cli.cli.learner_cmds._client"

    def test_each_handled_error_exits_two(self):
        from preply_cli.cli import main

        for error in self._errors():
            with self.subTest(error=type(error).__name__):
                with mock.patch(self.TRANSPORT, side_effect=error), \
                     mock.patch("sys.stderr"):
                    with self.assertRaises(SystemExit) as caught:
                        main(["stats"])
                self.assertEqual(2, caught.exception.code, type(error).__name__)

    def test_keyboard_interrupt_exits_130(self):
        from preply_cli.cli import main

        with mock.patch(self.TRANSPORT, side_effect=KeyboardInterrupt), \
             mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as caught:
                main(["stats"])
        self.assertEqual(130, caught.exception.code)

    def test_the_transport_patch_actually_intercepts(self):
        # If `_client` were ever resolved somewhere else, the tests above would
        # quietly start exercising the network again and still pass. This makes
        # that regression loud: reaching the real transport is an error here.
        from preply_cli.cli import main

        with mock.patch(self.TRANSPORT) as client, mock.patch("sys.stderr"), \
             mock.patch("sys.stdout"):
            try:
                main(["stats"])
            except SystemExit:
                pass
        client.assert_called_once()


if __name__ == "__main__":
    unittest.main()

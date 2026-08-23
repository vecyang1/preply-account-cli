"""Guard against source characters that are invisible in an editor.

Written after a U+200B ZERO WIDTH SPACE was introduced at the start of a comment
line in analysis.py. The file looked correct in every editor and diff view, and
failed only at import with `SyntaxError: invalid non-printable character`.

This is the "literal that lies about itself" failure mode: reading the line
cannot confirm the behaviour. It is silent, it recurs whenever source is
generated rather than typed, and it is exactly decidable - so it earns a test
rather than a note in prose.

Scope is deliberately narrow: only characters that are *invisible yet
significant*. Legitimate non-ASCII (accented tutor names, CJK, the middle dot in
item titles) must keep working, so this does not ban non-ASCII.

Every banned character is declared by **code point**, never as a literal.
Spelling them literally would plant the very bytes this module rejects - the
first draft did that and this test caught itself.
"""
import unicodedata
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# code point -> why it is banned
INVISIBLE_CODEPOINTS = {
    0x200B: "ZERO WIDTH SPACE",
    0x200C: "ZERO WIDTH NON-JOINER",
    0x200D: "ZERO WIDTH JOINER",
    0x2060: "WORD JOINER",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE / BOM",
    0x00A0: "NO-BREAK SPACE",
}


def python_sources():
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if any(part in {".venv", "__pycache__", ".git"} for part in path.parts):
            continue
        yield path


def scan(text: str, predicate) -> list[tuple[int, int, int]]:
    """Return (line, column, codepoint) for every character matching predicate."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for col, char in enumerate(line):
            if predicate(ord(char)):
                hits.append((lineno, col, ord(char)))
    return hits


class InvisibleCharacterTest(unittest.TestCase):
    def test_no_invisible_characters_in_python_sources(self):
        offences = []
        for path in python_sources():
            for lineno, col, code in scan(
                path.read_text(encoding="utf-8"), lambda c: c in INVISIBLE_CODEPOINTS
            ):
                offences.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{lineno}:{col} "
                    f"U+{code:04X} {INVISIBLE_CODEPOINTS[code]}"
                )
        self.assertEqual(
            offences, [], "Invisible characters found in source:\n" + "\n".join(offences)
        )

    def test_no_unexpected_control_characters(self):
        """Raw control bytes make grep treat a file as binary and stop matching."""
        offences = []
        for path in python_sources():
            for lineno, col, code in scan(
                path.read_text(encoding="utf-8"), lambda c: c < 0x20 and c != 0x09
            ):
                offences.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{lineno}:{col} "
                    f"U+{code:04X} {unicodedata.name(chr(code), 'control')}"
                )
        self.assertEqual(
            offences, [], "Control characters found in source:\n" + "\n".join(offences)
        )

    def test_all_sources_are_valid_utf8(self):
        for path in python_sources():
            try:
                path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:  # pragma: no cover - guard
                self.fail(f"{path.relative_to(PROJECT_ROOT)} is not valid UTF-8: {exc}")

    def test_scanner_actually_detects_a_planted_character(self):
        """A check nobody has seen fail is not evidence. Prove it can fail."""
        planted = "x = 1  # trailing" + chr(0x200B) + "zero width"
        hits = scan(planted, lambda c: c in INVISIBLE_CODEPOINTS)
        self.assertEqual([(1, 17, 0x200B)], hits)

    def test_scanner_does_not_reject_legitimate_non_ascii(self):
        """Accented and CJK text must keep working; only invisibles are banned.

        Uses placeholder names, not real ones: this repository is public.
        """
        legitimate = 'name = "Nguyen"  # Hàng, José, 中文, bullet ·'
        self.assertEqual([], scan(legitimate, lambda c: c in INVISIBLE_CODEPOINTS))

    def test_it_scans_a_nonzero_number_of_files(self):
        """A green run over zero files is inconclusive, not passing."""
        self.assertGreater(len(list(python_sources())), 10)


if __name__ == "__main__":
    unittest.main()

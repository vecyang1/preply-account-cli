import unittest

from preply_cli.formatting import format_table, redact_email


class FormattingTests(unittest.TestCase):
    def test_format_table_keeps_columns_readable(self):
        rows = [
            {"student": "Example Student", "status": "ACTIVE_SUBSCRIPTION", "lessons": 11},
            {"student": "Past Student", "status": "CANCELED_SUBSCRIPTION", "lessons": 7},
        ]

        rendered = format_table(rows, ["student", "status", "lessons"])

        self.assertIn("student", rendered.splitlines()[0])
        self.assertIn("ACTIVE_SUBSCRIPTION", rendered)
        self.assertIn("CANCELED_SUBSCRIPTION", rendered)

    def test_redact_email_preserves_debuggable_shape(self):
        self.assertEqual(redact_email("learner@example.com"), "l***@example.com")
        self.assertEqual(redact_email(None), None)


if __name__ == "__main__":
    unittest.main()

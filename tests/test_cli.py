import unittest

from preply_cli.cli import _confirmation_rows, build_parser


class CliParserTests(unittest.TestCase):
    def test_tutor_reviews_defaults_to_all_reviews(self):
        parser = build_parser()

        args = parser.parse_args(["tutor-reviews", "2807691"])

        self.assertIsNone(args.limit)

    def test_tutor_reviews_command_accepts_url_limit_and_output_flags(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "tutor-reviews",
                "https://preply.com/en/tutor/2807691",
                "--limit",
                "3",
                "--json",
            ]
        )

        self.assertEqual(args.command, "tutor-reviews")
        self.assertEqual(args.source, "https://preply.com/en/tutor/2807691")
        self.assertEqual(args.limit, 3)
        self.assertTrue(args.json)

    def test_confirmation_command_defaults_to_status_mode(self):
        parser = build_parser()

        args = parser.parse_args(["--role", "learner", "confirmation", "--json"])

        self.assertEqual(args.command, "confirmation")
        self.assertFalse(args.confirm)
        self.assertFalse(args.yes)
        self.assertTrue(args.json)

    def test_confirmation_command_requires_explicit_action_flags(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "--role",
                "learner",
                "confirmation",
                "--confirm",
                "--yes",
                "--lesson-id",
                "161421617",
                "--expect-tutor",
                "Andres",
            ]
        )

        self.assertTrue(args.confirm)
        self.assertTrue(args.yes)
        self.assertEqual(args.lesson_id, 161421617)
        self.assertEqual(args.expect_tutor, "Andres")

    def test_confirmation_rows_extract_prompt_lesson(self):
        data = {
            "confirmation": {
                "myNextLessonForConfirmation": {
                    "id": 161421617,
                    "datetime": "2026-06-15T21:00:00+07:00",
                    "status": "SCHEDULED_PAST",
                    "isFirstLesson": False,
                    "tutor": {"id": 2807691, "user": {"firstName": "Andres"}},
                    "tutoring": {
                        "id": 9909441,
                        "lead": {"subject": {"alias": "music"}},
                    },
                }
            }
        }

        rows = _confirmation_rows(data)

        self.assertEqual(
            rows,
            [
                {
                    "lesson_id": 161421617,
                    "datetime": "2026-06-15T21:00:00+07:00",
                    "tutor": "Andres",
                    "status": "SCHEDULED_PAST",
                    "first_lesson": False,
                    "tutoring_id": 9909441,
                    "subject": "music",
                    "report_url": "/en/lessons/report/161421617?src=confirmation_modal",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()


class NewCommandParserTests(unittest.TestCase):
    """Parser coverage for the commands added in 0.7.0/0.8.x."""

    def test_balance_accepts_file_and_output_flags(self):
        args = build_parser().parse_args(["balance", "-f", "snap.json", "--csv"])
        self.assertEqual(args.command, "balance")
        self.assertEqual(args.file, "snap.json")
        self.assertTrue(args.csv)

    def test_me_defaults_and_supports_csv(self):
        args = build_parser().parse_args(["me"])
        self.assertEqual(args.recent, 5)
        self.assertFalse(args.csv)
        self.assertTrue(build_parser().parse_args(["me", "--csv"]).csv)

    def test_chat_target_is_optional_so_it_can_list_contacts(self):
        args = build_parser().parse_args(["chat"])
        self.assertEqual(args.command, "chat")
        self.assertEqual(args.who, "")
        self.assertEqual(args.limit, 50)
        self.assertFalse(args.full)

    def test_chat_accepts_a_target_and_full_text(self):
        args = build_parser().parse_args(["chat", "Ada", "--limit", "200", "--full"])
        self.assertEqual(args.who, "Ada")
        self.assertEqual(args.limit, 200)
        self.assertTrue(args.full)

    def test_global_selectors_precede_the_subcommand(self):
        args = build_parser().parse_args(
            ["--role", "learner", "--transport", "direct", "balance"]
        )
        self.assertEqual(args.role, "learner")
        self.assertEqual(args.transport, "direct")
        self.assertEqual(args.command, "balance")


class WarningChannelTests(unittest.TestCase):
    """Warnings must reach stderr and must not pollute the summary table."""

    def test_summary_rows_drop_the_warnings_key(self):
        from preply_cli.cli._shared import _summary_rows

        rows = _summary_rows({"lesson_count": 3, "warnings": ["something drifted"]})
        self.assertEqual([r["metric"] for r in rows], ["lesson_count"])

    def test_warnings_go_to_stderr_from_both_summary_and_payload(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from preply_cli.cli import _print_data_warnings

        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            _print_data_warnings({"warnings": ["a"]}, {"_warnings": ["b", "a"]})
        self.assertIn("a", err.getvalue())
        self.assertIn("b", err.getvalue())
        self.assertEqual(err.getvalue().count("warning:"), 2, "duplicates collapse")
        self.assertEqual(out.getvalue(), "", "stdout stays clean for pipes")

    def test_healthy_summary_prints_nothing(self):
        import io
        from contextlib import redirect_stderr

        from preply_cli.cli import _print_data_warnings

        err = io.StringIO()
        with redirect_stderr(err):
            _print_data_warnings({"warnings": []}, {})
        self.assertEqual(err.getvalue(), "")

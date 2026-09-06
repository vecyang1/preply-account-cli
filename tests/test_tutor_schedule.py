import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from preply_cli.cli import build_parser
from preply_cli.cli.schedule_cmds import cmd_tutor_schedule
from preply_cli.public_schedule import (
    NIGHT_CUTOFF_HOUR,
    PublicScheduleError,
    build_schedule_summary,
    extract_tutor_id,
    load_tutor_schedule,
    parse_tutor_schedule,
)


class TutorScheduleIdExtractionTests(unittest.TestCase):
    def test_extract_from_plain_numeric_id(self):
        self.assertEqual(extract_tutor_id("6558836"), 6558836)
        self.assertEqual(extract_tutor_id(" 2807691 "), 2807691)

    def test_extract_from_full_preply_url(self):
        self.assertEqual(
            extract_tutor_id("https://preply.com/en/tutor/6558836"),
            6558836,
        )
        self.assertEqual(
            extract_tutor_id("https://preply.com/en/tutor/6558836?source=search&featured=true"),
            6558836,
        )

    def test_extract_from_schemeless_url(self):
        self.assertEqual(
            extract_tutor_id("preply.com/en/tutor/6558836"),
            6558836,
        )

    def test_extract_invalid_source_raises_clean_error(self):
        with self.assertRaises(PublicScheduleError) as caught:
            extract_tutor_id("https://preply.com/en/learn-english")
        self.assertIn("Could not extract numeric tutor ID", str(caught.exception))


class TutorScheduleParsingAndSummaryTests(unittest.TestCase):
    def setUp(self):
        # Struktur identical to live Preply BookingTimeslots response
        self.sample_payload = {
            "tutor": {
                "id": 6558836,
                "bookingWindowInterval": 180,
                "timeslotsForBooking": [
                    {
                        "dateStart": "2026-09-05T09:00:00",
                        "dateEnd": "2026-09-05T09:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "D.C.",
                    },
                    {
                        "dateStart": "2026-09-05T10:00:00",
                        "dateEnd": "2026-09-05T10:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "S.T.",
                    },
                    {
                        "dateStart": "2026-09-05T13:00:00",
                        "dateEnd": "2026-09-05T13:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "M.K.",
                    },
                    {
                        "dateStart": "2026-09-05T14:00:00",
                        "dateEnd": "2026-09-05T14:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "V.Y.",
                    },
                    {
                        "dateStart": "2026-09-06T19:00:00",
                        "dateEnd": "2026-09-06T19:50:00",
                        "type": "FREE",
                        "bookedTimeslotUserInitials": None,
                    },
                    {
                        "dateStart": "2026-09-06T20:00:00",
                        "dateEnd": "2026-09-06T20:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "A.B.",
                    },
                ],
            }
        }

    def test_parse_tutor_schedule_and_summary_totals(self):
        result = parse_tutor_schedule(
            self.sample_payload,
            date_start="2026-09-05",
            date_end="2026-09-07",
            tzname="Asia/Ho_Chi_Minh",
        )
        self.assertEqual(result["tutor_id"], 6558836)
        self.assertEqual(result["booking_window_interval"], 180)
        self.assertEqual(len(result["slots"]), 6)

        summary = result["summary"]
        self.assertEqual(summary["total_slots"], 6)
        self.assertEqual(summary["booked_slots"], 5)
        self.assertEqual(summary["free_slots"], 1)
        self.assertEqual(summary["night_booked"], 1)  # 2026-09-06 20:00
        self.assertEqual(summary["night_free"], 1)    # 2026-09-06 19:00

    def test_saturday_2026_09_05_has_zero_night_slots(self):
        result = parse_tutor_schedule(
            self.sample_payload,
            date_start="2026-09-05",
            date_end="2026-09-07",
            tzname="Asia/Ho_Chi_Minh",
        )
        daily = result["summary"]["daily"]
        self.assertIn("2026-09-05", daily)
        sat = daily["2026-09-05"]

        self.assertEqual(sat["booked"], 4)
        self.assertEqual(sat["free"], 0)
        self.assertEqual(sat["earliest"], "09:00")
        self.assertEqual(sat["latest"], "14:50")
        self.assertFalse(sat["has_night_slots"])
        self.assertEqual(sat["night_slots"], 0)

    def test_sunday_2026_09_06_identifies_night_slots(self):
        result = parse_tutor_schedule(
            self.sample_payload,
            date_start="2026-09-05",
            date_end="2026-09-07",
            tzname="Asia/Ho_Chi_Minh",
        )
        daily = result["summary"]["daily"]
        sun = daily["2026-09-06"]

        self.assertTrue(sun["has_night_slots"])
        self.assertEqual(sun["night_slots"], 2)
        self.assertEqual(sun["booked"], 1)
        self.assertEqual(sun["free"], 1)
        self.assertEqual(sun["earliest"], "19:00")
        self.assertEqual(sun["latest"], "20:50")

    def test_load_from_offline_fixture_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(self.sample_payload, tf)
            temp_path = tf.name

        try:
            data = load_tutor_schedule(
                source=temp_path,
                date_start="2026-09-05",
                days=2,
                tzname="Asia/Ho_Chi_Minh",
            )
            self.assertEqual(data["tutor_id"], 6558836)
            self.assertEqual(len(data["slots"]), 6)
            self.assertEqual(data["summary"]["booked_slots"], 5)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_utc_aware_timestamps_converted_to_local_tz(self):
        # 12:30 UTC + 7h (Asia/Ho_Chi_Minh) = 19:30 Vietnam time
        payload = {
            "tutor": {
                "id": 3602540,
                "bookingWindowInterval": 180,
                "timeslotsForBooking": [
                    {
                        "dateStart": "2026-09-06T12:30:00+00:00",
                        "dateEnd": "2026-09-06T13:30:00+00:00",
                        "type": "FREE",
                        "bookedTimeslotUserInitials": None,
                    }
                ],
            }
        }
        res = parse_tutor_schedule(payload, "2026-09-06", "2026-09-07", "Asia/Ho_Chi_Minh")
        slot = res["slots"][0]
        self.assertEqual(slot["date"], "2026-09-06")
        self.assertEqual(slot["start_time"], "19:30")
        self.assertEqual(slot["end_time"], "20:30")
        self.assertTrue(slot["is_night"])



class TutorScheduleCliCommandTests(unittest.TestCase):
    def setUp(self):
        self.sample_payload = {
            "tutor": {
                "id": 6558836,
                "bookingWindowInterval": 90,
                "timeslotsForBooking": [
                    {
                        "dateStart": "2026-09-05T09:00:00",
                        "dateEnd": "2026-09-05T09:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "D.C.",
                    },
                    {
                        "dateStart": "2026-09-05T14:00:00",
                        "dateEnd": "2026-09-05T14:50:00",
                        "type": "BOOKED",
                        "bookedTimeslotUserInitials": "V.Y.",
                    },
                ],
            }
        }
        self.temp_file = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(self.sample_payload, self.temp_file)
        self.temp_file.close()

    def tearDown(self):
        Path(self.temp_file.name).unlink(missing_ok=True)

    def test_cli_json_output(self):
        parser = build_parser()
        args = parser.parse_args(["tutor-schedule", "-f", self.temp_file.name, "--json"])

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            args.func(args)

        output = buf.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed["tutor_id"], 6558836)
        self.assertEqual(len(parsed["slots"]), 2)
        self.assertEqual(parsed["summary"]["booked_slots"], 2)

    def test_cli_csv_output(self):
        parser = build_parser()
        args = parser.parse_args(["tutor-schedule", "-f", self.temp_file.name, "--csv"])

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            args.func(args)

        output = buf.getvalue()
        lines = output.strip().splitlines()
        self.assertEqual(lines[0], "date,time,duration,type,student,night")
        self.assertIn("2026-09-05,09:00 - 09:50,50m,BOOKED,D.C.,No", lines)

    def test_cli_table_output(self):
        parser = build_parser()
        args = parser.parse_args(["tutor-schedule", "-f", self.temp_file.name])

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            args.func(args)

        output = buf.getvalue()
        self.assertIn("Schedule Overview", output)
        self.assertIn("Daily Breakdown", output)
        self.assertIn("Timeslots (2 total)", output)
        self.assertIn("6558836", output)
        self.assertIn("2026-09-05", output)
        self.assertIn("D.C.", output)


if __name__ == "__main__":
    unittest.main()

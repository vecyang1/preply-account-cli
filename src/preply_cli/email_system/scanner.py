"""Scanner and parsing engine for Preply emails.

Extracts structured events from live Spark Desktop searches or local JSON caches.
Categorizes both Learner and Tutor communications into well-defined contracts.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .contracts import EmailCategory, EmailRecord, UserRole

logger = logging.getLogger(__name__)


class PreplyEmailScanner:
    """Scanner for Preply notification and transaction emails."""

    # Regex patterns for subject classification
    LEARNER_PATTERNS = [
        (r"Your\s+([A-Za-z]+)\s+lesson\s+is\s+coming\s+up", EmailCategory.LESSON_UPCOMING),
        (r"Your\s+lesson\s+is\s+(?:tomorrow|today)\s+at", EmailCategory.LESSON_UPCOMING),
        (r"Check\s+out\s+your\s+lesson\s+schedule", EmailCategory.LESSON_UPCOMING),
        (r"Your\s+lesson\s+with\s+([A-Za-z]+)\s+was\s+autoconfirmed", EmailCategory.LESSON_COMPLETED),
        (r"(?:Please\s+confirm\s+your\s+lesson|⭕)", EmailCategory.LESSON_CONFIRM_REQUEST),
        (r"([A-Za-z]+),\s+your\s+subscription\s+has\s+been\s+renewed", EmailCategory.SUBSCRIPTION_RENEWED),
        (r"You\s+used\s+all\s+your\s+monthly\s+hours", EmailCategory.MONTHLY_HOURS_DEPLETED),
        (r"You\s+(?:paused|postponed)\s+your\s+(?:subscription|renewal\s+date)", EmailCategory.SUBSCRIPTION_PAUSED),
        (r"You\s+downgraded\s+your\s+subscription", EmailCategory.SUBSCRIPTION_DOWNGRADED),
        (r"(?:Oops!\s+Time\s+to\s+restart\s+your\s+streak|You’ve⚡|You’re\s+back\s+on\s+track)", EmailCategory.STREAK_PROGRESS),
        (r"New\s+message\s+from\s+([A-Za-z]+)", EmailCategory.TUTOR_MESSAGE),
        (r"([A-Za-z]+)\s+rescheduled\s+your\s+lesson", EmailCategory.LESSON_RESCHEDULED),
        (r"You\s+cancelled\s+your\s+([A-Za-z]+)?\s*lesson", EmailCategory.LESSON_CANCELLED),
        (r"You’ve\s+subscribed\s+to\s+([A-Za-z]+)\s+with\s+([A-Za-z]+)", EmailCategory.SUBSCRIPTION_RENEWED),
        (r"first\s+([A-Za-z]+)\s+lesson\s+with\s+([A-Za-z]+)\s+is", EmailCategory.LESSON_UPCOMING),
    ]

    TUTOR_PATTERNS = [
        (r"([A-Za-z\u4e00-\u9fff\u3040-\u30ff]+)\s+confirmed\s+a\s+lesson", EmailCategory.LESSON_COMPLETED),
        (r"([A-Za-z\u4e00-\u9fff\u3040-\u30ff]+)\s+scheduled\s+a\s+new\s+lesson", EmailCategory.LESSON_SCHEDULED),
        (r"([A-Za-z\u4e00-\u9fff\u3040-\u30ff]+)\s+tried\s+to\s+book\s+a\s+lesson", EmailCategory.TUTOR_BOOKING_ATTEMPT),
        (r"([A-Za-z\u4e00-\u9fff\u3040-\u30ff]+)\s+cancelled\s+their\s+lesson", EmailCategory.LESSON_CANCELLED),
        (r"(?:It’s\s+time\s+to\s+get\s+paid|It’s\s+payday|has\s+been\s+deposited\s+in\s+your\s+account|Verify\s+your\s+withdrawal)", EmailCategory.TUTOR_PAYOUT),
        (r"(?:Preply-versary|You\s+should\s+be\s+proud|Tutor\s+Community\s+Award|New\s+favorite)", EmailCategory.TUTOR_CELEBRATION),
    ]

    def categorize_learner_subject(self, subject: str) -> tuple[EmailCategory, Optional[str], Optional[str]]:
        """Return (category, tutor_name, subject_name) from learner email subject."""
        for pattern, cat in self.LEARNER_PATTERNS:
            m = re.search(pattern, subject, re.IGNORECASE)
            if m:
                groups = m.groups()
                tutor_name = None
                subject_name = None
                if cat == EmailCategory.LESSON_UPCOMING and groups:
                    subject_name = groups[0]
                elif cat == EmailCategory.LESSON_COMPLETED and groups:
                    tutor_name = groups[0]
                elif cat == EmailCategory.TUTOR_MESSAGE and groups:
                    tutor_name = groups[0]
                elif cat == EmailCategory.LESSON_RESCHEDULED and groups:
                    tutor_name = groups[0]
                elif cat == EmailCategory.LESSON_CANCELLED and groups:
                    subject_name = groups[0]
                return cat, tutor_name, subject_name
        return EmailCategory.GENERAL_NOTIFICATION, None, None

    def categorize_tutor_subject(self, subject: str) -> tuple[EmailCategory, Optional[str]]:
        """Return (category, student_name) from tutor email subject."""
        for pattern, cat in self.TUTOR_PATTERNS:
            m = re.search(pattern, subject, re.IGNORECASE)
            if m:
                groups = m.groups()
                student_name = groups[0] if groups else None
                return cat, student_name
        return EmailCategory.GENERAL_NOTIFICATION, None

    def parse_raw_record(self, raw: dict[str, Any], default_role: UserRole) -> EmailRecord:
        """Parse a raw spark email search row into an EmailRecord."""
        subject = raw.get("subject", "").strip()
        account = raw.get("account", "").strip()
        msg_id = int(raw.get("id", 0))
        sender = raw.get("from", "").strip()
        dt = raw.get("date", "").strip()

        # Determine role based on account or default
        if "yanghxmail" in account.lower():
            role = UserRole.TUTOR
        elif "foxmail" in account.lower() or "vecs" in account.lower():
            role = UserRole.LEARNER
        else:
            role = default_role

        if role == UserRole.TUTOR:
            cat, student_name = self.categorize_tutor_subject(subject)
            tutor_name = None
            subject_name = None
        else:
            cat, tutor_name, subject_name = self.categorize_learner_subject(subject)
            student_name = None

        return EmailRecord(
            message_id=msg_id,
            account=account,
            sender=sender,
            date=dt,
            subject=subject,
            category=cat,
            role=role,
            tutor_name=tutor_name,
            student_name=student_name,
            subject_name=subject_name,
            snippet=raw.get("snippet", "")
        )

    def scan_from_file(self, file_path: str | Path) -> list[EmailRecord]:
        """Load and parse email records from a saved JSON cache."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Scan file not found: {file_path}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        records = []
        # Handle dict format with learner_emails and tutor_emails
        if isinstance(data, dict):
            for e in data.get("learner_emails", []):
                records.append(self.parse_raw_record(e, UserRole.LEARNER))
            for e in data.get("tutor_emails", []):
                records.append(self.parse_raw_record(e, UserRole.TUTOR))
        elif isinstance(data, list):
            for e in data:
                records.append(self.parse_raw_record(e, UserRole.LEARNER))
        return records

    def scan_from_spark(self, account: str, max_pages: int = 15) -> list[EmailRecord]:
        """Query Spark Desktop CLI for live preply emails."""
        records = []
        role = UserRole.TUTOR if "yanghxmail" in account.lower() else UserRole.LEARNER
        for page in range(1, max_pages + 1):
            cmd = [
                "spark", "search",
                "--filter", "from:preply",
                "--in", account,
                "--page", str(page),
                "--page-size", "100"
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            except (subprocess.SubprocessError, FileNotFoundError) as exc:
                logger.warning("Spark CLI unavailable: %s", exc)
                break

            lines = res.stdout.splitlines()
            page_found = 0
            for line in lines:
                m = re.search(
                    r"^\s*(\d+)\s+(\S+@\S+)\s+(.+?)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+(.+?)(?:\s{2,}(?:unread|attachment|,|\s)+)?$",
                    line.rstrip()
                )
                if m:
                    msg_id, acct, frm, dt, subj = m.groups()
                    raw = {
                        "id": int(msg_id),
                        "account": acct.strip(),
                        "from": frm.strip(),
                        "date": dt.strip(),
                        "subject": subj.strip()
                    }
                    records.append(self.parse_raw_record(raw, role))
                    page_found += 1
            if page_found < 100:
                break
        return records

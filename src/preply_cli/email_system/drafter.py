"""Drafter and delivery dispatch engine.

Bridges:
- Spark Desktop CLI (use-spark): pushes rendered digests directly into user's live drafts.
- Local preview generation: exports HTML for instant browser visual inspection.
- FluentCRM compatibility (fluentcrm-ops): supports pushing campaigns / subscriber notes.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

__file__ = globals().get("__file__", "")
logger = logging.getLogger(__name__)


class EmailDrafter:
    """Dispatches and drafts generated digests across local email surfaces."""

    @classmethod
    def create_spark_draft(
        cls,
        to_email: str,
        subject: str,
        body_text: str,
        account_email: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create an email draft directly in the running Spark Desktop application."""
        cmd = [
            "spark", "draft",
            "--to", to_email,
            "--subject", subject,
            "--body", body_text,
        ]
        if account_email:
            cmd.extend(["--account", account_email])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            stdout = res.stdout
            # Parse draft ID and deep link
            # Output format from Spark CLI:
            # ID: 1234
            # Link: https://sparkmailapp.com/dpl/bl?token=...
            draft_id = None
            deep_link = None
            for line in stdout.splitlines():
                if line.startswith("ID:"):
                    draft_id = line.split(":", 1)[1].strip()
                elif "Link:" in line:
                    deep_link = line.split("Link:", 1)[1].strip()

            if draft_id or "Draft created" in stdout or res.returncode == 0:
                return {
                    "success": True,
                    "status": "drafted",
                    "draft_id": draft_id or "created",
                    "deep_link": deep_link,
                    "raw_output": stdout,
                }
            else:
                return {
                    "success": False,
                    "status": "spark_error",
                    "error": res.stderr or stdout,
                }
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Spark Desktop CLI unavailable: %s", exc)
            return {
                "success": False,
                "status": "spark_unavailable",
                "error": str(exc),
            }

    @classmethod
    def save_preview_html(
        cls,
        html_content: str,
        out_path: Optional[str | Path] = None,
    ) -> Path:
        """Save HTML digest to disk for browser verification and visual auditing."""
        if out_path:
            target = Path(out_path).resolve()
        else:
            data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            target = data_dir / "preview_digest.html"

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(html_content)
        return target

    @classmethod
    def open_in_browser(cls, file_path: Path) -> bool:
        """Open the rendered HTML file in the default macOS browser."""
        try:
            subprocess.run(["open", str(file_path)], check=True)
            return True
        except Exception as exc:
            logger.warning("Could not open browser: %s", exc)
            return False

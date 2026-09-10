"""Automated execution and scheduling runner for periodic Preply digests.

Provides:
- DigestAutomationRunner: End-to-end weekly pipeline (scan -> calculate -> generate -> draft/CRM -> archive log).
- Cron schedule generator: Produces bulletproof crontab entries for scheduled unattended execution.
- Execution history logging: Maintains append-only audit trail in data/digest_run_log.json.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .calculator import SSOTCalculator
from .contracts import (
    CadenceType,
    DigestConfig,
    DigestRunResult,
    Language,
    LearnerMetrics,
    TutorMetrics,
    UserRole,
)
from .crm_sync import FluentCRMSync
from .drafter import EmailDrafter
from .renderer import XinChaoViEmailRenderer
from .scanner import PreplyEmailScanner

__file__ = globals().get("__file__", "")



class DigestAutomationRunner:
    """Executes the full automated pipeline for Preply periodic motivational digests."""

    @staticmethod
    def get_default_data_dir() -> Path:
        """Resolve path to default data directory."""
        return Path(__file__).resolve().parent.parent.parent.parent / "data"

    @classmethod
    def run_pipeline(
        cls,
        role: UserRole = UserRole.LEARNER,
        language: Language = Language.ZH,
        in_file: Optional[str] = None,
        spark_draft: bool = False,
        push_crm: bool = False,
        crm_site: str = "xinchaovi.com",
        dry_run: bool = False,
        out_dir: Optional[str] = None,
        recipient_override: Optional[str] = None,
    ) -> list[DigestRunResult]:
        """Run the end-to-end automated digest pipeline for specified role(s)."""
        data_dir = cls.get_default_data_dir()
        archive_dir = Path(out_dir) if out_dir else (data_dir / "digests")
        archive_dir.mkdir(parents=True, exist_ok=True)

        scanner = PreplyEmailScanner()
        scan_cache = Path(in_file) if in_file else (data_dir / "preply_scanned_emails.json")
        if scan_cache.exists():
            emails = scanner.scan_from_file(scan_cache)
        else:
            emails = scanner.scan_from_spark("learner@example.com", max_pages=6)
            emails.extend(scanner.scan_from_spark("tutor@example.com", max_pages=4))

        roles_to_run = [UserRole.LEARNER, UserRole.TUTOR] if role == UserRole.BOTH else [role]
        results: list[DigestRunResult] = []
        now_ts = datetime.now()
        timestamp_str = now_ts.strftime("%Y%m%d_%H%M%S")

        for r in roles_to_run:
            role_emails = [e for e in emails if e.role == r]
            snap_file = data_dir / ("tutor-snapshot.json" if r == UserRole.TUTOR else "learner-snapshot.json")
            snap_data = None
            if snap_file.exists():
                try:
                    with open(snap_file, "r", encoding="utf-8") as sf:
                        snap_data = json.load(sf)
                except Exception:
                    snap_data = None

            recipient = recipient_override or ("tutor@example.com" if r == UserRole.TUTOR else "learner@example.com")
            config = DigestConfig(
                role=r,
                language=language,
                recipient_email=recipient,
                portal_url="https://xinchaovi.com/student/",
                booking_url="https://xinchaovi.com/student/",
            )

            if r == UserRole.TUTOR:
                t_metrics = SSOTCalculator.derive_tutor_metrics(role_emails, snap_data)
                subject, html, text = XinChaoViEmailRenderer.render_tutor_email(t_metrics, config)
            else:
                l_metrics = SSOTCalculator.derive_learner_metrics(role_emails, snap_data)
                subject, html, text = XinChaoViEmailRenderer.render_learner_email(l_metrics, config)

            # Archive artifacts
            html_path = archive_dir / f"digest_{r.value}_{language.value}_{timestamp_str}.html"
            text_path = archive_dir / f"digest_{r.value}_{language.value}_{timestamp_str}.txt"
            if not dry_run:
                with open(html_path, "w", encoding="utf-8") as hf:
                    hf.write(html)
                with open(text_path, "w", encoding="utf-8") as tf:
                    tf.write(text)

            draft_id = None
            if spark_draft and not dry_run:
                draft_res = EmailDrafter.create_spark_draft(
                    to_email=recipient,
                    subject=subject,
                    body_text=text,
                )
                if draft_res.get("success"):
                    draft_id = draft_res.get("draft_id")

            crm_id = None
            if push_crm:
                post_title = (
                    f"[XinChaoVi] Preply 教学周报 - 导师课时与成就追踪 ({language.value.upper()})"
                    if r == UserRole.TUTOR
                    else f"[XinChaoVi] Preply 学习周报 - 学员鼓励与进度追踪 ({language.value.upper()})"
                )
                crm_res = FluentCRMSync.push_template(
                    title=post_title,
                    subject=subject,
                    html_content=html,
                    excerpt=f"Preply weekly motivational digest for {r.value}",
                    site=crm_site,
                    dry_run=dry_run,
                )
                if crm_res.success:
                    crm_id = crm_res.template_id

            run_res = DigestRunResult(
                timestamp=now_ts.isoformat(),
                role=r,
                language=language,
                subject=subject,
                recipient=recipient,
                generated_html_path=str(html_path) if not dry_run else "[dry-run]",
                generated_text_path=str(text_path) if not dry_run else "[dry-run]",
                spark_draft_id=draft_id,
                crm_template_id=crm_id,
                success=True,
            )
            results.append(run_res)

        # Audit trail logging
        if not dry_run:
            log_file = data_dir / "digest_run_log.json"
            existing_logs = []
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8") as lf:
                        existing_logs = json.load(lf)
                except Exception:
                    existing_logs = []
            for item in results:
                existing_logs.append(item.to_dict())
            with open(log_file, "w", encoding="utf-8") as lf:
                json.dump(existing_logs, lf, indent=2, ensure_ascii=False)

        return results

    @classmethod
    def generate_cron_entry(
        cls,
        python_bin: Optional[str] = None,
        role: UserRole = UserRole.BOTH,
        language: Language = Language.ZH,
        draft: bool = True,
        push_crm: bool = True,
        schedule_expression: str = "0 9 * * 1",  # Every Monday at 9:00 AM
    ) -> str:
        """Generate a complete crontab entry for weekly automated execution."""
        py = python_bin or sys.executable
        project_dir = Path(__file__).resolve().parent.parent.parent.parent
        data_dir = project_dir / "data"
        log_out = data_dir / "digest_cron.log"

        flags = [f"--role {role.value}", f"--lang {language.value}"]
        if draft:
            flags.append("--draft")
        if push_crm:
            flags.append("--push-crm")

        cmd = f"cd '{project_dir}' && {py} -m preply_cli digest run {' '.join(flags)} >> '{log_out}' 2>&1"
        return f"{schedule_expression} {cmd}"

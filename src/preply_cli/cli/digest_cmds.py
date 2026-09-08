"""CLI command implementations for `preply digest`.

Exposes:
- preply digest scan: Scan Preply emails from Spark or file cache
- preply digest calculate: Calculate derived SSOT metrics
- preply digest generate: Render production motivational email
- preply digest draft: Push draft to live Spark Desktop application
- preply digest preview: Save and open HTML preview in browser
- preply digest verify: Run mathematical invariant checks
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..email_system import (
    CadenceType,
    DigestConfig,
    DigestResult,
    EmailCategory,
    EmailDrafter,
    FluentCRMSync,
    Language,
    LearnerMetrics,
    Milestone,
    PreplyEmailScanner,
    PsychologicalCopywriter,
    SSOTCalculator,
    UserRole,
    XinChaoViEmailRenderer,
)
from ..formatting import format_table
from ._shared import _print_json

__file__ = globals().get("__file__", "")


def _log(msg: Any = "") -> None:
    print(msg)


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DEFAULT_SCAN_CACHE = DEFAULT_DATA_DIR / "preply_scanned_emails.json"
DEFAULT_LEARNER_SNAPSHOT = DEFAULT_DATA_DIR / "learner-snapshot.json"
DEFAULT_TUTOR_SNAPSHOT = DEFAULT_DATA_DIR / "tutor-snapshot.json"


def _load_emails(in_file: str | None, role: UserRole) -> list[Any]:
    """Helper to load emails from file cache or scan live Spark."""
    scanner = PreplyEmailScanner()
    cache_path = Path(in_file) if in_file else DEFAULT_SCAN_CACHE

    if cache_path.exists():
        emails = scanner.scan_from_file(cache_path)
    else:
        # Fallback to spark live scan
        account = "yanghxmail@gmail.com" if role == UserRole.TUTOR else "vecs@foxmail.com"
        emails = scanner.scan_from_spark(account, max_pages=10)

    if role == UserRole.LEARNER:
        return [e for e in emails if e.role == UserRole.LEARNER]
    elif role == UserRole.TUTOR:
        return [e for e in emails if e.role == UserRole.TUTOR]
    return emails


def _load_snapshot(role: UserRole) -> dict[str, Any] | None:
    """Helper to load existing snapshot data if available."""
    snap_path = DEFAULT_TUTOR_SNAPSHOT if role == UserRole.TUTOR else DEFAULT_LEARNER_SNAPSHOT
    if snap_path.exists():
        try:
            with open(snap_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def cmd_digest_scan(args: argparse.Namespace) -> int:
    """Scan Preply emails from Spark or parse an input file."""
    scanner = PreplyEmailScanner()
    records = []

    if getattr(args, "live", False):
        acct = getattr(args, "account", None)
        if acct:
            records = scanner.scan_from_spark(acct, max_pages=getattr(args, "max_pages", 10))
        else:
            records.extend(scanner.scan_from_spark("vecs@foxmail.com", max_pages=10))
            records.extend(scanner.scan_from_spark("yanghxmail@gmail.com", max_pages=10))
    else:
        source_file = getattr(args, "in_file", None) or DEFAULT_SCAN_CACHE
        if not Path(source_file).exists():
            # Run live scan if cache missing
            records.extend(scanner.scan_from_spark("vecs@foxmail.com", max_pages=6))
            records.extend(scanner.scan_from_spark("yanghxmail@gmail.com", max_pages=4))
        else:
            records = scanner.scan_from_file(source_file)

    save_path = getattr(args, "save", None)
    if save_path:
        out_p = Path(save_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in records], f, indent=2, ensure_ascii=False)

    if getattr(args, "json", False):
        _print_json([r.to_dict() for r in records])
        return 0

    # Summary table output
    rows = []
    category_counts: dict[str, int] = {}
    for r in records:
        category_counts[r.category.value] = category_counts.get(r.category.value, 0) + 1

    for cat, cnt in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        rows.append({"Event Category": cat, "Count": cnt})

    _log(f"Scanned {len(records)} Preply email events across accounts.\n")
    if rows:
        _log(format_table(rows, ["Event Category", "Count"]))
    return 0


def cmd_digest_calculate(args: argparse.Namespace) -> int:
    """Calculate derived SSOT metrics from scanned records and snapshot ledgers."""
    role_str = getattr(args, "role", "learner")
    role = UserRole(role_str)
    emails = _load_emails(getattr(args, "in_file", None), role)
    snapshot = _load_snapshot(role)

    if role == UserRole.TUTOR:
        metrics = SSOTCalculator.derive_tutor_metrics(emails, snapshot)
        if getattr(args, "json", False):
            _print_json(metrics.to_dict())
            return 0

        _log(f"=== Tutor Mentorship Metrics (SSOT) ===")
        _log(f"Total Lessons Taught: {metrics.total_lessons_taught}")
        _log(f"Active Students Mentored: {metrics.active_students_count}")
        _log(f"Booking Inquiries: {metrics.booking_attempts_count}")
        _log(f"Teaching Streak: {metrics.current_streak_weeks} weeks")
        if metrics.next_milestone:
            _log(f"Next Honor: {metrics.next_milestone.title} ({metrics.classes_needed_for_next} lessons needed)")
        return 0

    metrics = SSOTCalculator.derive_learner_metrics(emails, snapshot)
    if getattr(args, "json", False):
        _print_json(metrics.to_dict())
        return 0

    _log(f"=== Learner Progress Metrics (SSOT) ===")
    _log(f"Total Completed Lessons: {metrics.total_completed_lessons} ({metrics.total_hours:.1f} hours)")
    _log(f"Current Cycle: {metrics.current_cycle_consumed} / {metrics.current_cycle_granted} completed ({metrics.completion_rate_pct}%)")
    _log(f"Available Balance to Book: {metrics.available_balance} lesson(s)")
    _log(f"Learning Habit Streak: {metrics.current_streak_weeks} weeks")
    _log(f"Subscription Paused: {'Yes' if metrics.is_paused else 'No'}")
    if metrics.next_milestone:
        _log(f"Next Milestone: {metrics.next_milestone.title} ({metrics.classes_needed_for_next} classes to unlock)")
        _log(f"Unlocks: {metrics.next_milestone.perk}")
    return 0


def cmd_digest_generate(args: argparse.Namespace) -> int:
    """Generate production periodic email (HTML / Plaintext / JSON)."""
    role_str = getattr(args, "role", "learner")
    role = UserRole(role_str)
    lang_str = getattr(args, "lang", "en")
    language = Language(lang_str)
    fmt = getattr(args, "format", "html")

    emails = _load_emails(getattr(args, "in_file", None), role)
    snapshot = _load_snapshot(role)

    config = DigestConfig(
        role=role,
        language=language,
        portal_url="https://xinchaovi.com/student/",
        booking_url="https://xinchaovi.com/student/",
    )

    if role == UserRole.TUTOR:
        t_metrics = SSOTCalculator.derive_tutor_metrics(emails, snapshot)
        subject, html, text = XinChaoViEmailRenderer.render_tutor_email(t_metrics, config)
        summary = t_metrics.to_dict()
    else:
        l_metrics = SSOTCalculator.derive_learner_metrics(emails, snapshot)
        subject, html, text = XinChaoViEmailRenderer.render_learner_email(l_metrics, config)
        summary = l_metrics.to_dict()

    out_path = getattr(args, "out", None)
    if out_path:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        content = html if fmt == "html" else (json.dumps(summary, indent=2) if fmt == "json" else text)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(content)
        _log(f"Exported digest to {out_p}")
        return 0

    if fmt == "json":
        _print_json({"subject": subject, "summary": summary, "html": html, "text": text})
    elif fmt == "text":
        _log(text)
    else:
        _log(html)
    return 0


def cmd_digest_draft(args: argparse.Namespace) -> int:
    """Push generated digest directly into user's live Spark Desktop drafts."""
    role_str = getattr(args, "role", "learner")
    role = UserRole(role_str)
    lang_str = getattr(args, "lang", "en")
    language = Language(lang_str)

    to_email = getattr(args, "to", None)
    if not to_email:
        to_email = "vecs@foxmail.com" if role == UserRole.LEARNER else "yanghxmail@gmail.com"

    acct_email = getattr(args, "account", None)

    emails = _load_emails(getattr(args, "in_file", None), role)
    snapshot = _load_snapshot(role)
    config = DigestConfig(role=role, language=language)

    if role == UserRole.TUTOR:
        metrics = SSOTCalculator.derive_tutor_metrics(emails, snapshot)
        subject, html, text = XinChaoViEmailRenderer.render_tutor_email(metrics, config)
    else:
        metrics = SSOTCalculator.derive_learner_metrics(emails, snapshot)
        subject, html, text = XinChaoViEmailRenderer.render_learner_email(metrics, config)

    res = EmailDrafter.create_spark_draft(
        to_email=to_email,
        subject=subject,
        body_text=text,
        account_email=acct_email,
    )

    if res.get("success"):
        _log(f"Draft created successfully in Spark Desktop!")
        _log(f"Draft ID: {res.get('draft_id')}")
        if res.get("deep_link"):
            _log(f"Spark Deep Link: {res.get('deep_link')}")
        return 0
    else:
        _log(f"Could not create draft in Spark: {res.get('error')}")
        preview_path = EmailDrafter.save_preview_html(html)
        _log(f"Saved local HTML fallback to {preview_path}")
        return 1


def cmd_digest_preview(args: argparse.Namespace) -> int:
    """Save rendered HTML digest and open in default browser."""
    role_str = getattr(args, "role", "learner")
    role = UserRole(role_str)
    lang_str = getattr(args, "lang", "en")
    language = Language(lang_str)

    emails = _load_emails(getattr(args, "in_file", None), role)
    snapshot = _load_snapshot(role)
    config = DigestConfig(role=role, language=language)

    if role == UserRole.TUTOR:
        metrics = SSOTCalculator.derive_tutor_metrics(emails, snapshot)
        subject, html, text = XinChaoViEmailRenderer.render_tutor_email(metrics, config)
    else:
        metrics = SSOTCalculator.derive_learner_metrics(emails, snapshot)
        subject, html, text = XinChaoViEmailRenderer.render_learner_email(metrics, config)

    out_file = getattr(args, "out", None)
    target = EmailDrafter.save_preview_html(html, out_file)
    _log(f"Preview HTML saved: {target}")

    if getattr(args, "open", True):
        EmailDrafter.open_in_browser(target)
        _log(f"Opened preview in browser.")
    return 0


def cmd_digest_verify(args: argparse.Namespace) -> int:
    """Run mathematical and psychological invariant checks on the digest system."""
    _log("Running Preply Digest Invariant Verification...")

    # 1. Math invariant: Available Balance = max(0, Granted - Consumed - Scheduled)
    m = SSOTCalculator.derive_learner_metrics([], None, custom_granted=8)
    assert m.available_balance >= 0, "Balance cannot be negative"
    assert 0.0 <= m.completion_rate_pct <= 100.0, "Completion rate must be in [0, 100]"

    # 2. Milestones progress monotonically
    milestones = m.milestones
    assert len(milestones) == 6, "Must have exactly 6 canonical milestones"
    for i in range(len(milestones) - 1):
        assert milestones[i].required_count < milestones[i+1].required_count

    # 3. Psychological copywriter integrity: Must not use harsh/demotivating words
    copy_zh = PsychologicalCopywriter.craft_learner_copy(m, Language.ZH)
    for bad_word in ["过期作废", "惩罚", "强制扣款", "扣光", "失败"]:
        assert bad_word not in copy_zh["motivation_body"], f"Harsh word {bad_word} found in ZH copy"

    copy_en = PsychologicalCopywriter.craft_learner_copy(m, Language.EN)
    for bad_word in ["expired", "penalized", "punished", "forfeited your chance"]:
        assert bad_word not in copy_en["motivation_body"].lower(), f"Harsh phrase found in EN copy"

    # 4. HTML Renderer design token parity with https://xinchaovi.com/student
    cfg = DigestConfig()
    _, html, _ = XinChaoViEmailRenderer.render_learner_email(m, cfg)
    assert "#E07A5F" in html, "Must contain XinChaoVi Terracotta #E07A5F"
    assert "#1E293B" in html, "Must contain XinChaoVi Dark Slate #1E293B"
    assert "CURRENT CYCLE PROGRESS" in html, "Must contain progress section"
    assert "NEXT MILESTONE UNLOCK" in html, "Must contain milestone spotlight"

    _log(" All 4 invariant checks PASSED successfully.")
    return 0


def cmd_digest_push_crm(args: argparse.Namespace) -> int:
    """Push generated motivational email templates to FluentCRM on WordPress."""
    site = getattr(args, "site", "xinchaovi.com") or "xinchaovi.com"
    dry_run = getattr(args, "dry_run", False)
    role_str = getattr(args, "role", "all")
    lang_str = getattr(args, "lang", "zh-CN")
    language = Language(lang_str)

    _log(f"Synchronizing Preply digest templates with FluentCRM (site: {site})...")
    if dry_run:
        _log("[DRY-RUN MODE] No changes will be committed to remote WordPress database.")

    results = []

    if role_str in ("learner", "all"):
        emails = _load_emails(getattr(args, "in_file", None), UserRole.LEARNER)
        snapshot = _load_snapshot(UserRole.LEARNER)
        l_metrics = SSOTCalculator.derive_learner_metrics(emails, snapshot)
        cfg = DigestConfig(role=UserRole.LEARNER, language=language)
        subject, html, _ = XinChaoViEmailRenderer.render_learner_email(l_metrics, cfg)

        title = f"[XinChaoVi] Preply 学习周报 - 学员鼓励与进度追踪 ({language.value.upper()})"
        res = FluentCRMSync.push_template(
            title=title,
            subject=subject,
            html_content=html,
            excerpt="本周学习进度回顾与里程碑解锁",
            site=site,
            dry_run=dry_run,
        )
        results.append(res)

    if role_str in ("tutor", "all"):
        emails = _load_emails(getattr(args, "in_file", None), UserRole.TUTOR)
        snapshot = _load_snapshot(UserRole.TUTOR)
        t_metrics = SSOTCalculator.derive_tutor_metrics(emails, snapshot)
        cfg = DigestConfig(role=UserRole.TUTOR, language=language)
        subject, html, _ = XinChaoViEmailRenderer.render_tutor_email(t_metrics, cfg)

        title = f"[XinChaoVi] Preply 教学周报 - 导师课时与成就追踪 ({language.value.upper()})"
        res = FluentCRMSync.push_template(
            title=title,
            subject=subject,
            html_content=html,
            excerpt="本周教学里程碑回顾与新学员指引",
            site=site,
            dry_run=dry_run,
        )
        results.append(res)

    if getattr(args, "json", False):
        _print_json([r.to_dict() for r in results])
        return 0

    rows = []
    all_ok = True
    for r in results:
        status_str = "SUCCESS" if r.success else "FAILED"
        action_str = "UPDATED" if r.updated else ("CREATED" if r.success else "ERROR")
        if not r.success:
            all_ok = False
        rows.append({
            "Template Title": r.post_title,
            "Remote ID": str(r.template_id or "-"),
            "Action": action_str,
            "Status": status_str,
        })

    _log(format_table(rows, ["Template Title", "Remote ID", "Action", "Status"]))

    if all_ok:
        _log("\n FluentCRM templates synchronized and verified via remote readback.")
        return 0
    else:
        _log("\n❌ Some templates failed to synchronize. See error details.")
        return 1


def cmd_digest(args: argparse.Namespace) -> int:
    """Default handler for preply digest when invoked directly."""
    _log("Usage: preply digest {scan,calculate,generate,draft,preview,verify,push-crm} [options]")
    _log("Run 'preply digest --help' for details on each subcommand.")
    return 0


def register_digest_subparser(sub: argparse._SubParsersAction[Any]) -> None:
    """Attach the `digest` command group to the main Preply parser."""
    digest_parser = sub.add_parser(
        "digest",
        help="Periodic encouraging email system for teachers and students (XinChaoVi parity).",
    )
    digest_parser.set_defaults(func=cmd_digest)
    d_sub = digest_parser.add_subparsers(dest="digest_command")

    # scan
    scan_p = d_sub.add_parser("scan", help="Scan Preply emails from Spark or JSON cache.")
    scan_p.add_argument("--in-file", help="Path to input JSON scan file.")
    scan_p.add_argument("--save", help="Path to save scanned events.")
    scan_p.add_argument("--live", action="store_true", help="Perform live scan via Spark Desktop.")
    scan_p.add_argument("--account", help="Specific email account to scan.")
    scan_p.add_argument("--json", action="store_true")
    scan_p.set_defaults(func=cmd_digest_scan)

    # calculate
    calc_p = d_sub.add_parser("calculate", help="Calculate derived SSOT metrics for student or tutor.")
    calc_p.add_argument("--role", choices=["learner", "tutor"], default="learner")
    calc_p.add_argument("--in-file", help="Path to input JSON scan file.")
    calc_p.add_argument("--json", action="store_true")
    calc_p.set_defaults(func=cmd_digest_calculate)

    # generate
    gen_p = d_sub.add_parser("generate", help="Render periodic motivational email (HTML/Text/JSON).")
    gen_p.add_argument("--role", choices=["learner", "tutor"], default="learner")
    gen_p.add_argument("--lang", choices=["en", "zh-CN", "vi"], default="en")
    gen_p.add_argument("--format", choices=["html", "text", "json"], default="html")
    gen_p.add_argument("--out", help="Path to output file.")
    gen_p.add_argument("--in-file", help="Path to input JSON scan file.")
    gen_p.set_defaults(func=cmd_digest_generate)

    # draft
    draft_p = d_sub.add_parser("draft", help="Push draft to running Spark Desktop application.")
    draft_p.add_argument("--role", choices=["learner", "tutor"], default="learner")
    draft_p.add_argument("--to", help="Recipient email address.")
    draft_p.add_argument("--account", help="Sender account email in Spark.")
    draft_p.add_argument("--lang", choices=["en", "zh-CN", "vi"], default="en")
    draft_p.add_argument("--in-file", help="Path to input JSON scan file.")
    draft_p.set_defaults(func=cmd_digest_draft)

    # preview
    prev_p = d_sub.add_parser("preview", help="Save rendered HTML and open in browser.")
    prev_p.add_argument("--role", choices=["learner", "tutor"], default="learner")
    prev_p.add_argument("--lang", choices=["en", "zh-CN", "vi"], default="en")
    prev_p.add_argument("--out", help="Path to save HTML file.")
    prev_p.add_argument("--no-open", dest="open", action="store_false", help="Do not open browser.")
    prev_p.add_argument("--in-file", help="Path to input JSON scan file.")
    prev_p.set_defaults(func=cmd_digest_preview)

    # verify
    ver_p = d_sub.add_parser("verify", help="Run self-contained mathematical & design invariant checks.")
    ver_p.set_defaults(func=cmd_digest_verify)

    # push-crm
    push_p = d_sub.add_parser("push-crm", help="Push email templates to FluentCRM (fc_template).")
    push_p.add_argument("--role", choices=["learner", "tutor", "all"], default="all")
    push_p.add_argument("--lang", choices=["en", "zh-CN", "vi"], default="zh-CN")
    push_p.add_argument("--site", default="xinchaovi.com", help="Target WordPress site (default: xinchaovi.com).")
    push_p.add_argument("--dry-run", action="store_true", help="Preview payload without modifying remote database.")
    push_p.add_argument("--in-file", help="Path to input JSON scan file.")
    push_p.add_argument("--json", action="store_true")
    push_p.set_defaults(func=cmd_digest_push_crm)

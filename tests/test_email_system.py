"""Comprehensive test suite for Preply periodic email system.

Covers:
- Contracts & Type Safety
- Scanner subject classification (Learner & Tutor)
- SSOT Calculator & Mathematical Invariants (Positive & Adversarial)
- Psychological Copywriter ("说人话，不要说实话" & Multilingual)
- XinChaoVi Email Renderer (Design Token Parity & Responsive Layout)
- Drafter & Dispatch
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from preply_cli.email_system import (
    CadenceType,
    CRMPushResult,
    DigestAutomationRunner,
    DigestConfig,
    DigestResult,
    DigestRunResult,
    EmailCategory,
    EmailDrafter,
    EmailRecord,
    FluentCRMSync,
    Language,
    LearnerMetrics,
    Milestone,
    PreplyEmailScanner,
    PsychologicalCopywriter,
    SSOTCalculator,
    TutorMetrics,
    UpcomingSession,
    UserRole,
    XinChaoViEmailRenderer,
    get_default_learner_milestones,
    get_default_tutor_milestones,
)


class TestEmailContracts(unittest.TestCase):
    """Test contract definitions and serialization."""

    def test_email_record_serialization(self):
        rec = EmailRecord(
            message_id=713844,
            account="learner@example.com",
            sender="Preply <noreply@example.com>",
            date="2026-08-11 15:40",
            subject="You used all your monthly hours 🎉",
            category=EmailCategory.MONTHLY_HOURS_DEPLETED,
            role=UserRole.LEARNER,
            subject_name="Vietnamese",
        )
        d = rec.to_dict()
        self.assertEqual(d["category"], "monthly_hours_depleted")
        self.assertEqual(d["role"], "learner")

        restored = EmailRecord.from_dict(d)
        self.assertEqual(restored.message_id, 713844)
        self.assertEqual(restored.category, EmailCategory.MONTHLY_HOURS_DEPLETED)
        self.assertEqual(restored.role, UserRole.LEARNER)

    def test_digest_config_defaults(self):
        cfg = DigestConfig()
        self.assertEqual(cfg.cadence, CadenceType.WEEKLY)
        self.assertEqual(cfg.role, UserRole.LEARNER)
        self.assertEqual(cfg.language, Language.EN)
        self.assertTrue(cfg.portal_url.startswith("https://xinchaovi.com"))


class TestPreplyEmailScanner(unittest.TestCase):
    """Test email categorization and regex classification."""

    def setUp(self):
        self.scanner = PreplyEmailScanner()

    def test_learner_subject_classification(self):
        cases = [
            ("Your Vietnamese lesson is coming up ⏰", EmailCategory.LESSON_UPCOMING, "Vietnamese"),
            ("Your Music lesson is coming up ⏰", EmailCategory.LESSON_UPCOMING, "Music"),
            ("Chapelle, your subscription has been renewed 🎉", EmailCategory.SUBSCRIPTION_RENEWED, None),
            ("You used all your monthly hours 🎉", EmailCategory.MONTHLY_HOURS_DEPLETED, None),
            ("You paused your subscription ⏸️", EmailCategory.SUBSCRIPTION_PAUSED, None),
            ("Oops! Time to restart your streak", EmailCategory.STREAK_PROGRESS, None),
            ("You’ve⚡", EmailCategory.STREAK_PROGRESS, None),
            ("New message from  Victor ✉️", EmailCategory.TUTOR_MESSAGE, None),
            ("⭕ Please confirm your lesson", EmailCategory.LESSON_CONFIRM_REQUEST, None),
            ("Your lesson with Victor was autoconfirmed", EmailCategory.LESSON_COMPLETED, None),
        ]
        for subject, expected_cat, expected_subj in cases:
            cat, tutor, sub_name = self.scanner.categorize_learner_subject(subject)
            self.assertEqual(cat, expected_cat, f"Failed on subject: {subject}")
            if expected_subj:
                self.assertEqual(sub_name, expected_subj)

    def test_tutor_subject_classification(self):
        cases = [
            ("Alex confirmed a lesson", EmailCategory.LESSON_COMPLETED, "Alex"),
            ("John scheduled a new lesson", EmailCategory.LESSON_SCHEDULED, "John"),
            ("Maria tried to book a lesson", EmailCategory.TUTOR_BOOKING_ATTEMPT, "Maria"),
            ("Ken cancelled their lesson", EmailCategory.LESSON_CANCELLED, "Ken"),
            ("It’s time to get paid", EmailCategory.TUTOR_PAYOUT, None),
            ("You should be proud 🎉", EmailCategory.TUTOR_CELEBRATION, None),
        ]
        for subject, expected_cat, expected_student in cases:
            cat, student = self.scanner.categorize_tutor_subject(subject)
            self.assertEqual(cat, expected_cat, f"Failed on tutor subject: {subject}")
            if expected_student:
                self.assertEqual(student, expected_student)

    def test_unrecognized_subject_falls_back_safely(self):
        cat, tutor, sub_name = self.scanner.categorize_learner_subject("Random newsletter 123")
        self.assertEqual(cat, EmailCategory.GENERAL_NOTIFICATION)
        self.assertIsNone(tutor)
        self.assertIsNone(sub_name)


class TestSSOTCalculator(unittest.TestCase):
    """Test SSOT metric calculation and mathematical invariants."""

    def test_learner_mathematical_invariants(self):
        emails = [
            EmailRecord(
                message_id=1,
                account="learner@example.com",
                sender="Preply",
                date="2026-08-01 10:00",
                subject="Your lesson with Victor was autoconfirmed",
                category=EmailCategory.LESSON_COMPLETED,
                role=UserRole.LEARNER,
                tutor_name="Victor",
                subject_name="Vietnamese",
            ),
            EmailRecord(
                message_id=2,
                account="learner@example.com",
                sender="Preply",
                date="2026-08-05 10:00",
                subject="Your lesson with Victor was autoconfirmed",
                category=EmailCategory.LESSON_COMPLETED,
                role=UserRole.LEARNER,
                tutor_name="Victor",
                subject_name="Vietnamese",
            ),
            EmailRecord(
                message_id=3,
                account="learner@example.com",
                sender="Preply",
                date="2026-08-10 20:00",
                subject="Your Vietnamese lesson is coming up ⏰",
                category=EmailCategory.LESSON_UPCOMING,
                role=UserRole.LEARNER,
                tutor_name="Victor",
                subject_name="Vietnamese",
            ),
            EmailRecord(
                message_id=4,
                account="learner@example.com",
                sender="Preply",
                date="2026-08-01 12:00",
                subject="Chapelle, your subscription has been renewed 🎉",
                category=EmailCategory.SUBSCRIPTION_RENEWED,
                role=UserRole.LEARNER,
            ),
        ]
        metrics = SSOTCalculator.derive_learner_metrics(emails, custom_granted=4)

        # Invariant 1: Non-negative balance
        self.assertGreaterEqual(metrics.available_balance, 0)
        # Invariant 2: Total hours matches completed lessons * 1.0
        self.assertEqual(metrics.total_hours, float(metrics.total_completed_lessons))
        # Invariant 3: Completion rate clamped between 0 and 100
        self.assertGreaterEqual(metrics.completion_rate_pct, 0.0)
        self.assertLessEqual(metrics.completion_rate_pct, 100.0)
        # Invariant 4: Milestones unlocked up to total_completed_lessons
        for m in metrics.milestones:
            if m.required_count <= metrics.total_completed_lessons:
                self.assertTrue(m.unlocked)
            else:
                self.assertFalse(m.unlocked)

        # Next milestone verification
        if metrics.next_milestone:
            self.assertFalse(metrics.next_milestone.unlocked)
            self.assertEqual(
                metrics.classes_needed_for_next,
                max(0, metrics.next_milestone.required_count - metrics.total_completed_lessons),
            )

    def test_adversarial_zero_lessons_learner(self):
        """Zero lessons should not divide by zero or produce invalid percentages."""
        metrics = SSOTCalculator.derive_learner_metrics([], custom_granted=4)
        self.assertEqual(metrics.total_completed_lessons, 0)
        self.assertEqual(metrics.total_hours, 0.0)
        self.assertEqual(metrics.completion_rate_pct, 0.0)
        self.assertEqual(metrics.available_balance, 4)
        self.assertIsNotNone(metrics.next_milestone)
        self.assertEqual(metrics.classes_needed_for_next, 1)

    def test_tutor_metrics_derivation(self):
        emails = [
            EmailRecord(
                message_id=10,
                account="tutor@example.com",
                sender="Preply",
                date="2026-08-01 10:00",
                subject="StudentA confirmed a lesson",
                category=EmailCategory.LESSON_COMPLETED,
                role=UserRole.TUTOR,
                student_name="StudentA",
            ),
            EmailRecord(
                message_id=11,
                account="tutor@example.com",
                sender="Preply",
                date="2026-08-02 10:00",
                subject="StudentB confirmed a lesson",
                category=EmailCategory.LESSON_COMPLETED,
                role=UserRole.TUTOR,
                student_name="StudentB",
            ),
            EmailRecord(
                message_id=12,
                account="tutor@example.com",
                sender="Preply",
                date="2026-08-03 10:00",
                subject="StudentC tried to book a lesson",
                category=EmailCategory.TUTOR_BOOKING_ATTEMPT,
                role=UserRole.TUTOR,
                student_name="StudentC",
            ),
        ]
        metrics = SSOTCalculator.derive_tutor_metrics(emails)
        self.assertEqual(metrics.total_lessons_taught, 2)
        self.assertEqual(metrics.active_students_count, 2)
        self.assertEqual(metrics.booking_attempts_count, 1)
        self.assertIn("StudentA", metrics.student_names)


class TestPsychologicalCopywriter(unittest.TestCase):
    """Test empathy-first, positive-reinforcement copywriting ('说人话，不要说实话')."""

    def test_learner_paused_state_copy_zh(self):
        """Paused state should never sound punitive, framing pause as natural absorption."""
        metrics = LearnerMetrics(
            total_completed_lessons=12,
            total_hours=12.0,
            current_cycle_granted=4,
            current_cycle_consumed=0,
            current_cycle_scheduled=0,
            available_balance=4,
            completion_rate_pct=0.0,
            current_streak_weeks=2,
            next_renewal_date="2026-09-30",
            is_paused=True,
            milestones=get_default_learner_milestones(),
            next_milestone=get_default_learner_milestones()[4],
            classes_needed_for_next=8,
        )
        copy = PsychologicalCopywriter.craft_learner_copy(metrics, Language.ZH)
        self.assertIn("沉淀", copy["motivation_body"])
        self.assertIn("肌肉记忆", copy["motivation_body"])
        self.assertIn("温和的课桌", copy["motivation_body"])
        self.assertNotIn("欠费", copy["motivation_body"])
        self.assertNotIn("过期", copy["motivation_body"])

    def test_learner_near_milestone_copy_en(self):
        """When 1-2 classes away from milestone, motivate to cross the finish line."""
        metrics = LearnerMetrics(
            total_completed_lessons=9,
            total_hours=9.0,
            current_cycle_granted=4,
            current_cycle_consumed=3,
            current_cycle_scheduled=1,
            available_balance=1,
            completion_rate_pct=75.0,
            current_streak_weeks=3,
            next_renewal_date="2026-09-15",
            is_paused=False,
            milestones=get_default_learner_milestones(),
            next_milestone=get_default_learner_milestones()[3],
            classes_needed_for_next=1,
        )
        copy = PsychologicalCopywriter.craft_learner_copy(metrics, Language.EN)
        self.assertIn("1 session away", copy["motivation_body"])
        self.assertIn("Halfway Hero", copy["motivation_body"])
        self.assertIn("human conversation", copy["motivation_body"])

    def test_tutor_copy_zh(self):
        """Tutor copy should celebrate teaching impact, not just lesson tallies."""
        metrics = TutorMetrics(
            total_lessons_taught=48,
            active_students_count=6,
            student_names=["Alex", "Chris"],
            booking_attempts_count=2,
            payout_events_count=4,
            current_streak_weeks=8,
            milestones=get_default_tutor_milestones(),
            next_milestone=get_default_tutor_milestones()[2],
            classes_needed_for_next=2,
        )
        copy = PsychologicalCopywriter.craft_tutor_copy(metrics, Language.ZH)
        self.assertIn("48", copy["subject"])
        self.assertIn("点亮学员的新世界", copy["hero_headline"])
        self.assertIn("2 位潜在学员", copy["motivation_body"])


class TestXinChaoViEmailRenderer(unittest.TestCase):
    """Test HTML and Plaintext email rendering with design tokens parity."""

    def test_learner_email_design_tokens(self):
        metrics = LearnerMetrics(
            total_completed_lessons=14,
            total_hours=14.0,
            current_cycle_granted=4,
            current_cycle_consumed=3,
            current_cycle_scheduled=1,
            available_balance=1,
            completion_rate_pct=75.0,
            current_streak_weeks=4,
            next_renewal_date="2026-09-18",
            is_paused=False,
            milestones=get_default_learner_milestones(),
            next_milestone=get_default_learner_milestones()[4],
            classes_needed_for_next=6,
            upcoming_sessions=[
                UpcomingSession(
                    session_id="s1",
                    datetime_str="Thursday, Sep 10 at 7:00 PM",
                    partner_name="Thao Vy",
                    subject_name="Vietnamese",
                    topic="Authentic Saigon Street Food & Ordering Practice",
                )
            ],
        )
        config = DigestConfig(
            language=Language.EN,
            portal_url="https://xinchaovi.com/student/",
            booking_url="https://xinchaovi.com/student/",
        )
        subject, html, text = XinChaoViEmailRenderer.render_learner_email(metrics, config)

        self.assertIn("#E07A5F", html)
        self.assertIn("#1E293B", html)
        self.assertIn("#81B29A", html)
        self.assertIn("#F59E0B", html)
        self.assertIn("XinChaoVi Learning Hub", html)
        self.assertIn("Saigon Street Food", html)
        self.assertIn("https://xinchaovi.com/student/", html)

        self.assertIn("XinChaoVi Learning Hub", text)
        self.assertIn("14 lessons", text)
        self.assertIn("https://xinchaovi.com/student/", text)

    def test_tutor_email_rendering(self):
        metrics = TutorMetrics(
            total_lessons_taught=102,
            active_students_count=12,
            student_names=["Chapelle", "Liam"],
            booking_attempts_count=1,
            payout_events_count=10,
            current_streak_weeks=12,
            milestones=get_default_tutor_milestones(),
            next_milestone=get_default_tutor_milestones()[4],
            classes_needed_for_next=198,
        )
        config = DigestConfig(
            role=UserRole.TUTOR,
            language=Language.EN,
            portal_url="https://xinchaovi.com/student/",
        )
        subject, html, text = XinChaoViEmailRenderer.render_tutor_email(metrics, config)
        self.assertIn("#E07A5F", html)
        self.assertIn("102", subject)
        self.assertIn("MENTORSHIP", text)


class TestEmailDrafter(unittest.TestCase):
    """Test disk preview generation."""

    def test_save_preview_html(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_preview.html"
            target = EmailDrafter.save_preview_html("<h1>Test Digest</h1>", out_file)
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "<h1>Test Digest</h1>")


class TestFluentCRMSync(unittest.TestCase):
    """Test FluentCRM sync logic, dry runs, and serialization."""

    def test_crm_push_result_to_dict(self):
        res = CRMPushResult(
            success=True,
            template_id=2733,
            post_title="Test Title",
            updated=False,
            site="xinchaovi.com",
            readback_record={"ID": 2733, "post_status": "publish"},
        )
        d = res.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["template_id"], 2733)
        self.assertEqual(d["site"], "xinchaovi.com")
        self.assertFalse(d["updated"])

    def test_dry_run_push_template(self):
        res = FluentCRMSync.push_template(
            title="Dry Run Title",
            subject="Dry Run Subject",
            html_content="<p>Test</p>",
            site="xinchaovi.com",
            dry_run=True,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.template_id, 0)
        self.assertFalse(res.updated)
        self.assertIsNotNone(res.readback_record)
        self.assertEqual(res.readback_record.get("status"), "dry_run_preview")

    def test_seed_standard_templates_dry_run(self):
        results = FluentCRMSync.seed_standard_templates(site="xinchaovi.com", dry_run=True)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))

    def test_find_script_returns_valid_or_none(self):
        script = FluentCRMSync.find_fluentcrm_ops_script()
        if script:
            self.assertTrue(script.exists())


class TestAdversarialAndEdgeCases(unittest.TestCase):
    """Test edge cases, boundary conditions, and adversarial inputs."""

    def test_negative_hours_or_balances_clamped_to_zero(self):
        metrics = SSOTCalculator.derive_learner_metrics(
            [], snapshot_data={"current_cycle": {"consumed": -5, "granted": 4}}
        )
        self.assertGreaterEqual(metrics.available_balance, 0)
        self.assertGreaterEqual(metrics.completion_rate_pct, 0.0)

    def test_excessive_consumption_clamped_to_100_pct(self):
        metrics = SSOTCalculator.derive_learner_metrics(
            [], snapshot_data={"current_cycle": {"consumed": 20, "granted": 4}}
        )
        self.assertEqual(metrics.completion_rate_pct, 100.0)
        self.assertEqual(metrics.available_balance, 0)

    def test_empty_email_list_tutor(self):
        metrics = SSOTCalculator.derive_tutor_metrics([])
        self.assertEqual(metrics.total_lessons_taught, 0)
        self.assertEqual(metrics.active_students_count, 0)
        self.assertEqual(metrics.booking_attempts_count, 0)
        self.assertIsNotNone(metrics.next_milestone)

    def test_vietnamese_copy_tone_and_safety(self):
        metrics = SSOTCalculator.derive_learner_metrics([], custom_granted=8)
        copy_vi = PsychologicalCopywriter.craft_learner_copy(metrics, Language.VI)
        self.assertIn("học", copy_vi["subject"].lower())
        self.assertNotIn("hết hạn", copy_vi["motivation_body"].lower())
        self.assertNotIn("phạt", copy_vi["motivation_body"].lower())

    def test_renderer_with_no_upcoming_sessions(self):
        base_m = SSOTCalculator.derive_learner_metrics([], custom_granted=4)
        metrics = LearnerMetrics(
            total_completed_lessons=base_m.total_completed_lessons,
            total_hours=base_m.total_hours,
            current_cycle_granted=base_m.current_cycle_granted,
            current_cycle_consumed=base_m.current_cycle_consumed,
            current_cycle_scheduled=base_m.current_cycle_scheduled,
            available_balance=base_m.available_balance,
            completion_rate_pct=base_m.completion_rate_pct,
            current_streak_weeks=base_m.current_streak_weeks,
            next_renewal_date=base_m.next_renewal_date,
            is_paused=base_m.is_paused,
            milestones=base_m.milestones,
            next_milestone=base_m.next_milestone,
            classes_needed_for_next=base_m.classes_needed_for_next,
            upcoming_sessions=[],
        )
        config = DigestConfig(language=Language.ZH)
        subject, html, text = XinChaoViEmailRenderer.render_learner_email(metrics, config)
        self.assertIn("暂无待上课时", html)
        self.assertIn("预约下一节课", html)
        self.assertIn("https://xinchaovi.com/student/", html)


class TestDigestScheduler(unittest.TestCase):
    """Test automated digest execution runner and cron generator."""

    def test_generate_cron_entry_default(self):
        cron_str = DigestAutomationRunner.generate_cron_entry()
        self.assertTrue(cron_str.startswith("0 9 * * 1"))
        self.assertIn("preply_cli digest run", cron_str)
        self.assertIn("--role both", cron_str)
        self.assertIn("--lang zh-CN", cron_str)
        self.assertIn("--draft", cron_str)
        self.assertIn("--push-crm", cron_str)
        self.assertIn("digest_cron.log", cron_str)

    def test_generate_cron_entry_custom(self):
        cron_str = DigestAutomationRunner.generate_cron_entry(
            role=UserRole.LEARNER,
            language=Language.EN,
            draft=False,
            push_crm=False,
            schedule_expression="30 8 * * 5",
        )
        self.assertTrue(cron_str.startswith("30 8 * * 5"))
        self.assertIn("--role learner", cron_str)
        self.assertIn("--lang en", cron_str)
        self.assertNotIn("--draft", cron_str)
        self.assertNotIn("--push-crm", cron_str)

    def test_run_pipeline_dry_run_learner(self):
        results = DigestAutomationRunner.run_pipeline(
            role=UserRole.LEARNER,
            language=Language.ZH,
            dry_run=True,
        )
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.success)
        self.assertEqual(res.role, UserRole.LEARNER)
        self.assertEqual(res.language, Language.ZH)
        self.assertTrue(any(res.subject.startswith(emoji) for emoji in ["🌿", "🎉", "🌟", "✨"]))
        self.assertEqual(res.generated_html_path, "[dry-run]")
        d = res.to_dict()
        self.assertEqual(d["role"], "learner")
        self.assertTrue(d["success"])

    def test_run_pipeline_dry_run_both_roles(self):
        results = DigestAutomationRunner.run_pipeline(
            role=UserRole.BOTH,
            language=Language.EN,
            dry_run=True,
        )
        self.assertEqual(len(results), 2)
        roles = [r.role for r in results]
        self.assertIn(UserRole.LEARNER, roles)
        self.assertIn(UserRole.TUTOR, roles)
        self.assertTrue(all(r.success for r in results))


class TestPeakMilestonesAndOutlookRendering(unittest.TestCase):
    """Test extreme milestone tiers and cross-client Outlook / mobile markup."""

    def test_peak_learner_milestone_copy(self):
        # Test learner with 262 lessons (beyond standard 50-lesson tier)
        metrics = LearnerMetrics(
            total_completed_lessons=262,
            total_hours=261.5,
            current_cycle_granted=4,
            current_cycle_consumed=4,
            current_cycle_scheduled=0,
            available_balance=0,
            completion_rate_pct=100.0,
            current_streak_weeks=12,
            next_renewal_date="2026-09-15",
            is_paused=False,
            milestones=get_default_learner_milestones(),
            next_milestone=None,
            classes_needed_for_next=0,
            upcoming_sessions=[],
        )
        copy_zh = PsychologicalCopywriter.craft_learner_copy(metrics, Language.ZH)
        self.assertIn("殿堂级语言大家", copy_zh["spotlight_title"])
        self.assertIn("顶峰", copy_zh["spotlight_tag"])

        copy_en = PsychologicalCopywriter.craft_learner_copy(metrics, Language.EN)
        self.assertIn("Fluency Ambassador", copy_en["spotlight_title"])

        copy_vi = PsychologicalCopywriter.craft_learner_copy(metrics, Language.VI)
        self.assertIn("Đại Sứ Ngôn Ngữ", copy_vi["spotlight_title"])

    def test_peak_tutor_milestone_copy(self):
        # Test tutor with 330 lessons taught
        metrics = TutorMetrics(
            total_lessons_taught=330,
            active_students_count=30,
            student_names=["Alex", "Maria"],
            booking_attempts_count=6,
            payout_events_count=12,
            current_streak_weeks=24,
            milestones=get_default_tutor_milestones(),
            next_milestone=None,
            classes_needed_for_next=0,
            upcoming_sessions=[],
        )
        copy_zh = PsychologicalCopywriter.craft_tutor_copy(metrics, Language.ZH)
        self.assertIn("传奇领航导师", copy_zh["spotlight_title"])
        self.assertIn("全球教学大使", copy_zh["spotlight_perk"])

        copy_vi = PsychologicalCopywriter.craft_tutor_copy(metrics, Language.VI)
        self.assertIn("Giảng viên Tinh hoa Toàn cầu", copy_vi["spotlight_title"])

    def test_mso_and_responsive_markup_present(self):
        metrics = SSOTCalculator.derive_learner_metrics([])
        config = DigestConfig(language=Language.ZH)
        _, html, _ = XinChaoViEmailRenderer.render_learner_email(metrics, config)

        # MSO Outlook wrappers
        self.assertIn("<!--[if (gte mso 9)|(IE)]>", html)
        self.assertIn("<v:roundrect", html)
        self.assertIn("<![endif]-->", html)

        # Mobile and dark mode media queries
        self.assertIn("@media only screen and (max-width: 620px)", html)
        self.assertIn("@media (prefers-color-scheme: dark)", html)
        self.assertIn(".gm-stat-num", html)


if __name__ == "__main__":
    unittest.main()


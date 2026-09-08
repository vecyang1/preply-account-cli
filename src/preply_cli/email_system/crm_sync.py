"""FluentCRM synchronization engine for seeding Preply motivational email templates.

Pushes responsive, high-empathy learner and tutor email templates directly into
FluentCRM's `fc_template` custom post type via the `fluentcrm-ops` toolchain,
enforcing unidirectional data flow (write -> remote readback verification).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import DigestConfig, Language, UserRole
from .renderer import XinChaoViEmailRenderer
from .calculator import SSOTCalculator

__file__ = globals().get("__file__", "")


@dataclass(frozen=True)
class CRMPushResult:
    """Result of pushing a template to FluentCRM."""

    success: bool
    template_id: int | None
    post_title: str
    updated: bool
    site: str
    error: str | None = None
    readback_record: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "template_id": self.template_id,
            "post_title": self.post_title,
            "updated": self.updated,
            "site": self.site,
            "error": self.error,
            "readback_record": self.readback_record,
        }


class FluentCRMSync:
    """Synchronizes Preply motivational email templates to FluentCRM."""

    CANDIDATE_SCRIPT_PATHS = (
        Path.home() / ".codex" / "skills" / "fluentcrm-ops" / "scripts" / "fluentcrm_ops.py",
        Path.home() / ".gemini" / "antigravity" / "skills" / "fluentcrm-ops" / "scripts" / "fluentcrm_ops.py",
        Path.home() / ".agents" / "skills" / "fluentcrm-ops" / "scripts" / "fluentcrm_ops.py",
    )

    @classmethod
    def find_fluentcrm_ops_script(cls) -> Path | None:
        """Locate the canonical fluentcrm_ops.py script."""
        env_p = os.getenv("FLUENTCRM_OPS_SCRIPT")
        if env_p and Path(env_p).exists():
            return Path(env_p)

        for candidate in cls.CANDIDATE_SCRIPT_PATHS:
            if candidate.exists():
                return candidate
        return None

    @classmethod
    def push_template(
        cls,
        title: str,
        subject: str,
        html_content: str,
        excerpt: str = "",
        site: str = "xinchaovi.com",
        dry_run: bool = False,
    ) -> CRMPushResult:
        """Push an email template to FluentCRM fc_template table.

        Follows unidirectional data flow: writes via API, then reads back
        from database to verify actual persistence.
        """
        if dry_run:
            return CRMPushResult(
                success=True,
                template_id=0,
                post_title=title,
                updated=False,
                site=site,
                readback_record={"status": "dry_run_preview", "title": title, "subject": subject},
            )

        script = cls.find_fluentcrm_ops_script()
        if not script:
            return CRMPushResult(
                success=False,
                template_id=None,
                post_title=title,
                updated=False,
                site=site,
                error="fluentcrm_ops.py script not found on system paths.",
            )

        b64_content = base64.b64encode(html_content.encode("utf-8")).decode("ascii")
        escaped_title = title.replace("\"", "\\\"")
        escaped_subject = subject.replace("\"", "\\\"")
        escaped_excerpt = excerpt.replace("\"", "\\\"")

        php_code = f"""
global $wpdb;
$slug = fluentcrmTemplateCPTSlug();
$title = \"{escaped_title}\";
$subject = \"{escaped_subject}\";
$excerpt = \"{escaped_excerpt}\";
$content = base64_decode(\"{b64_content}\");

$existing = $wpdb->get_row($wpdb->prepare(\"SELECT ID FROM {{$wpdb->prefix}}posts WHERE post_title = %s AND post_type = %s\", $title, $slug));

if ($existing) {{
    $templateId = $existing->ID;
    wp_update_post([
        \"ID\" => $templateId,
        \"post_content\" => $content,
        \"post_excerpt\" => $excerpt,
        \"post_status\" => \"publish\",
    ]);
}} else {{
    $templateId = wp_insert_post([
        \"post_title\" => $title,
        \"post_content\" => $content,
        \"post_excerpt\" => $excerpt,
        \"post_status\" => \"publish\",
        \"post_type\" => $slug,
        \"post_date\" => current_time(\"mysql\"),
        \"post_date_gmt\" => gmdate(\"Y-m-d H:i:s\"),
        \"post_modified\" => current_time(\"mysql\"),
        \"post_modified_gmt\" => gmdate(\"Y-m-d H:i:s\"),
    ]);
}}

update_post_meta($templateId, \"_email_subject\", $subject);
update_post_meta($templateId, \"_edit_type\", \"html\");
update_post_meta($templateId, \"_design_template\", \"simple\");

return [
    \"template_id\" => $templateId,
    \"post_title\" => $title,
    \"updated\" => !empty($existing),
    \"status\" => \"success\",
];
"""
        cmd = [
            sys.executable,
            str(script),
            "--site",
            site,
            "php",
            "--confirm-write",
            php_code,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if res.returncode != 0:
                return CRMPushResult(
                    success=False,
                    template_id=None,
                    post_title=title,
                    updated=False,
                    site=site,
                    error=f"CLI failed (code {res.returncode}): {res.stderr.strip() or res.stdout.strip()}",
                )

            stdout = res.stdout.strip()
            idx = stdout.find("{")
            if idx == -1:
                return CRMPushResult(
                    success=False,
                    template_id=None,
                    post_title=title,
                    updated=False,
                    site=site,
                    error=f"No JSON in output: {stdout}",
                )

            payload = json.loads(stdout[idx:])
            tid = payload.get("template_id")
            updated = payload.get("updated", False)

            readback = cls.read_template(tid, site=site)

            return CRMPushResult(
                success=True,
                template_id=tid,
                post_title=title,
                updated=updated,
                site=site,
                readback_record=readback,
            )

        except Exception as exc:
            return CRMPushResult(
                success=False,
                template_id=None,
                post_title=title,
                updated=False,
                site=site,
                error=str(exc),
            )

    @classmethod
    def read_template(cls, template_id: int | None, site: str = "xinchaovi.com") -> dict[str, Any] | None:
        """Readback template from FluentCRM to confirm persistence."""
        if not template_id:
            return None
        script = cls.find_fluentcrm_ops_script()
        if not script:
            return None

        read_php = f"""
global $wpdb;
$post = $wpdb->get_row($wpdb->prepare(\"SELECT ID, post_title, post_status, post_modified FROM {{$wpdb->prefix}}posts WHERE ID = %d\", {template_id}), ARRAY_A);
if (!$post) {{
    return null;
}}
$post[\"_email_subject\"] = get_post_meta({template_id}, \"_email_subject\", true);
$post[\"_edit_type\"] = get_post_meta({template_id}, \"_edit_type\", true);
return $post;
"""
        cmd = [
            sys.executable,
            str(script),
            "--site",
            site,
            "php",
            read_php,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                stdout = res.stdout.strip()
                idx = stdout.find("{")
                if idx != -1:
                    return json.loads(stdout[idx:])
        except Exception:
            pass
        return None

    @classmethod
    def seed_standard_templates(
        cls,
        site: str = "xinchaovi.com",
        dry_run: bool = False,
    ) -> list[CRMPushResult]:
        """Seed both Learner and Tutor periodic digest templates into FluentCRM."""
        results = []

        learner_metrics = SSOTCalculator.derive_learner_metrics([], None, custom_granted=8)
        cfg_zh = DigestConfig(role=UserRole.LEARNER, language=Language.ZH)
        subject_zh, html_zh, _ = XinChaoViEmailRenderer.render_learner_email(learner_metrics, cfg_zh)
        res_learner = cls.push_template(
            title="[XinChaoVi] Preply 学习周报 - 学员进度与习惯追踪 (Learner Digest)",
            subject=subject_zh,
            html_content=html_zh,
            excerpt="本周学习进度回顾与里程碑解锁",
            site=site,
            dry_run=dry_run,
        )
        results.append(res_learner)

        tutor_metrics = SSOTCalculator.derive_tutor_metrics([], None)
        cfg_tutor = DigestConfig(role=UserRole.TUTOR, language=Language.ZH)
        subject_tutor, html_tutor, _ = XinChaoViEmailRenderer.render_tutor_email(tutor_metrics, cfg_tutor)
        res_tutor = cls.push_template(
            title="[XinChaoVi] Preply 教学周报 - 导师课时与教学成就 (Tutor Digest)",
            subject=subject_tutor,
            html_content=html_tutor,
            excerpt="本周教学里程碑回顾与新学员指引",
            site=site,
            dry_run=dry_run,
        )
        results.append(res_tutor)

        return results

"""HTML & Plaintext email renderer conforming to XinChaoVi design language.

Direct parity with https://xinchaovi.com/student:
- Brand colors: Terracotta (#E07A5F), Dark Slate (#1E293B), Sage (#81B29A), Amber (#F59E0B).
- Dark gradient Hero Card with progress track and milestone beads (with solid fallback).
- 3-column stats grid for instant comprehension (with mobile-responsive fluid scaling).
- Next Milestone Spotlight card with perk unlock framing.
- Upcoming sessions listing with topics and instructor attribution.
- Psychological motivation spark card.
- Bulletproof MSO conditionals and email-safe inline CSS for flawless cross-client rendering.
- Dark mode compatibility for iOS Mail, Apple Mail, and modern clients.
"""

from __future__ import annotations

from typing import Any

from .contracts import DigestConfig, Language, LearnerMetrics, TutorMetrics, UserRole
from .copywriter import PsychologicalCopywriter


class XinChaoViEmailRenderer:
    """Renders production-grade responsive emails matching the XinChaoVi design system."""

    BRAND_PRIMARY = "#E07A5F"
    BRAND_SECONDARY = "#3D405B"
    BRAND_DARK = "#1E293B"
    BRAND_LIGHT = "#F8FAFC"
    BRAND_CARD_BG = "#FFFFFF"
    BRAND_BORDER = "#E2E8F0"
    BRAND_TEXT_MAIN = "#0F172A"
    BRAND_TEXT_MUTED = "#64748B"
    BRAND_ACCENT = "#81B29A"
    BRAND_WARNING = "#F59E0B"

    @classmethod
    def _render_head_styles(cls) -> str:
        """Return standardized email reset, responsiveness, and dark-mode styles."""
        return """
<style type="text/css">
  /* Client resets */
  body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
  table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
  img { -ms-interpolation-mode: bicubic; border: 0; outline: none; text-decoration: none; }
  table { border-collapse: collapse !important; }
  body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; }

  /* Mobile responsiveness */
  @media only screen and (max-width: 620px) {
    .gm-outer-wrap { padding: 12px 6px !important; }
    .gm-container { width: 100% !important; max-width: 100% !important; border-radius: 12px !important; }
    .gm-header-pad { padding: 14px 16px !important; }
    .gm-inner-pad { padding: 16px 14px !important; }
    .gm-hero-pad { padding: 16px 14px !important; }
    .gm-hero-number { font-size: 34px !important; }
    .gm-stat-cell { padding: 8px 4px !important; }
    .gm-stat-num { font-size: 18px !important; }
    .gm-stat-lbl { font-size: 10px !important; }
    .gm-stat-sub { font-size: 9px !important; }
    .gm-btn-wrap { width: 100% !important; }
    .gm-btn { width: 100% !important; max-width: 100% !important; box-sizing: border-box !important; text-align: center !important; }
    .gm-session-card td { display: block !important; width: 100% !important; box-sizing: border-box !important; }
    .gm-session-action { text-align: left !important; margin-top: 8px !important; width: 100% !important; }
    .gm-session-action a { display: block !important; width: 100% !important; text-align: center !important; box-sizing: border-box !important; }
  }

  /* Dark mode overrides */
  @media (prefers-color-scheme: dark) {
    body, .gm-body-bg { background-color: #0F172A !important; }
    .gm-card-bg { background-color: #1E293B !important; border-color: #334155 !important; }
    .gm-text-main { color: #F8FAFC !important; }
    .gm-text-muted { color: #94A3B8 !important; }
    .gm-sub-bg { background-color: #0F172A !important; border-color: #334155 !important; }
    .gm-border-dark { border-color: #334155 !important; }
  }
</style>
"""

    @classmethod
    def render_learner_email(
        cls,
        metrics: LearnerMetrics,
        config: DigestConfig,
    ) -> tuple[str, str, str]:
        """Render (subject, html_body, plain_text) for a student/learner."""
        copy = PsychologicalCopywriter.craft_learner_copy(metrics, config.language)
        subject = copy["subject"]

        # Milestone beads HTML
        beads_html = ""
        total_beads = len(metrics.milestones) or 6
        for m in metrics.milestones:
            if m.unlocked:
                bg = cls.BRAND_PRIMARY
                border = "none"
            else:
                bg = "rgba(255, 255, 255, 0.2)"
                border = "1px dashed rgba(255, 255, 255, 0.4)"
            beads_html += (
                f'<td style="padding: 0 2px; width: {100 // total_beads}%;">'
                f'<div style="height: 8px; border-radius: 4px; background-color: {bg}; background: {bg}; border: {border};"></div>'
                f'</td>'
            )

        # Upcoming sessions HTML
        upcoming_items_html = ""
        if metrics.upcoming_sessions:
            for s in metrics.upcoming_sessions:
                upcoming_items_html += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-session-card" style="margin-bottom: 10px; background-color: #FAFAFA; border: 1px solid #E2E8F0; border-left: 4px solid {cls.BRAND_PRIMARY}; border-radius: 8px;">
                    <tr>
                        <td style="vertical-align: middle; padding: 12px 14px;">
                            <div style="font-size: 13px; font-weight: 700; color: #0F172A; margin-bottom: 4px;">📅 {s.datetime_str}</div>
                            <div style="font-size: 12px; color: #475569; margin-bottom: 2px;"><strong>Instructor:</strong> {s.partner_name} · <strong>Subject:</strong> {s.subject_name}</div>
                            <div style="font-size: 12px; color: #64748B;">{s.topic}</div>
                        </td>
                        <td align="right" valign="middle" class="gm-session-action" style="width: 110px; padding: 12px 14px 12px 0;">
                            <a href="{s.meet_url or config.portal_url}" style="display: inline-block; background-color: #FFFFFF; border: 1px solid #CBD5E1; color: #1E293B; font-size: 11px; font-weight: 700; padding: 7px 12px; border-radius: 6px; text-decoration: none; white-space: nowrap;">Join / View →</a>
                        </td>
                    </tr>
                </table>
                """
        else:
            if config.language == Language.ZH:
                empty_msg = f"暂无待上课时。你当前有 {metrics.available_balance} 节可用课时随时可预约！"
            elif config.language == Language.VI:
                empty_msg = f"Hiện chưa có lịch học nào. Bạn còn {metrics.available_balance} buổi học sẵn sàng đặt lịch!"
            else:
                empty_msg = f"No sessions currently scheduled. You have {metrics.available_balance} lesson credit(s) ready to book!"
            upcoming_items_html = f"""
            <div style="padding: 18px; text-align: center; background-color: #F8FAFC; border: 1.5px dashed #CBD5E1; border-radius: 8px; font-size: 13px; color: #64748B;">
                {empty_msg}
            </div>
            """

        progress_width = min(100, max(5, int(round(metrics.completion_rate_pct))))

        # HTML Email Payload with MSO & Bulletproof Email standards
        html = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no" />
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
<title>{subject}</title>
<!--[if mso]>
<noscript>
    <xml>
        <o:OfficeDocumentSettings>
            <o:PixelsPerInch>96</o:PixelsPerInch>
        </o:OfficeDocumentSettings>
    </xml>
</noscript>
<![endif]-->
{cls._render_head_styles()}
</head>
<body class="gm-body-bg" style="margin: 0; padding: 0; background-color: {cls.BRAND_LIGHT}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: {cls.BRAND_TEXT_MAIN};">
<div style="display: none; font-size: 1px; color: #fefefe; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden; mso-hide: all;">
  {copy['preheader']}
</div>

<!-- Outer Wrapper Table -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-outer-wrap" style="background-color: {cls.BRAND_LIGHT}; padding: 24px 12px;">
  <tr>
    <td align="center">
      <!--[if (gte mso 9)|(IE)]>
      <table width="620" align="center" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
      <![endif]-->

      <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-container gm-card-bg" style="max-width: 620px; background-color: {cls.BRAND_CARD_BG}; border-radius: 16px; overflow: hidden; border: 1px solid {cls.BRAND_BORDER}; box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.06);">
        
        <!-- Header Bar -->
        <tr>
          <td class="gm-header-pad" style="padding: 18px 24px; border-bottom: 1px solid {cls.BRAND_BORDER}; background-color: #FFFFFF;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="vertical-align: middle;">
                  <table cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="width: 38px; height: 38px; border-radius: 10px; background-color: {cls.BRAND_PRIMARY}; color: #FFFFFF; font-weight: 800; text-align: center; font-size: 19px; vertical-align: middle;">
                        V
                      </td>
                      <td style="padding-left: 12px; vertical-align: middle;">
                        <div style="font-size: 15px; font-weight: 800; color: {cls.BRAND_DARK}; letter-spacing: -0.2px;">XinChaoVi Learning Hub</div>
                        <div style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED};">Personalized Language Mastery</div>
                      </td>
                    </tr>
                  </table>
                </td>
                <td align="right" style="vertical-align: middle;">
                  <span style="display: inline-block; background-color: #ECFDF5; border: 1px solid #A7F3D0; color: #065F46; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.3px;">
                    ● ACTIVE MOMENTUM
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Main Body Container -->
        <tr>
          <td class="gm-inner-pad" style="padding: 24px;">
            
            <!-- Greeting & Hero Headline -->
            <div style="font-size: 11px; font-weight: 800; color: {cls.BRAND_PRIMARY}; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px;">{copy['greeting']}</div>
            <div style="font-size: 20px; font-weight: 800; color: {cls.BRAND_DARK}; letter-spacing: -0.3px; line-height: 1.35; margin-bottom: 16px;">{copy['hero_headline']}</div>

            <!-- Hero Progress Card (Dark Gradient with Solid Fallback) -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-hero-pad" style="background-color: #1E293B; background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border-radius: 14px; padding: 22px; color: #FFFFFF; margin-bottom: 16px;">
              <tr>
                <td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #CBD5E1; letter-spacing: 0.6px;">
                        CURRENT CYCLE PROGRESS
                      </td>
                      <td align="right">
                        <span style="background-color: rgba(224, 122, 95, 0.25); color: #FFAA8A; border: 1px solid rgba(224, 122, 95, 0.45); font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 12px;">
                          {metrics.completion_rate_pct}% COMPLETED
                        </span>
                      </td>
                    </tr>
                  </table>
                  
                  <div style="margin: 12px 0 14px 0;">
                    <span class="gm-hero-number" style="font-size: 42px; font-weight: 800; line-height: 1; letter-spacing: -1px; color: #FFFFFF;">{metrics.current_cycle_consumed}</span>
                    <span style="font-size: 15px; color: #CBD5E1; font-weight: 600;"> / {metrics.current_cycle_granted} Lessons Completed</span>
                  </div>

                  <!-- Progress Bar with Solid Fallback -->
                  <div style="height: 10px; background-color: rgba(255, 255, 255, 0.15); border-radius: 999px; overflow: hidden; margin-bottom: 12px;">
                    <div style="height: 100%; width: {progress_width}%; background-color: {cls.BRAND_PRIMARY}; background: linear-gradient(90deg, #E07A5F 0%, #F59E0B 100%); border-radius: 999px;"></div>
                  </div>

                  <div style="font-size: 11.5px; color: #CBD5E1; margin-top: 8px;">
                    Subscribed via Preply · Next Cycle Auto-Refill: <strong style="color: #FFFFFF;">{metrics.next_renewal_date or 'October 2026'}</strong>
                  </div>
                </td>
              </tr>
            </table>

            <!-- 3-Column Stats Grid (with mobile classes) -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-sub-bg" style="background-color: #F8FAFC; border: 1px solid {cls.BRAND_BORDER}; border-radius: 12px; margin-bottom: 16px;">
              <tr>
                <td align="center" class="gm-stat-cell" style="width: 33.3%; border-right: 1px solid {cls.BRAND_BORDER}; padding: 14px 8px;">
                  <div class="gm-stat-num" style="font-size: 22px; font-weight: 800; color: {cls.BRAND_DARK};">{metrics.total_completed_lessons}</div>
                  <div class="gm-stat-lbl" style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; font-weight: 600; margin-top: 2px;">{copy['stat_completed_label']}</div>
                  <div class="gm-stat-sub" style="font-size: 10px; color: #94A3B8;">({metrics.total_hours:.1f} Total Hrs)</div>
                </td>
                <td align="center" class="gm-stat-cell" style="width: 33.3%; border-right: 1px solid {cls.BRAND_BORDER}; padding: 14px 8px;">
                  <div class="gm-stat-num" style="font-size: 22px; font-weight: 800; color: {cls.BRAND_PRIMARY};">{metrics.available_balance}</div>
                  <div class="gm-stat-lbl" style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; font-weight: 600; margin-top: 2px;">{copy['stat_balance_label']}</div>
                  <div class="gm-stat-sub" style="font-size: 10px; color: #94A3B8;">(Ready to Book)</div>
                </td>
                <td align="center" class="gm-stat-cell" style="width: 33.3%; padding: 14px 8px;">
                  <div class="gm-stat-num" style="font-size: 22px; font-weight: 800; color: {cls.BRAND_DARK};">{copy['stat_streak_val']}</div>
                  <div class="gm-stat-lbl" style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; font-weight: 600; margin-top: 2px;">{copy['stat_streak_label']}</div>
                  <div class="gm-stat-sub" style="font-size: 10px; color: #94A3B8;">(Steady Habit)</div>
                </td>
              </tr>
            </table>

            <!-- Next Milestone Spotlight Card -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #FFFDF9; border: 1.5px solid #FCD34D; border-radius: 12px; margin-bottom: 16px;">
              <tr>
                <td style="padding: 16px;">
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="font-size: 11px; font-weight: 800; color: #92400E; letter-spacing: 0.2px; text-transform: uppercase;">
                        {copy['spotlight_tag']}
                      </td>
                      <td align="right">
                        <span style="background-color: #FFFFFF; border: 1px solid #FCD34D; color: #B45309; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 12px;">
                          {copy['spotlight_needed']}
                        </span>
                      </td>
                    </tr>
                  </table>
                  <div style="font-size: 15px; font-weight: 800; color: #78350F; margin: 8px 0 4px 0;">
                    🏅 {copy['spotlight_title']}
                  </div>
                  <div style="font-size: 12px; color: #92400E; line-height: 1.5;">
                    <strong style="color: #B45309;">{copy['spotlight_perk_label']}</strong> {copy['spotlight_perk']}
                  </div>
                </td>
              </tr>
            </table>

            <!-- Upcoming Sessions -->
            <div style="font-size: 14px; font-weight: 800; color: {cls.BRAND_DARK}; margin: 20px 0 10px 0;">
              {copy['upcoming_title']}
            </div>
            {upcoming_items_html}

            <!-- Motivation Spark (Human / Psychological Note) -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F8FAF9; border-left: 4px solid {cls.BRAND_ACCENT}; border-radius: 12px; padding: 16px; margin: 18px 0;">
              <tr>
                <td>
                  <div style="font-size: 13px; font-weight: 800; color: {cls.BRAND_DARK}; margin-bottom: 6px;">
                    {copy['motivation_title']}
                  </div>
                  <div style="font-size: 13px; color: #334155; line-height: 1.6;">
                    {copy['motivation_body']}
                  </div>
                </td>
              </tr>
            </table>

            <!-- Bulletproof Action Button CTA -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 22px;">
              <tr>
                <td align="center">
                  <!--[if mso]>
                  <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="{config.booking_url}" style="height:48px;v-text-anchor:middle;width:280px;" arcsize="18%" strokecolor="{cls.BRAND_PRIMARY}" fillcolor="{cls.BRAND_PRIMARY}">
                    <w:anchorlock/>
                    <center style="color:#ffffff;font-family:-apple-system,sans-serif;font-size:15px;font-weight:bold;">{copy['cta_label']}</center>
                  </v:roundrect>
                  <![endif]-->
                  <!--[if !mso]><!-->
                  <table border="0" cellspacing="0" cellpadding="0" class="gm-btn-wrap" style="margin: 0 auto;">
                    <tr>
                      <td align="center" style="border-radius: 10px; background-color: {cls.BRAND_PRIMARY}; box-shadow: 0 4px 14px rgba(224, 122, 95, 0.35);">
                        <a href="{config.booking_url}" target="_blank" class="gm-btn" style="font-size: 15px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #FFFFFF; text-decoration: none; border-radius: 10px; padding: 14px 28px; border: 1px solid {cls.BRAND_PRIMARY}; display: inline-block; font-weight: 800; letter-spacing: 0.2px;">
                          {copy['cta_label']}
                        </a>
                      </td>
                    </tr>
                  </table>
                  <!--<![endif]-->
                </td>
              </tr>
            </table>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td class="gm-footer" style="padding: 20px 24px; background-color: #F8FAFC; border-top: 1px solid {cls.BRAND_BORDER}; text-align: center; font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; line-height: 1.6;">
            <div>XinChaoVi Student Transparency Portal · Real-time Single Source of Truth</div>
            <div style="margin-top: 4px;">{copy['footer_help']}</div>
            <div style="margin-top: 10px; color: #94A3B8;">
              <a href="{config.portal_url}" style="color: {cls.BRAND_PRIMARY}; text-decoration: none; font-weight: 600;">Student Portal</a> · 
              <a href="{config.portal_url}?action=history" style="color: {cls.BRAND_PRIMARY}; text-decoration: none; font-weight: 600;">Class Ledger</a> · 
              <a href="{config.portal_url}#notion" style="color: {cls.BRAND_PRIMARY}; text-decoration: none; font-weight: 600;">Notion Hub</a>
            </div>
          </td>
        </tr>

      </table>

      <!--[if (gte mso 9)|(IE)]>
          </td>
        </tr>
      </table>
      <![endif]-->
    </td>
  </tr>
</table>
</body>
</html>
"""

        # Plain Text Fallback
        text = f"""====================================================
XinChaoVi Learning Hub — {subject}
====================================================

{copy['greeting']}

{copy['hero_headline']}
{copy['hero_subheadline']}

--- CURRENT PROGRESS ---
- Total Completed: {metrics.total_completed_lessons} lessons ({metrics.total_hours:.1f} hours)
- This Cycle: {metrics.current_cycle_consumed} / {metrics.current_cycle_granted} completed ({metrics.completion_rate_pct}%)
- Ready to Schedule: {metrics.available_balance} lesson(s)
- Learning Streak: {metrics.current_streak_weeks} weeks
- Next Refill Date: {metrics.next_renewal_date or 'October 2026'}

--- NEXT MILESTONE UNLOCK ---
Badge: {copy['spotlight_title']}
Status: {copy['spotlight_needed']}
Perk: {copy['spotlight_perk']}

--- MOTIVATION SPARK ---
{copy['motivation_body']}

--- ACTION ---
Schedule your next conversation:
{config.booking_url}

Transparency Portal:
{config.portal_url}

XinChaoVi Learning Hub · support@example.com
"""

        return subject, html, text

    @classmethod
    def render_tutor_email(
        cls,
        metrics: TutorMetrics,
        config: DigestConfig,
    ) -> tuple[str, str, str]:
        """Render (subject, html_body, plain_text) for a tutor/mentor."""
        copy = PsychologicalCopywriter.craft_tutor_copy(metrics, config.language)
        subject = copy["subject"]

        # Tutor honor beads
        beads_html = ""
        tutor_milestones = metrics.milestones or []
        total_beads = len(tutor_milestones) or 5
        for m in tutor_milestones:
            if m.unlocked:
                bg = cls.BRAND_ACCENT
                border = "none"
            else:
                bg = "rgba(255, 255, 255, 0.2)"
                border = "1px dashed rgba(255, 255, 255, 0.4)"
            beads_html += (
                f'<td style="padding: 0 2px; width: {100 // total_beads}%;">'
                f'<div style="height: 8px; border-radius: 4px; background-color: {bg}; background: {bg}; border: {border};"></div>'
                f'</td>'
            )

        # Upcoming sessions
        upcoming_items_html = ""
        if metrics.upcoming_sessions:
            for s in metrics.upcoming_sessions:
                upcoming_items_html += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-session-card" style="margin-bottom: 10px; background-color: #FAFAFA; border: 1px solid #E2E8F0; border-left: 4px solid {cls.BRAND_ACCENT}; border-radius: 8px; padding: 12px 14px;">
                    <tr>
                        <td style="vertical-align: middle;">
                            <div style="font-size: 13px; font-weight: 700; color: #0F172A; margin-bottom: 4px;">📅 {s.datetime_str}</div>
                            <div style="font-size: 12px; color: #475569;"><strong>Student:</strong> {s.partner_name} · 1-on-1 Class</div>
                        </td>
                        <td align="right" valign="middle" class="gm-session-action" style="width: 125px; padding-left: 10px;">
                            <a href="{config.portal_url}" style="display: inline-block; background-color: #FFFFFF; border: 1px solid #CBD5E1; color: #1E293B; font-size: 11px; font-weight: 700; padding: 7px 12px; border-radius: 6px; text-decoration: none; white-space: nowrap;">View Classroom →</a>
                        </td>
                    </tr>
                </table>
                """
        else:
            if config.language == Language.ZH:
                empty_tutor_msg = "暂无待上课时。建议在导师工作台开放更多空闲时间段，让学员随时预约！"
            elif config.language == Language.VI:
                empty_tutor_msg = "Hôm nay chưa có lịch dạy. Thầy/Cô hãy mở thêm khung giờ trống để học viên đặt lịch nhé!"
            else:
                empty_tutor_msg = "No teaching sessions scheduled today. Open open time slots to let students book!"
            upcoming_items_html = f"""
            <div style="padding: 18px; text-align: center; background-color: #F8FAFC; border: 1.5px dashed #CBD5E1; border-radius: 8px; font-size: 13px; color: #64748B;">
                {empty_tutor_msg}
            </div>
            """

        revenue_display = f"${metrics.total_revenue_usd:,.2f}" if metrics.total_revenue_usd else "Active"

        html = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta name="x-apple-disable-message-reformatting" />
<meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no" />
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
<title>{subject}</title>
<!--[if mso]>
<noscript>
    <xml>
        <o:OfficeDocumentSettings>
            <o:PixelsPerInch>96</o:PixelsPerInch>
        </o:OfficeDocumentSettings>
    </xml>
</noscript>
<![endif]-->
{cls._render_head_styles()}
</head>
<body class="gm-body-bg" style="margin: 0; padding: 0; background-color: {cls.BRAND_LIGHT}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased; color: {cls.BRAND_TEXT_MAIN};">
<div style="display: none; font-size: 1px; color: #fefefe; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden; mso-hide: all;">
  {copy['preheader']}
</div>

<!-- Outer Wrapper Table -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-outer-wrap" style="background-color: {cls.BRAND_LIGHT}; padding: 24px 12px;">
  <tr>
    <td align="center">
      <!--[if (gte mso 9)|(IE)]>
      <table width="620" align="center" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td>
      <![endif]-->

      <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-container gm-card-bg" style="max-width: 620px; background-color: {cls.BRAND_CARD_BG}; border-radius: 16px; overflow: hidden; border: 1px solid {cls.BRAND_BORDER}; box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.06);">
        
        <!-- Header -->
        <tr>
          <td class="gm-header-pad" style="padding: 18px 24px; border-bottom: 1px solid {cls.BRAND_BORDER}; background-color: #FFFFFF;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="vertical-align: middle;">
                  <table cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="width: 38px; height: 38px; border-radius: 10px; background-color: {cls.BRAND_ACCENT}; color: #FFFFFF; font-weight: 800; text-align: center; font-size: 19px; vertical-align: middle;">
                        V
                      </td>
                      <td style="padding-left: 12px; vertical-align: middle;">
                        <div style="font-size: 15px; font-weight: 800; color: {cls.BRAND_DARK}; letter-spacing: -0.2px;">XinChaoVi Educator Hub</div>
                        <div style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED};">Personalized Mentorship Network</div>
                      </td>
                    </tr>
                  </table>
                </td>
                <td align="right" style="vertical-align: middle;">
                  <span style="display: inline-block; background-color: #ECFDF5; border: 1px solid #A7F3D0; color: #065F46; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.3px;">
                    ● CERTIFIED MENTOR
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Main Body -->
        <tr>
          <td class="gm-inner-pad" style="padding: 24px;">
            <div style="font-size: 11px; font-weight: 800; color: {cls.BRAND_ACCENT}; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px;">{copy['greeting']}</div>
            <div style="font-size: 20px; font-weight: 800; color: {cls.BRAND_DARK}; line-height: 1.35; margin-bottom: 16px;">{copy['hero_headline']}</div>

            <!-- Hero Teaching Card (Dark Gradient with Solid Fallback) -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-hero-pad" style="background-color: #1E293B; background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%); border-radius: 14px; padding: 22px; color: #FFFFFF; margin-bottom: 16px;">
              <tr>
                <td>
                  <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #94A3B8; letter-spacing: 0.6px;">LIFETIME MENTORSHIP IMPACT</div>
                  <div style="margin: 10px 0;">
                    <span class="gm-hero-number" style="font-size: 44px; font-weight: 800; color: #FFFFFF; line-height: 1;">{metrics.total_lessons_taught}</span>
                    <span style="font-size: 16px; color: #CBD5E1; font-weight: 600;"> Confirmed Lessons Taught</span>
                  </div>

                  <!-- Honor Beads -->
                  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 10px 0;">
                    <tr>
                      {beads_html}
                    </tr>
                  </table>

                  <div style="font-size: 12px; color: #94A3B8; margin-top: 6px;">
                    Lifetime Mentorship Impact: <strong style="color: #10B981;">{revenue_display}</strong> · Active Students: <strong>{metrics.active_students_count}</strong>
                  </div>
                </td>
              </tr>
            </table>

            <!-- 3-Column Stats Grid -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" class="gm-sub-bg" style="background-color: #F8FAFC; border: 1px solid {cls.BRAND_BORDER}; border-radius: 12px; margin-bottom: 16px; padding: 12px 0;">
              <tr>
                <td align="center" class="gm-stat-cell" style="width: 33.3%; border-right: 1px solid {cls.BRAND_BORDER};">
                  <div class="gm-stat-num" style="font-size: 22px; font-weight: 800; color: {cls.BRAND_DARK};">{metrics.total_lessons_taught}</div>
                  <div class="gm-stat-lbl" style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; font-weight: 600; margin-top: 2px;">{copy['stat_completed_label']}</div>
                </td>
                <td align="center" class="gm-stat-cell" style="width: 33.3%; border-right: 1px solid {cls.BRAND_BORDER};">
                  <div class="gm-stat-num" style="font-size: 22px; font-weight: 800; color: {cls.BRAND_PRIMARY};">{metrics.active_students_count}</div>
                  <div class="gm-stat-lbl" style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; font-weight: 600; margin-top: 2px;">{copy['stat_balance_label']}</div>
                </td>
                <td align="center" class="gm-stat-cell" style="width: 33.3%;">
                  <div class="gm-stat-num" style="font-size: 22px; font-weight: 800; color: #10B981;">{copy['stat_streak_val']}</div>
                  <div class="gm-stat-lbl" style="font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; font-weight: 600; margin-top: 2px;">{copy['stat_streak_label']}</div>
                </td>
              </tr>
            </table>

            <!-- Next Honor Badge -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F0FDF4; border: 1.5px solid #BBF7D0; border-radius: 12px; padding: 16px; margin-bottom: 16px;">
              <tr>
                <td>
                  <div style="font-size: 10px; font-weight: 800; color: #166534; text-transform: uppercase;">{copy['spotlight_tag']}</div>
                  <div style="font-size: 16px; font-weight: 800; color: {cls.BRAND_DARK}; margin: 6px 0;">🏆 {copy['spotlight_title']}</div>
                  <div style="font-size: 12px; color: #374151; line-height: 1.5;"><strong style="color: #166534;">{copy['spotlight_perk_label']}</strong> {copy['spotlight_perk']} ({copy['spotlight_needed']})</div>
                </td>
              </tr>
            </table>

            <!-- Upcoming Sessions -->
            <div style="font-size: 14px; font-weight: 800; color: {cls.BRAND_DARK}; margin: 18px 0 10px 0;">{copy['upcoming_title']}</div>
            {upcoming_items_html}

            <!-- Educator Note -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F8FAF9; border-left: 4px solid {cls.BRAND_ACCENT}; border-radius: 12px; padding: 16px; margin: 18px 0;">
              <tr>
                <td>
                  <div style="font-size: 13px; font-weight: 800; color: {cls.BRAND_DARK}; margin-bottom: 6px;">{copy['motivation_title']}</div>
                  <div style="font-size: 13px; color: #334155; line-height: 1.6;">{copy['motivation_body']}</div>
                </td>
              </tr>
            </table>

            <!-- Bulletproof CTA -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px;">
              <tr>
                <td align="center">
                  <!--[if mso]>
                  <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="{config.portal_url}" style="height:48px;v-text-anchor:middle;width:280px;" arcsize="18%" strokecolor="{cls.BRAND_SECONDARY}" fillcolor="{cls.BRAND_SECONDARY}">
                    <w:anchorlock/>
                    <center style="color:#ffffff;font-family:-apple-system,sans-serif;font-size:15px;font-weight:bold;">{copy['cta_label']}</center>
                  </v:roundrect>
                  <![endif]-->
                  <!--[if !mso]><!-->
                  <table border="0" cellspacing="0" cellpadding="0" class="gm-btn-wrap" style="margin: 0 auto;">
                    <tr>
                      <td align="center" style="border-radius: 10px; background-color: {cls.BRAND_SECONDARY}; box-shadow: 0 4px 14px rgba(61, 64, 91, 0.35);">
                        <a href="{config.portal_url}" target="_blank" class="gm-btn" style="font-size: 15px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #FFFFFF; text-decoration: none; border-radius: 10px; padding: 14px 28px; border: 1px solid {cls.BRAND_SECONDARY}; display: inline-block; font-weight: 800; letter-spacing: 0.2px;">
                          {copy['cta_label']}
                        </a>
                      </td>
                    </tr>
                  </table>
                  <!--<![endif]-->
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td class="gm-footer" style="padding: 18px 24px; background-color: #F8FAFC; border-top: 1px solid {cls.BRAND_BORDER}; text-align: center; font-size: 11px; color: {cls.BRAND_TEXT_MUTED}; line-height: 1.6;">
            <div>XinChaoVi Educator Network · Preply Verified Partner</div>
            <div style="margin-top: 4px;">{copy['footer_help']}</div>
            <div style="margin-top: 10px; color: #94A3B8;">
              <a href="{config.portal_url}" style="color: {cls.BRAND_PRIMARY}; text-decoration: none; font-weight: 600;">Educator Hub</a> · 
              <a href="{config.portal_url}#schedule" style="color: {cls.BRAND_PRIMARY}; text-decoration: none; font-weight: 600;">Classroom Calendar</a> · 
              <a href="{config.portal_url}#resources" style="color: {cls.BRAND_PRIMARY}; text-decoration: none; font-weight: 600;">Teaching Materials</a>
            </div>
          </td>
        </tr>
      </table>

      <!--[if (gte mso 9)|(IE)]>
          </td>
        </tr>
      </table>
      <![endif]-->
    </td>
  </tr>
</table>
</body>
</html>
"""

        text = f"""====================================================
XinChaoVi Educator Hub — {subject}
====================================================

{copy['greeting']}

{copy['hero_headline']}
{copy['hero_subheadline']}

--- MENTORSHIP & TEACHING STATS ---
- Total Lessons Delivered: {metrics.total_lessons_taught}
- Active Learners Mentored: {metrics.active_students_count}
- Booking Inquiries: {metrics.booking_attempts_count}
- Earnings: {revenue_display}

--- EDUCATOR HONOR MILESTONE ---
- Title: {copy['spotlight_title']}
- Status: {copy['spotlight_needed']}
- Perk: {copy['spotlight_perk']}

--- EDUCATOR'S REFLECTION ---
{copy['motivation_body']}

Tutor Hub & Availability:
{config.portal_url}
"""

        return subject, html, text

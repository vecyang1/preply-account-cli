"""Preply Periodic Email System Package.

Provides:
- Email scanning & classification from Spark Desktop / local caches.
- Single Source of Truth metrics derivation (balances, completion rates, streaks).
- Psychological copywriting ("说人话，不要说实话").
- XinChaoVi design system HTML & plaintext rendering.
- Spark draft dispatch and browser preview auditing.
"""

from .calculator import (
    SSOTCalculator,
    get_default_learner_milestones,
    get_default_tutor_milestones,
)
from .contracts import (
    CadenceType,
    DigestConfig,
    DigestResult,
    DigestRunResult,
    EmailCategory,
    EmailRecord,
    Language,
    LearnerMetrics,
    Milestone,
    TutorMetrics,
    UpcomingSession,
    UserRole,
)
from .copywriter import PsychologicalCopywriter
from .crm_sync import CRMPushResult, FluentCRMSync
from .drafter import EmailDrafter
from .renderer import XinChaoViEmailRenderer
from .scanner import PreplyEmailScanner
from .scheduler import DigestAutomationRunner

__all__ = [
    "CRMPushResult",
    "CadenceType",
    "DigestAutomationRunner",
    "DigestConfig",
    "DigestResult",
    "DigestRunResult",
    "EmailCategory",
    "EmailDrafter",
    "EmailRecord",
    "FluentCRMSync",
    "Language",
    "LearnerMetrics",
    "Milestone",
    "PreplyEmailScanner",
    "PsychologicalCopywriter",
    "SSOTCalculator",
    "TutorMetrics",
    "UpcomingSession",
    "UserRole",
    "XinChaoViEmailRenderer",
    "get_default_learner_milestones",
    "get_default_tutor_milestones",
]

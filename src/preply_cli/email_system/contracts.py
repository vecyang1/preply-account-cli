"""Contracts and strongly-typed data structures for the Preply periodic email system.

Adheres strictly to the Single Source of Truth (SSOT) philosophy:
- Raw email events & ledger entries are truth.
- Metrics, milestone badges, and completion rates are strictly derived, never stored.
- Schema definitions serve as the contract for both CLI and rendering engines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class UserRole(str, Enum):
    """Role of the user in the learning interaction."""
    LEARNER = "learner"
    TUTOR = "tutor"
    BOTH = "both"


class EmailCategory(str, Enum):
    """Categorized Preply email event types."""
    LESSON_COMPLETED = "lesson_completed"
    LESSON_UPCOMING = "lesson_upcoming"
    LESSON_SCHEDULED = "lesson_scheduled"
    LESSON_RESCHEDULED = "lesson_rescheduled"
    LESSON_CANCELLED = "lesson_cancelled"
    LESSON_CONFIRM_REQUEST = "lesson_confirm_request"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    SUBSCRIPTION_PAUSED = "subscription_paused"
    SUBSCRIPTION_DOWNGRADED = "subscription_downgraded"
    MONTHLY_HOURS_DEPLETED = "monthly_hours_depleted"
    STREAK_PROGRESS = "streak_progress"
    TUTOR_MESSAGE = "tutor_message"
    TUTOR_BOOKING_ATTEMPT = "tutor_booking_attempt"
    TUTOR_PAYOUT = "tutor_payout"
    TUTOR_CELEBRATION = "tutor_celebration"
    GENERAL_NOTIFICATION = "general_notification"


class CadenceType(str, Enum):
    """Cadence for the recurring email system."""
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class Language(str, Enum):
    """Supported display languages."""
    EN = "en"
    ZH = "zh-CN"
    VI = "vi"


@dataclass
class EmailRecord:
    """A single normalized email record extracted from mailbox."""
    message_id: int
    account: str
    sender: str
    date: str
    subject: str
    category: EmailCategory
    role: UserRole
    tutor_name: Optional[str] = None
    student_name: Optional[str] = None
    subject_name: Optional[str] = None
    lesson_datetime: Optional[str] = None
    lessons_count: Optional[int] = None
    price_str: Optional[str] = None
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmailRecord:
        data = dict(data)
        if isinstance(data.get("category"), str):
            data["category"] = EmailCategory(data["category"])
        if isinstance(data.get("role"), str):
            data["role"] = UserRole(data["role"])
        return cls(**data)


@dataclass
class UpcomingSession:
    """A scheduled or upcoming lesson session."""
    session_id: str
    datetime_str: str
    partner_name: str
    subject_name: str
    topic: str = "1-on-1 Personalized Session"
    meet_url: Optional[str] = None
    is_first_lesson: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Milestone:
    """A learning milestone badge."""
    key: str
    title: str
    description: str
    perk: str
    required_count: int
    unlocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearnerMetrics:
    """Derived single source of truth metrics for a student."""
    total_completed_lessons: int
    total_hours: float
    current_cycle_granted: int
    current_cycle_consumed: int
    current_cycle_scheduled: int
    available_balance: int
    completion_rate_pct: float
    current_streak_weeks: int
    next_renewal_date: Optional[str]
    is_paused: bool
    upcoming_sessions: list[UpcomingSession] = field(default_factory=list)
    tutor_breakdown: dict[str, int] = field(default_factory=dict)
    subject_breakdown: dict[str, float] = field(default_factory=dict)
    milestones: list[Milestone] = field(default_factory=list)
    next_milestone: Optional[Milestone] = None
    classes_needed_for_next: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["upcoming_sessions"] = [s.to_dict() for s in self.upcoming_sessions]
        d["milestones"] = [m.to_dict() for m in self.milestones]
        d["next_milestone"] = self.next_milestone.to_dict() if self.next_milestone else None
        return d


@dataclass
class TutorMetrics:
    """Derived single source of truth metrics for a tutor."""
    total_lessons_taught: int
    active_students_count: int
    student_names: list[str]
    booking_attempts_count: int
    payout_events_count: int
    current_streak_weeks: int
    upcoming_sessions: list[UpcomingSession] = field(default_factory=list)
    student_lesson_breakdown: dict[str, int] = field(default_factory=dict)
    total_revenue_usd: Optional[float] = None
    milestones: list[Milestone] = field(default_factory=list)
    next_milestone: Optional[Milestone] = None
    classes_needed_for_next: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["upcoming_sessions"] = [s.to_dict() for s in self.upcoming_sessions]
        d["milestones"] = [m.to_dict() for m in self.milestones]
        d["next_milestone"] = self.next_milestone.to_dict() if self.next_milestone else None
        return d


@dataclass
class DigestConfig:
    """Configuration for periodic email generation."""
    cadence: CadenceType = CadenceType.WEEKLY
    role: UserRole = UserRole.LEARNER
    recipient_name: str = "Learner"
    recipient_email: str = "student@example.com"
    sender_name: str = "XinChaoVi Learning Hub"
    sender_email: str = "support@xinchaovi.com"
    portal_url: str = "https://xinchaovi.com/student/"
    booking_url: str = "https://xinchaovi.com/student/"
    language: Language = Language.EN
    custom_quote: Optional[str] = None
    include_booking_cta: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cadence"] = self.cadence.value
        d["role"] = self.role.value
        d["language"] = self.language.value
        return d


@dataclass
class DigestResult:
    """Output of email generation."""
    subject: str
    html_content: str
    text_content: str
    role: UserRole
    recipient_email: str
    metrics_summary: dict[str, Any]
    preview_file_path: Optional[str] = None
    spark_draft_id: Optional[str] = None
    spark_deep_link: Optional[str] = None


@dataclass
class DigestRunResult:
    """Outcome of an automated periodic digest execution."""
    timestamp: str
    role: UserRole
    language: Language
    subject: str
    recipient: str
    generated_html_path: Optional[str] = None
    generated_text_path: Optional[str] = None
    spark_draft_id: Optional[str] = None
    crm_template_id: Optional[int] = None
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        d["language"] = self.language.value
        return d


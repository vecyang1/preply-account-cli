"""Turn Preply payloads into decision-shaped rows and summaries.

Split by whose data is being read, because that is the axis along which the
shapes are *verified*: learner views are checked against a live learner account,
tutor views cannot be (no tutor session exists).

Every summary builder returns a ``warnings: list[str]``. The CLI prints those to
stderr, so `--json` and `--csv` pipes stay clean while a human still sees that a
total is a floor rather than a fact. The recurring bug this guards against is
"absent is not zero": Preply moves a field, the response stays GraphQL-valid,
and `.get(x) or 0` turns the absence into a confident wrong number.

Re-exported flat, so the module's public surface is unchanged by the split.
"""

from __future__ import annotations

from ._common import (
    NO_SUBSCRIPTION,
    UNKNOWN,
    UNREADABLE_DATE,
    _absolute_preply_url,
    _dict_nodes,
    _number,
    _opt_int,
    _opt_number,
    _sum_or_unknown,
    balance_nodes,
    student_nodes,
)
from .chat_views import (
    SENDER_ME,
    SENDER_SYSTEM,
    SENDER_UNKNOWN,
    _file_entries,
    _message_sender,
    build_chat_summary,
    chat_context,
    chat_file_rows,
    chat_message_nodes,
    chat_rows,
)
from .learner_views import (
    STOPPED,
    _client_block,
    _is_upcoming,
    balance_rows,
    build_balance_summary,
    build_certificate_summary,
    build_lesson_summary,
    build_payment_summary,
    build_renewal_summary,
    certificate_rows,
    learner_lifetime_stats,
    learner_subscription_state,
    learner_wallet_context,
    lesson_nodes,
    lesson_rows,
    payment_nodes,
    pending_payment_rows,
    renewal_nodes,
    renewal_rows,
    tutoring_nodes,
    tutoring_rows,
    unread_message_count,
    upcoming_lesson_nodes,
    upcoming_rows,
)
from .tutor_views import build_account_summary, build_timeline

__all__ = [
    "NO_SUBSCRIPTION",
    "SENDER_ME",
    "SENDER_SYSTEM",
    "SENDER_UNKNOWN",
    "STOPPED",
    "UNKNOWN",
    "UNREADABLE_DATE",
    "balance_nodes",
    "balance_rows",
    "build_account_summary",
    "build_balance_summary",
    "build_certificate_summary",
    "build_chat_summary",
    "build_lesson_summary",
    "build_payment_summary",
    "build_renewal_summary",
    "build_timeline",
    "certificate_rows",
    "chat_context",
    "chat_file_rows",
    "chat_message_nodes",
    "chat_rows",
    "learner_lifetime_stats",
    "learner_subscription_state",
    "learner_wallet_context",
    "lesson_nodes",
    "lesson_rows",
    "payment_nodes",
    "pending_payment_rows",
    "renewal_nodes",
    "renewal_rows",
    "student_nodes",
    "tutoring_nodes",
    "tutoring_rows",
    "unread_message_count",
    "upcoming_lesson_nodes",
    "upcoming_rows",
]

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .browser import BrowserHarnessClient, BrowserTargetSelector, OperationCall
from .queries import get_operation


def _warn(data: dict[str, Any], message: str) -> None:
    """Attach a transport-level warning for the CLI to surface.

    Collected under ``_warnings`` alongside the operation keys, mirroring how
    ``_account`` rides along. Used when a pagination contract could not be read,
    which must never be reported to the user as "everything was fetched".
    """
    data.setdefault("_warnings", []).append(message)


def _report_more(has_next: bool, unknown: bool, fetched: int, limit: int) -> bool:
    """What to report back as "more data exists".

    ``unknown`` wins outright and is deliberately NOT gated on ``fetched >=
    limit``. Gating it was the bug: with a default limit of 50 and a page size
    of 20, an unreadable flag produced ``(False or True) and (20 >= 50)`` ==
    False — the exact confident "nothing more" this is supposed to prevent.
    Not knowing whether more exists is reported as "more may exist".
    """
    if unknown:
        return True
    return has_next and fetched >= limit


def _continues(connection: dict[str, Any], field: str = "hasNext") -> tuple[bool, bool]:
    """Read a pagination continuation flag as (should_continue, is_unknown).

    ``bool(None)`` is False, which would turn a renamed flag into a confident
    "no more pages". An absent flag is unknown, not finished.
    """
    if field not in connection or connection[field] is None:
        return False, True
    return bool(connection[field]), False


class PreplyClient:
    student_page_size = 20
    # Ceiling on follow-up student pages when totalCount is unreadable. Without
    # it the page count follows --limit, which argparse does not bound: a
    # `students --limit 100000` against a drifted field built 4999 aliased
    # sub-operations into a single live request.
    max_unknown_total_pages = 25

    def __init__(
        self,
        browser: BrowserHarnessClient | None = None,
        selector: BrowserTargetSelector | None = None,
    ):
        self.browser = browser or BrowserHarnessClient(selector=selector)

    def _fetch(self, calls: list[OperationCall]) -> dict[str, Any]:
        return self.browser.fetch_graphql(calls)

    def overview(self, limit: int = 100) -> dict[str, Any]:
        data = self._fetch(
            [
                OperationCall("account", get_operation("PreplyCliAccountIdentity"), {}),
                OperationCall("timezone", get_operation("Timezone"), {}),
                OperationCall("wallet", get_operation("TutorWallet"), {}),
                OperationCall(
                    "profile",
                    get_operation("PreplyCliStudentList"),
                    {"offset": 0, "count": min(limit, self.student_page_size), "smartFilter": None},
                ),
                OperationCall("messages", get_operation("ChatThreadSummaries"), {}),
            ]
        )
        self._extend_student_pages(data, limit=limit)
        return data

    def students(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        data = self._fetch(
            [
                OperationCall(
                    "profile",
                    get_operation("PreplyCliStudentList"),
                    {"offset": offset, "count": min(limit, self.student_page_size), "smartFilter": None},
                )
            ]
        )
        self._extend_student_pages(data, limit=limit, initial_offset=offset)
        return data

    def _student_connection(self, data: dict[str, Any]) -> dict[str, Any]:
        tutor = (
            data.get("profile", {})
            .get("currentUser", {})
            .get("tutor")
        )
        return (tutor or {}).get("studentManagementTutorings", {})

    def _extend_student_pages(self, data: dict[str, Any], limit: int, initial_offset: int = 0) -> None:
        connection = self._student_connection(data)
        if not connection:
            # No tutor block at all - a learner account has no student list.
            # Warning here would fire on every learner run and train the user to
            # ignore the channel, which is how a real warning gets missed.
            return
        nodes = connection.get("nodes") or []
        raw_total = connection.get("totalCount")
        if raw_total is None and not nodes:
            return  # nothing loaded and nothing claimed; no total to mis-report
        if raw_total is None:
            # Falling back to len(nodes) would make target_count equal the first
            # page, stop pagination immediately, and report that page as the
            # whole account. Page on instead - but bounded: this builds every
            # follow-up call and sends them as ONE aliased request, so deriving
            # the page count from an unbounded --limit turned a drifted field
            # into thousands of sub-operations in a single call.
            _warn(
                data,
                "Student totalCount could not be read; the loaded student count "
                "may be incomplete and account totals derived from it are a floor.",
            )
            total = min(limit, self.student_page_size * self.max_unknown_total_pages)
            total += initial_offset
        else:
            total = int(raw_total)
        target_count = min(limit, max(0, total - initial_offset))
        if len(nodes) >= target_count:
            return
        calls = []
        next_offset = initial_offset + len(nodes)
        while next_offset < initial_offset + target_count:
            count = min(self.student_page_size, initial_offset + target_count - next_offset)
            calls.append(
                OperationCall(
                    f"profile_page_{next_offset}",
                    get_operation("PreplyCliStudentList"),
                    {"offset": next_offset, "count": count, "smartFilter": None},
                )
            )
            next_offset += count
        if not calls:
            return
        extra = self._fetch(calls)
        # One request carries many aliased sub-operations; a partial response is
        # a silent under-fetch that would otherwise be reported as the account.
        missing = {call.key for call in calls} - set(extra)
        if missing:
            _warn(
                data,
                f"{len(missing)} of {len(calls)} student page(s) did not come back; "
                "the student list is incomplete.",
            )
        merged = list(nodes)
        for key in sorted(extra):
            page_nodes = self._student_connection({"profile": extra[key]}).get("nodes") or []
            merged.extend(page_nodes)
        connection["nodes"] = merged[:target_count]

    def wallet(self) -> dict[str, Any]:
        return self._fetch([OperationCall("wallet", get_operation("TutorWallet"), {})])

    def account(self) -> dict[str, Any]:
        return self._fetch([OperationCall("account", get_operation("PreplyCliAccountIdentity"), {})])

    def next_lesson_confirmation(self) -> dict[str, Any]:
        return self._fetch([OperationCall("confirmation", get_operation("NextLessonForConfirmation"), {})])

    def confirm_lesson(self, lesson_id: int) -> dict[str, Any]:
        return self._fetch(
            [
                OperationCall(
                    "confirm",
                    get_operation("ConfirmPastLesson"),
                    {"lessonId": lesson_id},
                )
            ]
        )

    def messages(self) -> dict[str, Any]:
        return self._fetch([OperationCall("messages", get_operation("ChatThreadSummaries"), {})])

    def schedule(self, days: int = 14, tzname: str | None = None) -> dict[str, Any]:
        timezone = tzname or self.timezone()
        start = date.today()
        end = start + timedelta(days=days)
        return self._fetch(
            [
                OperationCall(
                    "schedule",
                    get_operation("TutorHomeUpcomingLessons"),
                    {
                        "dateStart": start.isoformat(),
                        "dateEnd": end.isoformat(),
                        "tzname": timezone,
                    },
                )
            ]
        )

    def timezone(self) -> str:
        data = self._fetch([OperationCall("timezone", get_operation("Timezone"), {})])
        tzname = (
            data.get("timezone", {})
            .get("currentUser", {})
            .get("profile", {})
            .get("timezone", {})
            .get("tzname")
        )
        return tzname or "UTC"

    def student_detail(
        self,
        tutoring_id: int,
        past_limit: int = 20,
        include_insights_for_lesson_id: int | None = None,
    ) -> dict[str, Any]:
        calls = [
            OperationCall("details", get_operation("TutorStudentDetails"), {"tutoringId": tutoring_id}),
            OperationCall(
                "statistics",
                get_operation("TutoringStatistics"),
                {"tutoringId": tutoring_id, "cyclesCount": 3},
            ),
            OperationCall(
                "upcomingLessons",
                get_operation("TutorStudentUpcomingLessons"),
                {"tutoringId": tutoring_id},
            ),
            OperationCall(
                "pastLessons",
                get_operation("TutorStudentsPastLessons"),
                {"tutoringId": tutoring_id, "offset": 0, "limit": past_limit, "status": None},
            ),
            OperationCall(
                "revenueHistory",
                get_operation("StudentManagementRevenueHistory"),
                {"tutoringId": tutoring_id},
            ),
        ]
        if include_insights_for_lesson_id:
            calls.append(
                OperationCall(
                    "lessonInsights",
                    get_operation("LessonInsights"),
                    {"lessonId": include_insights_for_lesson_id},
                )
            )
        return self._fetch(calls)

    def learner_lessons(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Learner-side completed-lesson ledger via CurrentUserPastLessons.

        Paginates on ``hasNext`` in pages of ``student_page_size`` and merges the
        nodes back under the operation key so downstream row extraction sees a
        single list.
        """
        page_size = self.student_page_size
        data = self._fetch(
            [
                OperationCall(
                    "lessons",
                    get_operation("CurrentUserPastLessons"),
                    {
                        "offset": offset,
                        "limit": min(limit, page_size),
                        "excludeUnconfirmedLessons": False,
                    },
                )
            ]
        )
        connection = (
            (((data.get("lessons") or {}).get("currentUser") or {}).get("client") or {})
            .get("pastLessons")
        )
        if not connection:
            return data
        nodes = list(connection.get("nodes") or [])
        has_next, unknown = _continues(connection)
        if unknown:
            _warn(
                data,
                "Lesson pagination flag (hasNext) could not be read; this ledger "
                "may be missing older lessons and its totals are a floor.",
            )
        next_offset = offset + len(nodes)
        while has_next and len(nodes) < limit:
            page = self._fetch(
                [
                    OperationCall(
                        "lessons_page",
                        get_operation("CurrentUserPastLessons"),
                        {
                            "offset": next_offset,
                            "limit": min(page_size, limit - len(nodes)),
                            "excludeUnconfirmedLessons": False,
                        },
                    )
                ]
            )
            page_conn = (
                (((page.get("lessons_page") or {}).get("currentUser") or {}).get("client") or {})
                .get("pastLessons")
            )
            page_nodes = list((page_conn or {}).get("nodes") or [])
            if not page_nodes:
                break
            nodes.extend(page_nodes)
            has_next, page_unknown = _continues(page_conn or {})
            if page_unknown and not unknown:
                # A later page's drift is exactly as dangerous as the first
                # page's. Discarding this flag hid the loss entirely.
                unknown = True
                _warn(
                    data,
                    "Lesson pagination flag (hasNext) could not be read on a "
                    "follow-up page; older lessons may be missing.",
                )
            next_offset += len(page_nodes)
        connection["nodes"] = nodes[:limit]
        connection["hasNext"] = _report_more(has_next, unknown, len(nodes), limit)
        return data

    def learner_upcoming_lessons(self) -> dict[str, Any]:
        """Learner upcoming lessons (booked + recurrent reservations)."""
        return self._fetch(
            [OperationCall("upcoming", get_operation("CurrentUserUpcomingLessons"), {})]
        )

    def learner_tutorings(self) -> dict[str, Any]:
        """Learner active subscriptions / tutorings."""
        return self._fetch(
            [OperationCall("tutorings", get_operation("UserActiveTutorings"), {})]
        )

    def learner_stats(self) -> dict[str, Any]:
        """Learner lifetime learning stats."""
        return self._fetch(
            [OperationCall("stats", get_operation("ClientLifetimeStats"), {})]
        )

    def learner_renewals(self) -> dict[str, Any]:
        """Money side of every subscription: charge amount, currency, next date.

        `$orderBy` is deliberately never sent: it is nullable and its
        input-object shape was never recovered from the bundles, so supplying
        one would be a guess baked into a live query.
        """
        return self._fetch(
            [OperationCall("renewals", get_operation("SettingsTutoringList"), {})]
        )

    def learner_certificates(self) -> dict[str, Any]:
        """Achievement certificates per subject, with download links."""
        return self._fetch(
            [OperationCall("certificates", get_operation("AllAchievementCertificate"), {})]
        )

    def learner_balance(self) -> dict[str, Any]:
        """Learner hour balance, idle hours, and refill (charge) schedule."""
        return self._fetch(
            [
                OperationCall("balance", get_operation("BalanceManagementData"), {}),
                OperationCall("wallet_client", get_operation("ClientWallet"), {}),
            ]
        )

    def learner_dashboard(self, lesson_limit: int = 5) -> dict[str, Any]:
        """One-shot learner overview.

        Batches every dashboard panel into a single transport round so the
        stored session is resolved once. Past lessons come through
        ``learner_lessons`` afterwards because that call paginates.
        """
        data = self._fetch(
            [
                OperationCall("balance", get_operation("BalanceManagementData"), {}),
                OperationCall("wallet_client", get_operation("ClientWallet"), {}),
                OperationCall("subscription", get_operation("UserSubscriptionsData"), {}),
                OperationCall("unread", get_operation("ChatUnreadCounter"), {}),
                OperationCall("stats", get_operation("ClientLifetimeStats"), {}),
                OperationCall("upcoming", get_operation("CurrentUserUpcomingLessons"), {}),
            ]
        )
        if lesson_limit > 0:
            data["lessons"] = self.learner_lessons(limit=lesson_limit).get("lessons")
        return data

    chat_page_size = 50

    def chat_thread(self, user_id: int, limit: int = 50) -> dict[str, Any]:
        """Full conversation with one collocutor, paginating into older history.

        ``messages(first: N)`` returns the newest page; ``hasNext`` means older
        messages remain, and ``lastId`` walks backwards from the oldest message
        held so far. The loop stops when Preply reports no more, when a page
        comes back empty, or when ``limit`` is reached - so a server that keeps
        claiming ``hasNext`` cannot spin forever.

        **Stated assumption:** the cursor is ``min(id)``, which assumes message
        ids increase with time. That held on every observed thread (ids descend
        with ``timePosted``), and it is the only ordering signal the API offers
        for this cursor. If it ever stops holding, the failure is bounded rather
        than silent-and-unbounded: ids already fetched are deduped, an
        all-duplicate page breaks the loop, ``limit`` caps total work, and a
        drifted ``hasNext`` now warns. The residual risk is *missing* older
        messages, which ``has_older`` reports.
        """
        page_size = min(limit, self.chat_page_size)
        data = self._fetch(
            [
                OperationCall(
                    "chat",
                    get_operation("ChatAndMessages"),
                    {"userId": int(user_id), "first": page_size},
                )
            ]
        )
        connection = ((data.get("chat") or {}).get("chat") or {}).get("messages")
        if not connection:
            return data
        nodes = list(connection.get("nodes") or [])
        has_next, unknown = _continues(connection)
        if unknown:
            _warn(
                data,
                "Chat pagination flag (hasNext) could not be read; older messages "
                "may be missing from this transcript.",
            )
        while has_next and len(nodes) < limit:
            oldest = min(
                (n.get("id") for n in nodes if n.get("id") is not None),
                default=None,
            )
            if oldest is None:
                break
            page = self._fetch(
                [
                    OperationCall(
                        "chat_page",
                        get_operation("ChatAndMessages"),
                        {
                            "userId": int(user_id),
                            "first": min(page_size, limit - len(nodes)),
                            "lastId": oldest,
                        },
                    )
                ]
            )
            page_conn = ((page.get("chat_page") or {}).get("chat") or {}).get("messages") or {}
            page_nodes = list(page_conn.get("nodes") or [])
            known = {n.get("id") for n in nodes}
            fresh = [n for n in page_nodes if n.get("id") not in known]
            if not fresh:
                break
            nodes.extend(fresh)
            # Both flags must be taken from the latest page. Carrying page 1's
            # `hasOlder` forward reports "older history remains" on a fully
            # fetched conversation - measured against a real 85-message thread
            # whose final page returns hasNext=hasOlder=False.
            has_next, page_unknown = _continues(page_conn)
            if page_unknown and not unknown:
                unknown = True
                _warn(
                    data,
                    "Chat pagination flag (hasNext) could not be read on a "
                    "follow-up page; older messages may be missing.",
                )
            connection["hasOlder"] = bool(page_conn.get("hasOlder"))
        truncated = len(nodes) > limit
        connection["nodes"] = nodes[:limit]
        connection["hasNext"] = _report_more(has_next, unknown, len(nodes), limit) or truncated
        connection["hasOlder"] = bool(connection.get("hasOlder")) or truncated or unknown
        return data

    def chat_collocutors(self) -> dict[str, Any]:
        """Thread summaries, used to resolve a tutor name to a collocutor id."""
        return self._fetch(
            [OperationCall("messages", get_operation("ChatThreadSummaries"), {})]
        )

    def payment_history(self, limit: int = 100) -> dict[str, Any]:
        data = self._fetch([OperationCall("history", get_operation("historyWithBilling"), {})])
        history = data.get("history") or {}
        connection = history.get("paymentsHistory") or {}
        payments = list(connection.get("payments") or [])
        has_next, unknown = _continues(connection)
        if unknown:
            _warn(
                data,
                "Payment pagination flag (hasNext) could not be read; this history "
                "may be missing older payments and spend totals are a floor.",
            )
        while has_next and len(payments) < limit:
            last_id = payments[-1].get("id") if payments else None
            if last_id is None:
                break
            page = self._fetch(
                [
                    OperationCall(
                        "history_page",
                        get_operation("history"),
                        {"lastId": last_id},
                    )
                ]
            )
            page_connection = (page.get("history_page") or {}).get("paymentsHistory") or {}
            page_payments = list(page_connection.get("payments") or [])
            if not page_payments:
                break
            payments.extend(page_payments)
            has_next, page_unknown = _continues(page_connection)
            if page_unknown and not unknown:
                unknown = True
                _warn(
                    data,
                    "Payment pagination flag (hasNext) could not be read on a "
                    "follow-up page; older payments may be missing.",
                )
        connection["payments"] = payments[:limit]
        connection["hasNext"] = _report_more(has_next, unknown, len(payments), limit)
        return data

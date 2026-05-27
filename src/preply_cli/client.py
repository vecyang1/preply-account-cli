from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .browser import BrowserHarnessClient, BrowserTargetSelector, OperationCall
from .queries import get_operation


class PreplyClient:
    student_page_size = 20

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
        return (
            data.get("profile", {})
            .get("currentUser", {})
            .get("tutor", {})
            .get("studentManagementTutorings", {})
        )

    def _extend_student_pages(self, data: dict[str, Any], limit: int, initial_offset: int = 0) -> None:
        connection = self._student_connection(data)
        nodes = connection.get("nodes") or []
        total = int(connection.get("totalCount") or len(nodes))
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
        merged = list(nodes)
        for key in sorted(extra):
            page_nodes = self._student_connection({"profile": extra[key]}).get("nodes") or []
            merged.extend(page_nodes)
        connection["nodes"] = merged[:target_count]

    def wallet(self) -> dict[str, Any]:
        return self._fetch([OperationCall("wallet", get_operation("TutorWallet"), {})])

    def account(self) -> dict[str, Any]:
        return self._fetch([OperationCall("account", get_operation("PreplyCliAccountIdentity"), {})])

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

    def payment_history(self, limit: int = 100) -> dict[str, Any]:
        data = self._fetch([OperationCall("history", get_operation("historyWithBilling"), {})])
        history = data.get("history") or {}
        connection = history.get("paymentsHistory") or {}
        payments = list(connection.get("payments") or [])
        has_next = bool(connection.get("hasNext"))
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
            has_next = bool(page_connection.get("hasNext"))
        connection["payments"] = payments[:limit]
        connection["hasNext"] = has_next and len(payments) >= limit
        return data

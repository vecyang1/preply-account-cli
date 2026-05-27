# Reverse-Engineering Notes

Source: live logged-in Preply tutor page and Preply's loaded JavaScript bundles.

Read-only GraphQL operations used:

- `TutorWallet`: tutor wallet balance, currency, last payout method.
- `PreplyCliStudentList`: custom query over `studentManagementTutorings` for student totals, status, price, confirmed lessons, revenue, refill status, subject, and timezone.
- `TutorHomeUpcomingLessons`: tutor calendar timeslots for schedule.
- `ChatThreadSummaries`: custom query over `messageThreads` for thread id, collocutor, unread count, labels, and last message preview.
- `TutorStudentDetails`, `TutoringStatistics`, `TutorStudentUpcomingLessons`, `TutorStudentsPastLessons`, `StudentManagementRevenueHistory`: per-student detail and timeline data.
- `LessonInsights`: optional lesson insight headline when the account has access.
- `PreplyCliAccountIdentity`: custom identity probe used to choose among multiple logged-in Preply tabs/accounts without reading cookies.
- `historyWithBilling`: settings payment history plus billing information. This returned live learner payments in the second logged-in Chrome account.
- `history(lastId)`: paginated follow-up query for older learner payment rows. Use the last payment id from the previous page.

Useful UI route:

- `https://preply.com/en/settings/history` is useful as a human cross-check for wallet/history, but the tutor account's `paymentsHistory` query returned an empty payment list in the live smoke check. Tutor earnings are therefore summarized from wallet balance plus per-student `totalTutorRevenue`.
- The learner account at `https://preply.com/en/settings/history` loads `historyWithBilling`; a 100-row live smoke export verified pagination and total-spend calculation on 2026-05-27.

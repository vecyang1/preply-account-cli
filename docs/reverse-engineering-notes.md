# Reverse-Engineering Notes

Source: live logged-in Preply tutor page and Preply's loaded JavaScript bundles.

## Direct transport: authenticated cookie replay (2026-08-13)

The CLI can reach the private GraphQL API without a browser at all. Findings,
all measured:

- **Auth is a Django `sessionid` cookie.** `sessionid` alone authenticates
  (`currentUser` populates). `csrftoken` is only needed for mutations, sent as the
  `x-csrftoken` header equal to the cookie. A stale cookie returns HTTP 200 with
  `{"data":{"currentUser":null}}`, not an error — so liveness must be probed, not
  assumed. Locally, most Chrome profiles that held Preply cookies were logged out
  server-side; only one held a valid session.
- **Cloudflare fronts preply.com and can fingerprint the TLS client (JA3).** Plain
  `requests` reached the resolver on 2026-08-13, but `curl_cffi` with
  `impersonate="chrome"` is the robust choice and is the CLI's default. stdlib
  `urllib` failed here on local cert verification (env quirk, not Cloudflare).
- **Cookie custody.** Chrome on macOS stores cookies as `v10` blobs (classic
  "Chrome Safe Storage" Keychain key: PBKDF2-HMAC-SHA1, salt `saltysalt`, 1003
  iters, AES-128-CBC, IV = 16 spaces; newer builds prepend a 32-byte SHA256(host)
  integrity hash to the plaintext). Not the app-bound `v20` scheme. The CLI
  decrypts once, present-user, in `session capture`, then stores the value in
  1Password and reads it unattended via the Service Account bridge. `chrome_cookies.py`
  reads cookie METADATA (names/flags/expiry) without decrypting when enumerating.
- **No persisted-query registry.** Full documents POST to
  `/graphql/v2/<OperationName>`, matching how the CLI already worked.

## Bundle mining: the full operation surface (2026-08-13)

- Preply ships **two** front-end apps with different operations: the marketing/
  search Next.js app (`static.preply.com/static/ssr/...`) and the logged-in SPA
  (`static.preply.com/space/preply-space.<hash>.js`). The dashboard operations are
  in the SPA; its webpack chunk map enumerates ~276 lazy chunks.
- `graphql-tag` templates compile to frozen string arrays, so **entire query
  documents survive verbatim** in the public bundles. Mined **1193 distinct
  operations** (830 queries, 363 mutations) with 100% document text, validated
  against all 13 of the CLI's real operations. The catalogue is written to
  `docs/preply-graphql-catalog.md` + `docs/preply-operations.graphql`, which are
  **gitignored**: this repository is public and the CLI does not need Preply's
  private API surface published alongside it. Re-mine locally if the files are
  absent; do not commit the result.
- Method lesson worth keeping: to find whether a field exists, mine the app's own
  compiled query for it rather than probing key names on a payload. The learner
  lesson ledger (`CurrentUserPastLessons`) had been recorded as "not exposed" from
  a key-name probe; the bundle carried the whole query.

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
- `NextLessonForConfirmation`: learner home prompt payload for "Did your lesson happen?", including lesson id, datetime, status, tutor first name, tutoring id, and subject alias.
- `ConfirmPastLesson`: mutation used by the learner home modal's "Confirm lesson" button. It accepts `lessonId` and returns `{ ok, lesson { id, hasIssue, status } }`.
- `BalanceManagementData`, `ClientWallet`, `UserSubscriptionsData`, `ChatUnreadCounter`: learner hour balance, wallet context, subscription posture, and unread count. See "Learner hour balance" below.
- `ChatAndMessages`: full conversation history over GraphQL. See "Chat history needs no Agora" below.

## Chat history needs no Agora (2026-08-14)

This file and AGENTS.md both recorded that full transcript export "appears to
require additional Agora/chat transport reverse engineering". **That was wrong,
and it is worth keeping why.** The claim came from noticing that the *live*
message stream (`AgoraMessengerCreds` / `AgoraSignalingChannels`) runs over Agora
RTM, and over-generalising from "live delivery uses Agora" to "history uses
Agora". They are different surfaces.

- `ChatAndMessages($userId, $first, $lastId)` returns `chat.messages.nodes[]` with
  `body`, `timePosted`, `authorId`, `files`, and system-message typing — the whole
  archive, over the same GraphQL endpoint as everything else. Agora carries the
  live stream; the history was always queryable.
- Verified live 2026-08-14: one conversation returned 85 messages spanning
  2024-10-06 to 2026-08-06, in two pages, final page `hasNext=false`.
- **Sender attribution is measured, not assumed.** `authorId` is null on ~64% of
  messages: system notices carry a `systemMessageType`, and Preply's own action
  cards are null-author messages with a `button`. Rule, from a 50-message sample
  (me 5 / collocutor 13 / system-typed 24 / button-card 8): author==me → me;
  author==collocutor → their name; else systemMessageType or button → system;
  else `unknown`. Never attribute an unrecognised message to a person.
- Pagination walks backward with `lastId` = the oldest id held. Take **both**
  `hasNext` and `hasOlder` from the newest page fetched — carrying page one's
  `hasOlder` forward reported "older history remains" on a complete thread (found
  by the live check that was verifying the feature; now covered by a test).

## Learner hour balance (2026-08-14)

- The learner "balance" Preply exposes is denominated in **hours**, not money.
  `BalanceManagementData` is the only operation carrying `totalBalance` together
  with per-tutoring refill (subscription) scheduling: `unscheduledLessons`
  (paid hours not yet booked), `unavailableLessons`, and `refill.nextRefill`.
- Two payload facts drove the extractor design: a stopped subscription returns
  `refill: null` while the tutoring still holds paid hours (kept, marked
  `NO_SUBSCRIPTION`), and `unavailableLessons` are excluded from `totalBalance`,
  so the reported total and the per-row hour sum can legitimately differ.
- **General trap, seven instances found by audit (2026-08-14):** a Preply field
  that moves keeps the response GraphQL-valid, so `field or default` silently
  yields a confident wrong number — `balance or 0.0` → "$0.00", a moved `hasNext`
  → "no more pages" (and the code even wrote that back), a moved `totalCount` →
  "page one is the whole account". Distinguish absent (`None`, warn) from a real
  zero; never write back an unreadable continuation flag as `False`. This is the
  same class as the `reviewerLessonCount` move recorded above — a key-name probe
  cannot tell "removed" from "renamed".

Useful UI route:

- `https://preply.com/en/settings/history` is useful as a human cross-check for wallet/history, but the tutor account's `paymentsHistory` query returned an empty payment list in the live smoke check. Tutor earnings are therefore summarized from wallet balance plus per-student `totalTutorRevenue`.
- The learner account at `https://preply.com/en/settings/history` loads `historyWithBilling`; a 100-row live smoke export verified pagination and total-spend calculation on 2026-05-27.
- The learner home confirmation modal at `https://preply.com/en/home` uses stable `data-qa-id` values such as `modal-confirm-last-lesson`, `modal-confirm-last-lesson-confirm-lesson`, and `modal-confirm-last-lesson-report-issue`. Prefer the GraphQL query/mutation above over DOM clicks when automating the CLI.
- The "Report issue" button routes to `/<lang>/lessons/report/<lesson_id>?src=confirmation_modal`. The CLI prints this URL but does not submit issue reports.
- Live mutation check on 2026-06-15: `preply --role learner confirmation --confirm --yes --lesson-id 163250751 --expect-tutor Andres` returned `ok=true`, `status=COMPLETED`, `hasIssue=false`.

## Analysis boundary: lesson cadence

Observed 2026-08-09 while reconciling a learner's dated lesson-note document with a Preply snapshot:

- `historyWithBilling` and paginated `history(lastId)` expose payment/billing records. They are not evidence that each row is one completed class, so payment counts and billed hours must not be presented as lesson frequency without a provider contract that proves that mapping.
- `build_timeline()`'s event-level `past_lesson` rows come from tutor-side `student_details`. The current learner snapshot path does not provide a complete historical lesson-event ledger.

  **Correction (2026-08-13): a learner-side lesson ledger IS exposed.** `CurrentUserPastLessons` returns `currentUser.client.pastLessons.nodes`, one node per real lesson with `datetime`, `status`, `duration`, `paidAmount`, `isRated`/`rating`, tutor, and subject — verified live on a learner account. `CurrentUserUpcomingLessons` gives the forward side. The `lessons` and `upcoming` commands use these. This does not overturn the cadence-boundary caution below (a `COMPLETED` lesson node is still a lesson event, and `paidAmount` is a billing figure), but the earlier "not exposed" claim was a discovery gap, not a Preply limitation. It was found by mining Preply's own bundles rather than probing key names — see the direct-transport reverse engineering below.
- For learner cadence reports, use the dated lesson-note source as the event ledger and use the Preply snapshot only as a separately labelled billing cross-check. Keep capture date, account identity, and live/offline status in the report.
- A browser-harness or remote-debugging failure is evidence about that attempted live route only. Keep the offline snapshot usable, but do not upgrade it to current Preply truth without a fresh readback.

Public tutor profile route:

- `https://preply.com/en/tutor/<id>` exposes a server-rendered Next.js `__NEXT_DATA__` payload that can be read without a logged-in Chrome tab.
- The `props.pageProps.tutor` object contains public stats such as `fullName`, `headline`, `averageScore`, `numberReviews`, `totalLessons`, `reviewsSummary`, and `subcategoriesRatings.reviewedLessonsCount`.
- The `props.pageProps.reviews` list contains public review identity/text/score/date and tutor replies.
- **Per-reviewer lesson counts are exposed, nested.** Each review carries `reviewerInfo: {lessonCount, lastLessonAt, learningGoal}`. Verified live on 2026-08-12 for `https://preply.com/en/tutor/6558836`: all 10 reviews populated, counts `[67, 62, 49, 35, 33, 27, 16, 13, 10, 7]`, `lastLessonAt` as recent as `2026-08-11`. `lastLessonAt` and `learningGoal` are new and have no flat-key predecessor. Because a review's reviewer is identified by first name, this makes a tutor's *retained* students readable from the anonymous public page: how many lessons each reviewer took, and whether they are still taking them.

  This field moved rather than disappeared, and the way that was misread is worth keeping. It was a flat `review.reviewerLessonCount` on 2026-06-13. A 2026-08-09 check searched the payload for that key name, found nothing on two tutors, and this file was updated to say the data was no longer exposed and that per-reviewer counts must not be inferred. Both halves were wrong: the value was on the page the whole time under a new parent, and the instruction not to look is what kept it wrong for three days while `_normalize_review` silently returned `None` for every reviewer. **A key-name search cannot distinguish "removed" from "reorganized".** Before recording a field as gone, search for a known *value* as well as the name (`grep 49` would have landed inside `reviewerInfo`), and diff the parent object's key set against the older capture rather than probing one key at a time.
- The `props.pageProps.reviewDistribution` object contains star counts, and `props.pageProps.tutorSummary` contains Preply-generated strengths, teaching-style, and student-feedback text. The CLI uses these fields for deterministic public review reasoning rather than scraping visible HTML text.
- **Do not read numbers out of `tutorSummary`.** It is generated prose and it goes stale against the counters beside it. On 2026-08-12 tutor 6558836's `strengths` read "She has taught a total of 7 lessons" while `tutor.totalLessons` on the same payload was **517**. The CLI treats these fields as text only; anything numeric must come from the counter, not the summary.
- **`review.language` is not reliable enough for language analytics.** On the same capture, 3 of 10 reviews were labelled `"ko"` while their content was Traditional Chinese, and one tutor reply carried `language: null`. The field is fine to display and wrong to aggregate; detect from the content instead if the answer matters.
- No availability or calendar data is server-rendered. `apolloState.apolloClientCacheStateData2` is an empty object and `highlightDays` / `highlightTimesOfDay` are empty arrays on a cold anonymous fetch — the timetable loads client-side after hydration. `tutor.hasAvailability` is the only availability signal reachable without driving a browser.

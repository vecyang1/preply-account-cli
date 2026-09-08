# Changelog

## 0.12.0 - 2026-09-08

### New: Periodic Encouragement Email & Motivation System (`preply digest`)

- **Scanner & Categorizer (`PreplyEmailScanner`)**:
  - Live query via `spark search --filter "from:preply.com"` across mailboxes (`vecs@foxmail.com` and `yanghxmail@gmail.com`) or file caches (`data/preply_scanned_emails.json`).
  - Classifies 10+ Preply lifecycle email categories (completed lessons, upcoming bookings, subscription renewals, pauses, streaks, payouts).
- **Single Source of Truth Metrics (`SSOTCalculator`)**:
  - Computes non-negative available balances, clamped completion rates, streaks, and milestone progression.
  - Multi-tier milestone ladders for both learners (6 levels) and tutors (5 levels).
- **Psychological Copywriting Engine (`PsychologicalCopywriter`)**:
  - Multilingual support for Simplified Chinese (`zh-CN`), English (`en`), and Vietnamese (`vi`).
  - Adheres to "说人话，不要说实话": reframes paused subscriptions into natural knowledge digestion; celebrates 100% hour depletion as victory; eliminates bureaucratic/harsh administrative vocabulary.
- **Design System Parity Email Renderer (`XinChaoViEmailRenderer`)**:
  - Direct token parity with `https://xinchaovi.com/student`: Terracotta (`#E07A5F`), Dark Slate (`#1E293B`), Sage (`#81B29A`), Amber (`#F59E0B`).
  - Responsive layout: dark gradient hero progress track, milestone beads, 3-column stats grid, upcoming class cards, and localized CTAs.
- **Spark Drafter & Browser Preview (`EmailDrafter`)**:
  - Auto-drafting via Spark Desktop IPC with graceful HTML preview fallback (`data/preview_digest.html`).
- **FluentCRM Synchronization (`FluentCRMSync`)**:
  - Seeds and synchronizes templates directly into WordPress `fc_template` on `xinchaovi.com` with remote readback verification.
  - Deployed template IDs: `2733` (Learner ZH), `2734` (Tutor ZH), `2735` (Learner EN), `2736` (Tutor EN), `2737` (Learner VI), `2738` (Tutor VI).
- **Full Test Suite & Invariant Verification**:
  - Comprehensive unit and adversarial test suite in `tests/test_email_system.py` (260/260 tests passing in 0.44s).
  - CLI invariant checker: `preply digest verify`.

## 0.11.0 - 2026-09-06

### New: Tutor Acceptance Status, Overbooked Detection & Pricing Normalization

- `preply tutor-reviews <url-or-id>`:
  - **Acceptance Status Detection**: Preply SSOT is `isVisibleOnSearch` on the tutor hydration object. When `False`, Preply displays *"Tutor isn’t accepting new students. This can happen when tutors get overbooked."* The CLI now surfaces:
    - `status` (e.g. `APPROVED`)
    - `accepting_new_students` (`Yes`, `No (Overbooked/Paused)`, or `Unknown`)
    - Prominent warning banner when `is_accepting_new_students == False`
    - Caution note in `Review reasoning -> cautions`
  - **Pricing Normalization**:
    - Parsed and displayed `hourly_rate` (e.g. `$7.00 USD`) and `trial_rate` (e.g. `$4 USD`).
  - Unit and live regression tests covering both accepting and non-accepting tutors (237/237 tests passing).

## 0.10.1 - 2026-09-06

### Enhanced: Public Tutor Profile Velocity & Recent Student Lessons

- `preply tutor-reviews <url-or-id>`:
  - Extracted and surfaced `lessons_booked_last_48h`, `active_students`, `is_super_tutor`, and `latest_student_lesson` in the Tutor Overview table.
  - Added a dedicated table **`Recent student lessons (top 5 by last lesson date)`**, dynamically ranking students by their most recent lesson date (`reviewer_last_lesson_at`) and lesson count. Eliminates ad-hoc scripting for determining tutor teaching recency.
- `preply tutor-schedule <url-or-id>`:
  - Added an explanatory note under the Schedule Overview when `booked_slots == 0`, clarifying that Preply's public `BookingTimeslots` API only returns open available slots (`FREE`) and withholds booked slots for privacy.
- Documentation & Semantic Clarification:
  - Clarified `tutor-schedule` data semantics in `README.md` and `AGENTS.md`:
    - Preply's unauthenticated public `BookingTimeslots` endpoint returns exclusively open booking slots (`type: FREE`). Booked slots are either pruned from the public calendar or withheld for privacy.
    - Offline test fixtures (`data/tutor-schedule-sample.json`) retain `BOOKED` slot structures with student initials for schema validation and unit testing; they must not be conflated with live public API output.
    - Clarified the three distinct time horizons across Preply surfaces: past completed lessons (reviews), recent operational velocity (`lessonsBookedLast48h`), and upcoming public availability (`timeslotsForBooking`).


## 0.10.0 - 2026-09-05

### New: public tutor schedule & booking calendar (`tutor-schedule`)

- `preply tutor-schedule <url-or-id>`: inspect public booking timeslots, booked
  lessons, open slots, and daily schedule windows via GraphQL (`BookingTimeslots`).
  Needs no login and no stored session.
- Computes comprehensive aggregate summaries:
  - Total timeslots, booked slots, free slots.
  - Daily breakdown: earliest lesson start, latest lesson end, active window.
  - Night class detection with configurable cutoff (default 18:00 / 6 PM).
- Output options: structured multi-table view, `--json`, and `--csv`.
- Offline support: `-f/--file <saved_json>` for local replay and offline testing.

### Resilient Public Transport & Anti-Bot Egress

- Added `transport.py`: unified public transport with Chrome header impersonation
  (`User-Agent`, `Sec-Ch-Ua`, `Sec-Fetch-*`), eliminating Cloudflare 403 challenge
  blocks on public requests.
- Integrated transparent proxy resolution:
  - `--proxy <url>` CLI flag on both `tutor-schedule` and `tutor-reviews`.
  - Environment variable fallback: `PREPLY_PROXY_URL` -> `PREPLY_TRACKER_PROXY_URL` ->
    `DATAIMPULSE_PROXY_URL` -> `HTTPS_PROXY` -> `HTTP_PROXY`.
  - Auto-fallback on Cloudflare challenge (403/429): retries through proxy if
    direct request is challenged.
- Fixed `tutor-reviews` egress: replaced bare urllib request with resilient transport
  so public tutor review analysis no longer gets blocked on residential IPs.

## 0.9.0 - 2026-08-14

### New: what Preply is about to charge you

- `renewals` — the money side of every subscription: charge amount, currency,
  next charge date, refill hours, billing frequency, per tutor. `balance` counts
  hours and its source operation carries no amount at all, so this is the only
  answer to "how much am I about to pay". Live: 3 upcoming charges totalling
  40.95 USD, next 2026-08-15.
- `certificates` — achievement certificates per subject with hours completed,
  current/next level, hours to the next level, and a download URL. Live: 3
  certificates, 187.0 hours.
- Both support `--json`, `--csv`, and `-f/--file`.

**A bug this feature's own live verification caught.** Preply keeps the final
`nextRefill` date *and* `chargeAmount` on a stopped subscription. Counting every
non-null refill as upcoming reported `next_charge 2023-06-05` and a total of
`436.80 USD` against a true bill of `40.95 USD` — 9 of 23 tutorings were stopped
rows carrying 2023–2025 dates. `analysis._is_upcoming` is now the single gate.
Currencies are subtotalled separately and never summed into one figure.

### Fixed: eight failure paths that reported a verdict they had not earned

Found by an audit of every first-run failure path; each was reproduced before
being changed.

- A `--file` snapshot that was valid JSON but not a snapshot printed a complete
  financial report of zeros at exit 0 on 9 of 10 commands. All 16 load sites now
  go through `cli._load_snapshot`, which refuses unrecognised payloads.
- Every `--file` I/O or parse error escaped as a raw traceback at exit 1.
- `session status` said `stale` when 1Password was rate-limited or the network
  was down. `PreplySessionExpired` now separates "Preply rejected the session"
  from "we never reached Preply"; the latter reports `unknown`.
- `--transport auto` discarded the direct-side reason whenever browser-harness
  was present.
- `confirmation --confirm` without `--yes` resolved a credential and made a
  network round trip before refusing.
- `tutor-reviews` leaked urllib tracebacks on 404/403/refused, sent a
  User-Agent frozen at version 0.3, and read a scheme-less URL as a filename.
- A hung browser-harness raised an uncaught `TimeoutExpired` after 90s.
- `--limit 0` / `--limit -1` were accepted; offline they hit a negative slice
  and dropped rows off the end, live they were sent to Preply as `count: -5`.
- A silent `curl_cffi` → `requests` downgrade left Cloudflare errors blaming the
  session rather than the non-Chrome TLS fingerprint.

### Fixed: the CLI required `cryptography` for commands that never decrypt

`main()` imports `chrome_cookies` for one exception class, and that module
imported `cryptography` at module scope — so a missing `cryptography` was fatal
for every command, including the login-free `tutor-reviews`, and arrived as a
traceback. Proven with a `--no-deps` install: `tutor-reviews` now renders a full
profile with neither `cryptography` nor `curl_cffi` installed.

### Fixed: the browser transport picked silently among several accounts

With two Preply accounts logged in and no selector, it attached to whichever tab
sorted first (`/home` won) and used it. The direct transport already refuses the
identical condition, so which behaviour you got depended on which route `auto`
happened to take. Several tabs of the *same* account are still fine. A
fully-logged-out set of tabs is now reported as "log in", not as a selector
problem.

That logic lives in a Python script `browser.py` generates for browser-harness
to run, which is why no test had ever touched it. `tests/test_browser_script.py`
now compiles and executes that generated script against a simulated CDP; only
`cdp` is faked. Confirmed the new tests fail against the pre-fix file.

### Project

- **Structure**: `cli`, `analysis` and `queries` are now packages, split by whose
  account the code reads. Every module is under the project's 800-line limit
  (previously 1584 / 1208 / 932), and a test enforces it. All 28 operation
  documents were hashed before and after the move: byte-identical.
- The split shipped two latent `NameError`s that 207 passing tests did not
  catch — a live sweep did. `tests/test_module_wiring.py` now walks every
  module's AST for names read but never bound, checks every subcommand resolves
  to a callable, and exercises `main()`'s handler for each error type it claims
  to catch.
- **CI** (`.github/workflows/ci.yml`): the suite runs against the *built
  package* on Python 3.11–3.14 × {Linux, macOS}, plus an sdist/wheel build,
  `twine check`, and a clean-venv install. The test step asserts the collected
  count, because `discover` exits 0 when it collects nothing.
- Packaging metadata: readme, SPDX license, classifiers, keywords and URLs
  added; version is read from `preply_cli.__version__` instead of duplicated.
  `twine check` went from PASSED-with-warnings to PASSED (METADATA 380 → 11,645
  bytes).
- README now states up front that `direct` needs an unshipped 1Password bridge,
  `browser` needs an unshipped helper, `session capture` is macOS-only, and
  `tutor-reviews` is the only zero-setup command. It also documents the test
  command that actually works.
- The public-tutor regression fixture no longer carries a real tutor's name and
  id or 14 real reviewers' names and review text. Every structural field is
  untouched, and the suite passes unchanged against the scrubbed copy — which is
  the proof that no assertion ever depended on an identity.
- 148 → 213 tests.

## 0.8.3 - 2026-08-14

### Conversation content and attachments are now reasonable-over

- `chat <who> --files` lists every attachment in a thread: name, MIME type,
  size, sender, date, and an absolute URL. Verified live: 9 materials (7
  Vietnamese lesson PDFs, 2 audio) spanning 2024-10 to 2025-01.
- `chat <who> --full` now prints each message's attachments inline with their
  URLs instead of only a count.
- `--json` returns `messages` and `files` together, so a whole thread can be fed
  to analysis without a second pass.
- Attachment URLs come back relative from Preply (root-relative
  `/files/<id>?download=true`, or protocol-relative for CDN assets). Both forms
  are normalised to absolute; an already-absolute URL is left alone.

## 0.8.2 - 2026-08-14

### The 0.8.1 pagination fix did not work

An adversarial review demonstrated that 0.8.1's headline claim was false and
that its own test asserted the buggy value as correct. Reproduced, then fixed:

- `_continues()` returns `has_next=False` when the flag is unreadable, so the
  loop never ran and the writeback `(has_next or unknown) and len(nodes) >= limit`
  evaluated to `(False or True) and (20 >= 50)` = **False** — the exact confident
  "nothing more" it was meant to prevent, at the default `limit=50`.
  `_report_more()` now lets unknown win outright, ungated by the count.
- The inner loop discarded the per-page unknown flag, so drift on a *follow-up*
  page gave `hasNext: false` and **no warning at all**. Now warned.
- `chat_thread` had been left out of the `_continues`/`_warn` treatment entirely.

### Other review findings, each demonstrated

- `_extend_student_pages` derived its page count from an unbounded `--limit`:
  `students --limit 100000` built **4999 aliased sub-operations into one live
  request**. Capped at 25 pages.
- That batch never checked the response carried every key it requested; a
  dropped page passed as the whole account. Now warns.
- `compare` — the one command whose job is comparing money — never surfaced
  warnings and showed an unreadable balance as a blank cell. Now prints
  `unknown` plus an account-attributed stderr warning.
- The pagination test's fake transport answered only `calls[0]`, making it
  structurally unable to catch the batch defect above. Rewritten to honour every
  call in a batch.

### Robustness

`tests/test_robustness.py` fuzzes every extractor with malformed payloads and
found **12 crash paths**: `nodes: [null]` is a legal GraphQL response and took
down each one with an `AttributeError`. All node access funnels through
`_dict_nodes`.

Live verification then caught a defect in the fix itself: `students` warned about
a missing `totalCount` on a **learner** account, which has no tutor block at all.
A warning channel that cries wolf gets ignored, so that path returns silently.

Live after all changes: lessons 60 rows `hasNext=True`, history 40 rows, chat 85
messages `has_older=False` `unknown_sender=0`, `students` and `me` both silent on
stderr. Tests: 115 -> 140.

## 0.8.1 - 2026-08-14

### Chat history over GraphQL — a documented limit was wrong

- `chat [who]` — full conversation history with one tutor. No argument lists
  contacts; a name substring or numeric user id opens a thread. `--full` prints
  complete text, `--limit` pages into older history, `--json`/`--csv` export.
- **Corrects AGENTS.md and README**, which both stated full transcript export
  "appears to require Agora/chat transport reverse engineering". It does not.
  `ChatAndMessages` returns `messages.nodes.body` over plain GraphQL. Agora
  carries the live stream, not the archive. Evidence: a real thread returned 85
  messages spanning 2024-10-06 to 2026-08-06 in two pages, final page
  `hasNext=false`, 0 unattributable senders.
- Sender attribution is measured rather than assumed. Across a 50-message
  sample: authored-by-me 5, by-collocutor 13, null author with a
  `systemMessageType` 24, null author carrying an action `button` 8. Because
  `authorId` is null on 64% of messages it cannot decide the sender alone, so
  messages render as `me` / tutor name / `system` / `unknown`, and
  `unknown_sender` counts anything the rule cannot place.

### Data-integrity hardening (absent is not zero)

Two review passes found that a moved Preply field could be silently converted
into a confident wrong number. All were reproduced before being fixed.

- `balance`: a subscription whose `status` field moved reported
  `NO_SUBSCRIPTION` while still billing, and a restructured `totalBalance`
  reported `0.0` hours. Refill state is now three-valued —
  `CONFIGURED` / `NO_SUBSCRIPTION` (refill genuinely null) / `UNKNOWN` (present
  but unreadable) — and an unreadable balance reads `unknown`, never `0`.
- `build_balance_summary` now returns `warnings[]`, printed to **stderr** by
  `balance` and `me` so `--json`/`--csv` pipes stay clean. Proven both ways: a
  healthy snapshot emits 0 bytes on stderr; a snapshot with `status`,
  `nextRefill`, `nextSubscription` removed and `totalBalance` restructured emits
  3 warnings.
- Chat pagination took `hasOlder` from the first page instead of the last, so a
  fully fetched 85-message thread still claimed older history remained.
- `me` gained `--csv`, the only tabular command that lacked it.
- New `tests/test_source_hygiene.py` rejects zero-width and control characters in
  source, after a U+200B broke `analysis.py` at import while looking correct in
  every editor.

### Field-drift hardening across the older extractors

An audit demonstrated (not merely argued) seven more instances of the same bug
class in pre-existing code: a Preply field moves, the response stays
GraphQL-valid, and a `.get(x) or default` turns the absence into a confident
wrong number. Each is now a regression test in `tests/test_field_drift.py`.

- `build_account_summary`: a moved `balance` reported `0.00 USD` on a wallet
  actually holding money; moved `totalTutorRevenue` / `confirmedLessonsCount`
  reported `0`. Balance is now `unknown` when unreadable, and partial sums are
  reported as a floor with a warning.
- `build_payment_summary`: a moved `amount` reported `$0.00` spend.
- `build_lesson_summary`: moved `duration` / `paidAmount` zeroed hours and spend.
- `_extend_student_pages`: a moved `totalCount` made the target equal page one,
  so pagination never ran and 20 loaded students were reported as the whole
  account (measured against a 100-student tutor). It now keeps paging and warns.
- `learner_lessons` / `payment_history`: a moved `hasNext` not only stopped
  pagination after one page but **wrote back `hasNext: false`**, actively
  asserting completeness. Unknown continuation now stays truthy.
- `tutoring_rows`: an active subscription whose `status` moved rendered as a
  blank cell, identical to no subscription. Now three-valued like `balance`.
- `build_tutor_review_analysis`: moved `numberReviews` / `totalLessons`
  downgraded a 500-review, 12000-lesson tutor to `public_proof: limited`. There
  is now an explicit `unknown` bucket - missing data is not evidence of weakness.

Warnings from these summaries print to stderr in `status`, `history`, `lessons`,
`analyze`, `tutors`, `balance`, and `me`.

Tests: 77 -> 115.

## 0.7.0 - 2026-08-13

### Learner money/hours surface (verified live)

- `balance` — the learner **hour** balance that no previous command exposed.
  Per tutor: hours banked, hours still unscheduled, hours tied to a booked
  lesson, next automatic charge date, and billing frequency. Built on
  `BalanceManagementData`, the only operation that reports `totalBalance`
  together with per-tutoring refill scheduling.
- `me` — one-screen learner dashboard composing identity, lifetime stats, hour
  balance, upcoming lessons, recent lessons, upcoming charge dates, unscheduled
  paid hours, and tutors awaiting a first payment. Batches six operations into a
  single transport round so the 1Password session resolves once.
- Registered four operations, each probed live before wiring:
  `BalanceManagementData`, `ClientWallet`, `UserSubscriptionsData`,
  `ChatUnreadCounter`. Operation names match Preply's own, so requests look like
  the site's.
- `ClientWallet` also surfaces `leads(status: PENDING_PAYMENT)` — tutors matched
  with the learner but never paid — shown as "Awaiting first payment".

### Correctness notes found while building

- A tutoring whose subscription was stopped returns `refill: null` while still
  holding paid hours. Those rows are kept and marked `NO_SUBSCRIPTION` with no
  charge date, because they are exactly the ones worth acting on. Covered by
  `tests/test_balance.py::test_null_refill_becomes_no_subscription_not_a_crash`.
- `unavailable` hours are excluded from Preply's `totalBalance`. The summary
  therefore reports `total_balance_hours` (Preply's own number) and
  `summed_row_hours` (the row sum) as separate fields instead of reconciling
  them, so a future divergence stays visible.

## 0.6.0 - 2026-08-13

### Unattended direct transport (no browser)

- Added a second transport, `--transport {auto,direct,browser}` (default `auto`).
  `direct` replays a Preply `sessionid` cookie stored in 1Password straight to
  `https://preply.com/graphql/v2`, so the CLI runs with no logged-in Chrome tab,
  no `browser-harness`, and no Touch ID. `curl_cffi` Chrome-impersonation clears
  Cloudflare; `requests` is the fallback. `auto` prefers a stored session and
  falls back to the browser transport.
- Added `session capture|list|status`. `capture` decrypts live Chrome sessions
  (macOS `v10` cookies), probes each against the API, and stores only the ones
  that authenticate — recording the account identity Preply returns, not the
  Chrome email label. One 1Password `API Credential` item per account in the
  `Agent Automation` vault; the session token is read in-process via the
  Service Account bridge and is never printed or written to disk.
- **Custody model change**: SECURITY.md previously forbade storing tokens. The
  token is now stored deliberately — only in 1Password — as the custody choice
  that enables unattended runs. The `browser` transport still stores nothing.
- Proven live 2026-08-13 on a learner account: capture → `account`, `history`,
  `lessons`, `upcoming`, `tutors`, `stats` all returned real data through
  1Password with no browser. Of the local Chrome profiles with Preply cookies,
  only one held a server-side-valid session; the rest were logged out (a
  per-account liveness fact, surfaced by `session status`).

### New learner commands (verified live)

- `lessons` — learner completed-lesson **event ledger** via `CurrentUserPastLessons`
  (date, subject, tutor first name, duration, status, paid amount, rating + summary).
  This is the learner-side lesson ledger the reverse-engineering notes had recorded
  as not exposed; it is exposed, under `currentUser.client.pastLessons`.
- `upcoming` — learner upcoming lessons (`CurrentUserUpcomingLessons`, handles both
  booked lessons and recurrent reservations).
- `tutors` — learner active tutors/subscriptions (`UserActiveTutorings`): price,
  lessons taken, subject, refill/subscription state.
- `stats` — learner lifetime stats (`ClientLifetimeStats`): streak, lessons, practices.

### API surface reverse-engineering

- Mined Preply's public JS bundles: **1193 GraphQL operations** (830 queries,
  363 mutations) recovered with full document text, validated against all 13 of
  the CLI's real operations. The catalogue is kept **local and gitignored**
  (`docs/preply-graphql-catalog.md`, `docs/preply-operations.graphql`) as the
  prioritized surface to grow into; it is not published with this repository.
- Tests: 63 total (was 27) — added coverage for the direct transport, the
  1Password session store, Chrome `v10` cookie decryption, and the learner extractors.

### Hardening (from an adversarial security review of the new modules)

- Secret-bearing dataclass fields (`DirectHttpClient`, `ProfileCookies`) are now
  `repr=False`, so a stray `repr()`/`print()`/f-string can never dump a session
  value. (No active path did — closed defensively.)
- `upcoming`: recurrent-lesson reservations are now identified by GraphQL
  `__typename` and correctly labelled `RESERVED`; the previous heuristic left
  non-conflicting reservations with a blank status.
- `session capture` now exits cleanly (not a raw traceback) when Chrome is
  missing or the keychain read fails, and reports "cookie present but
  undecryptable" (e.g. a future app-bound scheme) instead of a bare "no-session".
- Chrome cookie lookup is pinned to `preply.com`/`*.preply.com` rather than any
  host containing the substring "preply".
- Clarified that `--transport auto` falls back to browser only when no session is
  stored; a stored-but-stale session is a clear re-capture error, not a silent
  fallback. Removed a dead helper.

## 0.5.0 - 2026-08-12

- Fixed the per-reviewer lesson count, which had silently read `None` for every review since Preply nested it. `_normalize_review` now reads `reviewerInfo.lessonCount` and keeps the flat `reviewerLessonCount` as a fallback for older captures.
- Added `reviewer_last_lesson_at` and `reviewer_learning_goal` from the same `reviewerInfo` object, and a `last_lesson` column to the `tutor-reviews` table and CSV.
- Added `analysis.retention`: reviewers ranked by lesson count, a long-term cohort at the 20-lesson cutoff, lessons represented by reviewers, and that figure as a share of the tutor's lifetime total. `tutor-reviews` prints a "Long-term students" table when the cohort is non-empty.
- Added `profile["warnings"]`, printed to stderr, when reviews are present but no reviewer lesson count parses from either location. A blanket `None` used to be indistinguishable from a tutor with no data, which is what hid the regression.
- Added a contract test over a real 2026-08-12 capture of tutor 6558836 (`tests/fixtures/`), covering the nested path, the legacy flat path, and the warning in both directions. Confirmed the new assertions fail against the pre-fix parser.
- Verified live on 2026-08-12: `tutor-reviews https://preply.com/en/tutor/6558836` returned six reviewers at 20+ lessons, the highest at 67 lessons with a last lesson dated 2026-08-11.

## 0.4.0 - 2026-06-15

- Added `confirmation` to show the learner "Did your lesson happen?" prompt from `NextLessonForConfirmation`.
- Added explicitly gated `confirmation --confirm --yes` support for `ConfirmPastLesson`, with optional `--lesson-id`, `--expect-tutor`, and `--expect-datetime` guards.
- Updated the safety model from read-only-only to read-only by default with one reviewed mutating command.
- Verified the live confirmation path on 2026-06-15: Andres lesson `163250751` returned `COMPLETED` with no issue flag.

## 0.3.1 - 2026-06-13

- Changed `tutor-reviews` to print all public reviews by default. Use `--limit N` when only a short preview is wanted.

## 0.3.0 - 2026-06-13

- Added `tutor-reviews` for public Preply tutor profile URLs or ids.
- Extracts public profile stats, all server-rendered reviews, tutor replies, review distribution, anonymous lesson-review counts, and Preply's review/tutor summaries.
- Adds deterministic review reasoning with public-proof strength, sentiment, recurring themes, cautions, and recent-review evidence.

## 0.2.0 - 2026-05-27

- Added role-aware Preply tab selection with `--role tutor`, `--role learner`, `--user-id`, and `--name`.
- Added `account` command to show the selected Preply account.
- Added learner payment history export through `historyWithBilling` and paginated `history(lastId)`.
- Added learner snapshot and compare support with spent totals.
- Added tests for account selectors, payment summaries, and reverse-engineered query registration.

## 0.1.0 - 2026-05-27

- Added read-only tutor CLI for status, students, schedule, wallet, messages, student details, analysis, snapshots, and comparisons.

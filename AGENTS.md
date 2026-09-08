# Preply CLI Agent Notes

This is a local Preply tutor and learner account CLI. It is read-only by default, with one explicitly gated lesson-confirmation mutation.

## Transports (how the CLI reaches Preply)

Choose with the global `--transport {auto,direct,browser}` flag (default `auto`).

- **direct** — the unattended path. Replays a stored Preply `sessionid` cookie
  to `https://preply.com/graphql/v2` using `curl_cffi` (Chrome TLS impersonation
  clears Cloudflare) with a `requests` fallback. The session token lives **only
  in 1Password** (`Agent Automation` vault, one item per account, tag
  `preply-session`) and is read in-process via the Service Account bridge — no
  Touch ID, no browser. Code: `direct.py`, `session_store.py`.
- **browser** — the original transport: same-origin `fetch()` inside a logged-in
  Chrome tab via `browser-harness`. No token stored; session never leaves Chrome.
- **auto** — use `direct` when a matching stored session exists, else `browser`.

`preply session capture` decrypts a live Chrome session once (present-user, one
Keychain authorization), probes it live, and stores only sessions that
authenticate — recording the account identity the server returns. Code:
`chrome_cookies.py`, `capture.py`.

## Layout

Three packages, each split along the axis that decides whether a shape is
*verified* — learner operations are checked against a live learner account,
tutor operations cannot be (no tutor session exists).

```
queries/   _operation.py  shared.py  tutor.py  learner.py
analysis/  _common.py     tutor_views.py  learner_views.py  chat_views.py
cli/       _shared.py     tutor_cmds.py   learner_cmds.py   chat_cmds.py  review_cmds.py  schedule_cmds.py
           __init__.py  <- parser, main(), session commands, the gated mutation
transport.py         <- resilient public HTTP/GraphQL transport with proxy resolution & Chrome headers
public_profile.py    <- Next.js hydration payload extractor for tutor profiles & reviews
public_schedule.py   <- BookingTimeslots GraphQL executor, timeslot normalization & night class analysis
```

`queries/__init__.py` and `analysis/__init__.py` re-export flat, so the public
surface is what it was before the split. Every module stays under 800 lines and
`tests/test_module_wiring.py` enforces it.

**When moving code between these modules, run the suite *and* a live command.**
The split itself shipped two latent `NameError`s that all 207 tests passed over:
a module-level name is resolved when the line executes, so `cmd_history` imported
cleanly and failed only against a live account, and `main()`'s `except` clause
referenced a name its new header did not import — reachable only when something
else had already gone wrong. `test_module_wiring.py` now walks every module's AST
for names it reads but never binds, and exercises `main()`'s handler for each
error type it claims to catch.

Patch the **transport**, not the command, when testing command behaviour:
`build_parser` binds each `func` as a parser default at build time, so patching
`learner_cmds.cmd_stats` leaves the bound original in place. The first draft of
that test ran the real command against the real account and passed.

## Safety

- The session token custody model changed deliberately: `direct` stores the
  `sessionid` in 1Password (never the repo, a dotfile, an env file, or logs).
  `browser` still stores nothing. See SECURITY.md.
- **Never print a `sessionid` or `csrftoken`.** Read secrets only through the
  Service Account bridge (`op read`); never shell out to bare `op` (it prompts).
- Chrome cookie decryption is a present-user setup step; do not run it unattended.
- Treat `data/` snapshots as private student/message data. Keep `data/` ignored.
- Keep operations read-only unless the user explicitly asks for a mutation and
  approves the exact action.
- `confirmation --confirm --yes` is the only approved mutating path. It confirms
  Preply's pending "Did your lesson happen?" prompt and can trigger tutor
  payment. Prefer `--lesson-id` and `--expect-tutor` guards.

## Verification

Offline (no account needed):

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
preply --version
```

Unattended direct path (needs a captured session in 1Password + SA bridge running):

```bash
preply session list
preply session status
preply --transport direct --role learner account
preply --transport direct --role learner history --limit 5
preply --transport direct --role learner confirmation
preply --transport direct --role learner me
preply --transport direct --role learner balance
```

Browser path (needs a logged-in Preply tab in desktop Chrome + browser-harness):

```bash
preply --transport browser --role tutor status
preply --transport browser --role tutor students --limit 3
preply --transport browser --role tutor schedule --days 7
```

To (re)capture a session while present in Chrome: `preply session capture`
(all profiles) or `preply session capture --profile "Profile 2"`.

## Known Limits

- `studentManagementTutorings` silently fails for `count` above 20, so the client paginates in 20-row chunks.
- Several Preply accounts can be open at once. Use global selectors before the command: `--role tutor`, `--role learner`, `--user-id`, or `--name`.
- Learner payment history is available through `historyWithBilling` plus paginated `history(lastId)`.
- **Chat history does NOT need Agora** (corrected 2026-08-14; this file previously
  said it did). `ChatAndMessages` returns `messages.nodes.body` over plain
  GraphQL. Measured on a real thread: 85 messages spanning 2024-10-06 to
  2026-08-06, fetched in two pages, final page `hasNext=false`. Agora carries the
  *live* stream; it is not required for history. Use `preply chat <who>`.
  - Sender attribution is measured, not assumed. Over a 50-message sample:
    authored-by-me (5), authored-by-collocutor (13), null author with a
    `systemMessageType` (24), and null author carrying an action `button` (8).
    `authorId` alone is null on 64% of messages, so it cannot decide the sender.
    Anything outside those buckets renders as `unknown` and is counted in
    `unknown_sender` — never attributed to a person.
  - Pagination walks backwards with `lastId` = the oldest id held so far. Take
    **both** `hasNext` and `hasOlder` from the newest page fetched; carrying page
    one's `hasOlder` forward reports "older history remains" on a thread that was
    already complete (regression covered in `tests/test_chat.py`).
  - Attachments are reachable too: `chat <who> --files` (name, MIME, size,
    sender, absolute URL). Preply returns attachment links **relative** —
    `downloadUrl` root-relative (`/files/<id>?download=true`), CDN assets
    protocol-relative (`//…`) — so both are normalised before display. Anything
    printing a Preply asset URL must do the same or it emits dead links.
  - `build_chat_summary` reports `system_by_button`: how many messages were
    called "system" purely because they carried an action button and no author.
    That rule is an inference from one 50-message sample, so the counter exists
    to keep it falsifiable. If it ever looks like real correspondence, revisit
    the rule rather than letting it mislabel a person.
- **Lesson cadence boundary**: `history` / `historyWithBilling` are billing surfaces, not a completed-lesson event ledger. Do not derive class frequency from `payment_count`, payment rows, or `hours_total` unless the provider contract proves a one-to-one mapping. For learner cadence work, join an explicitly dated external lesson-note source with a Preply snapshot as a billing cross-check; keep the source and freshness labels visible.
- **Event timeline scope**: `analyze --deep` can build event-level `past_lesson` rows from tutor-side `student_details`. It does not establish a complete learner-side historical class ledger. Offline snapshots are historical evidence; record their capture date and account identity before making current claims.
- **Stored-session liveness**: a `sessionid` cookie in Chrome (or 1Password) is not proof the session is valid — Preply invalidates sessions server-side on logout/expiry. A stale cookie authenticates to `currentUser: null`, not an error. `preply session status` probes each stored session live. To capture an account whose Chrome session is stale, re-log-in that account in Chrome, then rerun `preply session capture`. `direct` transport fails loudly ("session no longer authenticated") rather than guessing when a stored session goes stale.
- **Hours vs money (learner)**: the learner balance Preply exposes is denominated
  in **hours**, not currency. `balance` reads `BalanceManagementData`, the only
  operation carrying `totalBalance` alongside per-tutoring refill scheduling.
  Two shapes matter and both are covered by `tests/test_balance.py`: a stopped
  subscription returns `refill: null` while the tutoring still holds paid hours
  (kept, marked `NO_SUBSCRIPTION`), and `unavailableLessons` are excluded from
  `totalBalance`, so the reported total and the per-row sum can legitimately
  differ — report both rather than reconciling them.
- **Absent is not zero** (the recurring bug class in this repo). Preply moves
  fields while keeping the response GraphQL-valid, so nothing raises — and a
  `.get(x) or default` silently turns the absence into a confident wrong number.
  Measured instances: a moved `balance` reporting `0.00 USD`, a moved `hasNext`
  making pagination write back `hasNext: false` (asserting completeness it never
  checked), a moved `totalCount` reporting 20 loaded students as a 100-student
  account. Rules now in force:
  - Use `analysis._opt_number` (returns `None`) for any field a user reads as
    fact; reserve `_number`'s 0.0 default for genuine optional addends.
  - Summary builders return `warnings: list[str]`; commands print them via
    `cli._print_data_warnings` to **stderr**, so `--json`/`--csv` pipes stay clean.
  - Status-like fields are three-valued: real value / `NO_SUBSCRIPTION` (the
    parent object is genuinely null) / `UNKNOWN` (parent present, field
    unreadable). Never render "unreadable" as a blank cell.
  - Never write back a computed `False` for a continuation flag you could not
    read. Unknown stays truthy.
  - `tests/test_field_drift.py` reconstructs each measured failure; add to it
    rather than trusting a new extractor by inspection.
- **Stopped subscriptions keep a real charge date and amount.** Measured live
  2026-08-14 on `SettingsTutoringList`: of 23 tutorings, 11 had `refill: null`,
  9 were `status: STOPPED`, 3 `CONFIGURED`. The STOPPED rows carried
  `nextRefill` values from 2023-2025 *with* a non-null `chargeAmount`, so
  treating "has a refill object and a date" as "will be charged" produced a
  headline `next_charge 2023-06-05` and a total of `436.80 USD` against a true
  bill of `40.95 USD`. `analysis._is_upcoming` is the single gate; anything
  summing Preply charges must go through it. A status outside the known set is
  counted as upcoming **and** warned about — under-reporting a bill is an
  invisible surprise later, over-reporting is a visible one now.
- **Currencies are never summed together.** `build_renewal_summary` returns
  `charge_totals` as a per-currency dict. One number spanning USD and EUR is a
  coincidence, not a bill.
- **A failure to look is not a verdict** (the message-level form of "absent is
  not zero", added 2026-08-14 after an audit reproduced eight instances):
  - `session status` is three-valued. Only `PreplySessionExpired` -- Preply
    answering and rejecting the session -- means `stale`. A 1Password
    rate-limit, a TLS error, or an HTTP 500 means `unknown`, because the session
    was never tested. `stale` sends the user to `session capture`, which needs
    them physically present.
  - `--file` payloads are validated against `cli.SNAPSHOT_MARKERS`. Well-formed
    JSON that is not a snapshot used to render a full financial report of zeros
    at exit 0 on 9 of 10 commands. Add new top-level snapshot keys to that set.
  - `--transport auto` carries the direct-side failure reason into the browser
    route's error (`BrowserHarnessClient.fallback_note`). Reporting only the
    second-choice route's symptom hides the first choice's cause.
  - Gates run before I/O. `confirmation --confirm` without `--yes` refuses
    before a credential is resolved; the test asserts this with an exploding
    `_client`, not a stub return value, because a stub cannot observe ordering.
- **The full API catalogue is deliberately NOT in this repository.** 1193
  operations with full query text were mined from Preply's public JS bundles on
  2026-08-13 into `docs/preply-graphql-catalog.md`,
  `docs/preply-operations.graphql`, and `docs/preply-operation-names.txt`. This
  repository is public, and publishing the CLI does not require publishing
  Preply's private API surface, so those three files are **gitignored and kept
  local only**. If they are not in your working copy, re-mine them with the
  method in `docs/reverse-engineering-notes.md` ("Bundle mining") — do not commit
  the result. Wire new commands from the catalogue by priority and verify each
  against a live account before shipping.

## Recent Enhancements (2026-06-13)

- **Learner Safety**: Fixed `AttributeError` crashes in `client.py` and `analysis.py` when running CLI subcommands on learner/student accounts where `tutor` is `None` in GraphQL responses.
- **Offline Mode (`--file` / `-f`)**: Added option to pass a saved snapshot JSON file (e.g. `--file data/tutor-snapshot.json`) to subcommands to query and analyze account snapshots offline without needing browser connection.
- **CSV Output (`--csv`)**: Added a `--csv` flag option to tabular subcommands (`status`, `students`, `wallet`, `schedule`, `messages`, `student`, `analyze`, `compare`, `history`) to output raw data formatted as standard CSV, facilitating imports into spreadsheet/bookkeeping software.
- **Public Tutor Reviews**: Added `tutor-reviews <url-or-id>` to read Preply public tutor profile review payloads without login and summarize rating proof, themes, cautions, and review evidence. It prints all reviews by default; use `--limit N` only when a short preview is wanted. Verified on `https://preply.com/en/tutor/2807691` with `5.0`, `56` reviews, `2680` lessons, and `105` anonymous lesson-review ratings.
- **Lesson Confirmation Prompt**: Added `confirmation` to read Preply's pending "Did your lesson happen?" prompt through `NextLessonForConfirmation`. `confirmation --confirm --yes` sends `ConfirmPastLesson`, while optional `--lesson-id`, `--expect-tutor`, and `--expect-datetime` guards prevent accidental confirmation of the wrong prompt. Live verification on 2026-06-15 confirmed Andres lesson `163250751` and returned `COMPLETED`, `hasIssue=false`.

## Learnings for Future Agents

- **Browser Contexts**: The `chrome-devtools` server runs in an isolated sandboxed browser, whereas `browser-harness` connects to the user's active desktop Chrome profile. Use `browser-harness` scripts to interact with the user's active session, and ensure Preply tabs are opened in their desktop Chrome (not the sandboxed CDP browser).
- **Snapshot Integrity**: The saved snapshot JSON structures are stable and match GraphQL data shapes. Command refactoring should always support fallback structures (`_account` key vs `currentUser`) to maintain offline compatibility with historical snapshot files.
- **Snapshot Freshness**: An offline snapshot is a dated readback, not live Preply state. A failed browser-harness handshake narrows the live-route proof; it does not prove that Preply lacks an API or that the snapshot is current.
- **Public Profile Payloads**: Tutor profile pages expose a Next.js `__NEXT_DATA__` payload with `tutor`, `reviews`, `reviewDistribution`, and `tutorSummary`. Prefer that structured payload over visible-text scraping for public review work.
- **Confirmation Modal Payloads**: Learner home exposes `myNextLessonForConfirmation` and the modal buttons have stable `data-qa-id` values, but the CLI should prefer the GraphQL query/mutation over DOM clicking.
- **Public Schedule Semantics (`tutor-schedule` vs Live Reality)**:
  - **`BookingTimeslots` on unauthenticated public endpoints returns exclusively open booking slots (`type: FREE`)**. When a slot is booked by a student, Preply either prunes the timeslot from the public response or withholds the occupied interval for privacy. `BOOKED` slots with student initials (e.g. `bookedTimeslotUserInitials`) exist in offline test fixtures (`data/tutor-schedule-sample.json`) and internal/authenticated views, NOT in unauthenticated public fetches.
  - **Never confuse offline test fixtures with live network reality** (per `starting-with-readiness`: "没人跑的检查不算证据"). Running a test against a synthetic JSON file verifies the parser contract; it does not constitute proof that the production API returns booked records.
  - **Distinguish Three Preply Time Horizons**:
    1. *Past Completed Lessons*: Extracted from `tutor-reviews` timestamps (e.g. "student Alex had a lesson on 2026-09-04").
    2. *Recent Operational Velocity*: `lessonsBookedLast48h` on the public profile payload (bookings created in the past 48 hours).
    3. *Upcoming Availability*: `timeslotsForBooking` from `tutor-schedule` (open slots across the next N days). A tutor with recent reviews and `lessonsBookedLast48h: 4` can legitimately show `booked: 0` and `free: 128` on future dates if their upcoming availability is fully open and unreserved.

## Preply Periodic Email & Motivation System (`preply digest`) (2026-09-08)

Engineered a complete, production-grade periodic email notification and motivation engine for both Learners (students) and Tutors (educators) conforming to `https://xinchaovi.com/student` design tokens and psychological copywriting principles ("说人话，不要说实话").

### Architecture & Subsystems:
1. **Scanner & Parser (`PreplyEmailScanner`)**:
   - Scans live mailbox events via `spark search --filter "from:preply.com"` across accounts (`vecs@foxmail.com` and `yanghxmail@gmail.com`) or parses JSON snapshots (`data/preply_scanned_emails.json`).
   - Categorizes 10+ distinct Preply lifecycle events (completed lessons, upcoming bookings, subscription renewals, pauses, streak milestones, payout notifications).
2. **Single Source of Truth Metrics (`SSOTCalculator`)**:
   - Mathematical invariants: `Available Balance = max(0, Granted - Consumed - Scheduled)`. Non-negative bounds, clamped completion rates (0-100%).
   - Dynamic milestone ladder (6 progression levels for learners, 5 for tutors) with automatic unlock tracking.
3. **Psychological Copywriting (`PsychologicalCopywriter`)**:
   - Trilingual support: Simplified Chinese (`zh-CN`), English (`en`), Vietnamese (`vi`).
   - Reframes pauses as natural knowledge digestion/consolidation; reframes hours remaining into finish-line proximity; praises 100% hour depletion as milestone victory.
   - Zero guilt-tripping or harsh billing jargon.
4. **Design System Parity Renderer (`XinChaoViEmailRenderer`)**:
   - 100% parity with `xinchaovi.com/student` brand tokens: Terracotta (`#E07A5F`), Dark Slate (`#1E293B`), Sage (`#81B29A`), Amber (`#F59E0B`).
   - Dark gradient hero progress card, milestone beads, 3-column stats grid, upcoming session cards, and mobile-responsive inline CSS.
5. **Spark Drafter (`EmailDrafter`)**:
   - Pushes drafts directly into Spark Desktop via local IPC; gracefully falls back to local HTML preview generation (`data/preview_digest.html`) when IPC has read-only permissions.
6. **FluentCRM Synchronization (`FluentCRMSync`)**:
   - Seeds production templates directly into WordPress `fc_template` custom post type on `xinchaovi.com` via `fluentcrm-ops`.
   - Enforces unidirectional data flow: API mutation -> immediate remote readback verification.
   - Published live templates: IDs `2733` (Learner ZH), `2734` (Tutor ZH), `2735` (Learner EN), `2736` (Tutor EN), `2737` (Learner VI), `2738` (Tutor VI).

### Commands:
- `preply digest scan [--live] [--save data/events.json] [--in-file path]`
- `preply digest calculate [--role learner|tutor] [--json]`
- `preply digest generate [--role learner|tutor] [--lang en|zh-CN|vi] [--out file.html]`
- `preply digest draft [--role learner|tutor] [--to email]`
- `preply digest preview [--role learner|tutor] [--lang zh-CN]`
- `preply digest verify` (mathematical & psychological invariant checks)
- `preply digest push-crm [--site xinchaovi.com] [--role learner|tutor|all] [--lang zh-CN|en|vi] [--dry-run]`

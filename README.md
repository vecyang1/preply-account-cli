# Preply Account CLI

Local CLI for your own Preply tutor and learner accounts. Read-only by default;
the lesson confirmation command is the only mutating path and requires explicit
`--confirm --yes` flags.

Two ways to reach Preply (global `--transport {auto,direct,browser}`, default `auto`):

- **direct** — unattended. Replays a Preply session stored in **1Password** (one
  item per account) straight to the GraphQL API. No browser, no Touch ID. The
  session token never touches the repo or disk in plaintext.
- **browser** — same-origin `fetch()` inside a logged-in Chrome tab via
  `browser-harness`. Stores nothing; the session stays in Chrome.

This is an unofficial community tool. Use it only with accounts you own or are authorized to inspect, and respect Preply's terms and privacy requirements.

## Before you start — what you actually need

Be aware of this up front rather than three commands in:

- **Only `tutor-reviews` and `tutor-schedule` work with no setup at all.** They
  read any tutor's public profile and public booking calendar via GraphQL, need
  no login, and run on any platform. Both support `--proxy` and auto-proxy fallback.
  Everything else needs a logged-in Preply session, which means one of the two
  transports below.
- **`direct` needs 1Password plus a Service Account bridge** (`bridge_router`)
  that is *not* shipped with this package. Point `PREPLY_OP_BRIDGE_DIR` at your
  own bridge's scripts directory, or use the browser transport. `PREPLY_OP_VAULT`
  overrides the vault name (default `Agent Automation`).
- **`browser` needs `browser-harness`** on `PATH` — an external helper that
  drives your logged-in desktop Chrome. It is not published as part of this
  project either.
- **`session capture` is macOS-only.** It decrypts Chrome's `v10` cookie store
  via the macOS Keychain and refuses to run elsewhere. The rest of the CLI is
  portable; CI runs the suite on Linux and macOS.

Nothing here silently degrades: with neither transport configured, any
authenticated command prints both routes and why each is unavailable.

## Quick Start (unattended / direct)

1. Install this CLI:

```bash
python3 -m pip install -e .
```

2. Capture a live Preply session from Chrome into 1Password (present-user, one
   Keychain prompt). This decrypts each logged-in Chrome profile's session,
   probes it, and stores the ones that authenticate:

```bash
preply session capture
preply session list
preply session status
```

3. Run commands unattended — the session comes from 1Password, no browser needed:

```bash
preply --role learner account
preply --role learner history --limit 100
preply --role learner confirmation
preply --role tutor status
preply --role tutor students
preply --role tutor analyze
preply tutor-reviews https://preply.com/en/tutor/2807691
```

`--transport direct` forces the 1Password path (and fails loudly if no matching
session is stored); `--transport browser` forces the Chrome-tab path; `auto`
(default) prefers direct and falls back to browser.

### Browser path (no 1Password)

Install/expose `browser-harness` on `PATH`, open Preply logged-in in Chrome, then:

```bash
preply --transport browser --role tutor status
preply --transport browser --role tutor schedule --days 30
```

When several Preply tabs/accounts are open, choose the target before the command:

```bash
preply --role tutor account
preply --role learner account
preply --user-id 123456 account
preply --name "Example Learner" account
```

For different accounts, save separate snapshots:

```bash
preply --role learner snapshot --account-label "Learner" --out data/learner.json
preply --role tutor snapshot --account-label "Tutor" --out data/tutor.json
preply compare data/learner.json data/tutor.json
```

## Commands

- `session capture|list|status`: manage 1Password-stored sessions for the direct
  transport. `capture` decrypts live Chrome sessions and stores the ones that
  authenticate (add `--profile "Profile 2"` to restrict); `list` shows stored
  sessions; `status` probes each for current liveness.
- `account`: show which account the CLI will use (from the stored session or the logged-in tab).
- `me`: one-screen learner dashboard — identity, lifetime stats, hour balance,
  upcoming lessons, recent lessons, upcoming charge dates, unscheduled paid
  hours, and tutors awaiting a first payment. Start here.
- `balance`: learner **hour** balance per tutor — hours banked, how many are
  still unscheduled, how many are tied up in a booked lesson, and the next
  automatic charge date and billing frequency. A tutoring whose subscription was
  stopped shows `NO_SUBSCRIPTION` with no charge date: its hours are paid for and
  will sit idle until booked.
- `renewals`: learner **money** view of subscriptions — what Preply will charge,
  when, for which tutor, in which currency. `balance` answers "how many hours do
  I have"; this answers "how much am I about to pay". Only subscriptions that
  will actually charge are listed: Preply keeps the last charge date and amount
  on a *stopped* subscription, so `--all` is needed to see those. Totals are
  reported per currency and never summed across them.
- `certificates`: learner achievement certificates per subject — hours completed,
  current and next level, hours to the next level, and the download URL.
- `status`: account totals, wallet balance, loaded student revenue total, status counts.
- `students`: student list with tutoring id, subject, price, confirmed lessons, hours, revenue, timezone.
- `schedule`: upcoming class schedule.
- `wallet`: wallet balance, currency, last payout method.
- `messages`: message thread summaries and last-message previews.
- `chat [who]`: full conversation history with one tutor. Run with no argument to
  list contacts; pass a name substring or numeric user id to open a thread.
  `--full` prints complete message text plus each attachment's name and URL,
  `--files` lists just the shared materials, `--limit` pages into older history,
  and `--json` returns messages and files together for offline reasoning.
  Sender is shown as `me`, the tutor's name, `system`, or `unknown` — never
  guessed (see the note below).
- `history`: learner/tutor payment history where Preply exposes it in `settings/history`.
- `lessons`: learner completed-lesson ledger — each row is one real lesson (date,
  subject, tutor, duration, status, paid amount, rating), with a summary. Unlike
  `history` (a billing surface), this is an actual per-lesson event ledger.
- `upcoming`: learner upcoming lessons (booked lessons and recurrent reservations).
- `tutors`: learner active tutors/subscriptions — tutor, subject, price/hour,
  lessons taken, and subscription (refill) state, sorted by lessons taken.
- `stats`: learner lifetime stats — highest lesson streak, lessons completed, practices.
- `confirmation`: show the pending "Did your lesson happen?" prompt. Add `--confirm --yes` to confirm the pending lesson so the tutor can get paid. Use `--lesson-id`, `--expect-tutor`, or `--expect-datetime` as safety guards.
- `tutor-reviews <url-or-id>`: public tutor profile stats, review reasoning, themes, retention, and all reviews by default. Add `--limit 5` to preview only a few rows. Needs no login — it reads the server-rendered profile page of *any* tutor. Supports `--proxy <url>` for restricted networks.
  - Inspects tutor availability status (`accepting_new_students`: `Yes` / `No (Overbooked/Paused)`), status code, and displays a prominent warning banner when overbooked or temporarily paused.
  - Normalizes pricing: displays hourly lesson rate (`hourly_rate`) and short trial rate (`trial_rate`).
  - Each review carries the reviewer's own lesson count and the date of their last lesson, so the output includes a **Recent student lessons** ranking and a **Long-term students** table: who stayed, how many lessons they took, and whether they are still taking them. Reviewers are self-selected, so read it as a floor on repeat business, not a census.
- `tutor-schedule <url-or-id>`: public tutor calendar and booking availability via GraphQL (`BookingTimeslots`). Needs no login. Shows open booking slots (`FREE`), earliest/latest lesson windows, and night-class schedule (18:00 cutoff). Preply's public API returns open slots (booked slots are pruned from public view for privacy); offline fixtures (`-f`) or authenticated feeds can render `BOOKED` slots with initials.
  - Flags: `--date YYYY-MM-DD` (start date, default today), `--days N` (default 7), `--timezone` (default `Asia/Ho_Chi_Minh`), `--duration` (minutes, default 50), `--no-booked` (hide booked slots), `--proxy <url>`, `--json`, `--csv`, `-f <saved_json>`.
- `student <tutoring_id>`: per-student details, statistics, upcoming lessons, past lessons, and revenue history.
- `analyze`: summary plus timeline. Add `--deep` for per-student past lesson fetching.
- `snapshot`: local JSON snapshot for later comparison.
- `compare`: compare saved snapshots from different accounts.

## Notes

- Full chat history **does not require Agora**. `chat` reads message bodies over
  plain GraphQL; Agora carries the live stream, not the archive. Verified on a
  real thread: 85 messages spanning 2024-10-06 to 2026-08-06, fetched in two
  pages, with the final page reporting no more history.
- Attachments shared in a conversation (lesson PDFs, audio, homework) are
  enumerable with `chat <who> --files`: name, MIME type, size, sender, date, and
  an absolute URL. Preply returns these links root-relative
  (`/files/<id>?download=true`), so the CLI makes them absolute; the links still
  require your logged-in session in the browser.
- Chat sender attribution is measured, not inferred. `authorId` is null on about
  two thirds of messages (system notices and Preply's own action cards), so the
  command labels each message `me`, the tutor's name, `system`, or `unknown`, and
  counts anything unattributable in `unknown_sender` rather than assigning it to
  a person.
- Public tutor reviews are read from Preply's public server-rendered profile payload. This command does not need a logged-in Chrome tab and can also read a saved public profile HTML/JSON file.
- `balance` counts **hours, not money**. `hours`, `unscheduled`, and `unavailable`
  map one-to-one onto Preply's own `tutoring.hours`, `unscheduledLessons`, and
  `unavailableLessons` fields; Preply owns their exact semantics. Observed live:
  `unavailable` hours are excluded from `totalBalance`, so the reported balance
  and the per-row hour sum can legitimately differ — `--json` reports both
  (`total_balance_hours` and `summed_row_hours`) rather than reconciling them.
- `renewals` counts **money**, `balance` counts **hours**, and they come from
  different Preply operations. `BalanceManagementData` (behind `balance`) carries
  refill hours and dates but no amount and no currency, so it structurally cannot
  answer "how much will I be charged"; `SettingsTutoringList` (behind `renewals`)
  is the only verified source of `chargeAmount`. A *stopped* subscription keeps
  its final charge date and amount — measured live, 9 of 23 tutorings carried
  dates from 2023–2025 — so those are excluded from the upcoming total and shown
  only under `--all`.
- A `--file` snapshot that is valid JSON but not a Preply snapshot is refused,
  not rendered. Reading one used to print a full report of zeros at exit 0.
- `history` is payment history, not a completed-lesson ledger. Do not use payment-row counts or `hours_total` as lesson frequency without a provider-level one-to-one guarantee. For learner cadence, combine an explicitly dated lesson-note source with a Preply snapshot and label each source's freshness.
- `analyze --deep` exposes event-level past lessons only when tutor-side `student_details` are present; it is not a learner-side historical lesson export.
- `--file` reads an offline snapshot. Include its capture date and account label in any report, and refresh through `account` / `snapshot` before making a current-state claim.
- Lesson confirmation uses Preply's `NextLessonForConfirmation` query and `ConfirmPastLesson` mutation. The default command only displays the pending lesson; mutation requires `--confirm --yes`.
- Exported JSON can contain private student and message data. The `data/` directory is ignored by git.
- Global account selectors must appear before the subcommand, for example `preply --role learner history`, not `preply history --role learner`.

## Development

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests
```

Install first. Running `python3 -m unittest discover -s tests` in a bare clone
collects 21 of 198 tests and reports red — the 15 errors are all one cause
(`No module named 'preply_cli'`), not 15 findings. Without an install, prefix
with `PYTHONPATH=src`.

CI runs the suite against the **built package** on Python 3.11–3.14 across Linux
and macOS, and asserts the collected test count rather than trusting the exit
code: `discover` exits 0 when it finds nothing.

## Safety Model

- The session token is stored **only in 1Password** (the `Agent Automation` vault),
  never in the repo, a dotfile, an env file, or logs. The `direct` transport reads
  it in-process through the 1Password Service Account bridge and never prints it.
  The `browser` transport stores nothing. See [SECURITY.md](SECURITY.md).
- `session capture` performs a one-time, present-user decryption of a live Chrome
  session (one macOS Keychain prompt). Cookie decryption never runs unattended.
- A stored session can go stale (Preply invalidates it server-side on logout).
  `session status` probes liveness; `direct` fails loudly rather than guessing.
- The CLI is read-only by default. Do not add more mutating commands without a separate review and an explicit confirmation gate.
- `confirmation --confirm --yes` confirms the pending lesson and can affect tutor payment. Prefer adding `--lesson-id` and `--expect-tutor` when automating it.
- Keep `data/` exports local and private.

## Full API surface

Commands are wired from a locally-mined catalogue of Preply GraphQL operations
and each one is verified against a live account before shipping.

That catalogue is **not published here**. Shipping this CLI does not require
publishing Preply's private API surface, so the mined operation text is
gitignored and kept local. `docs/reverse-engineering-notes.md` records the
method and the findings without reproducing the operations themselves.

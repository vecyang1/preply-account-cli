# Preply Account CLI

Read-only local CLI for your own Preply tutor and learner accounts. It uses logged-in Preply tabs in Chrome through `browser-harness`, so it does not store cookies, tokens, passwords, or exported account data.

This is an unofficial community tool. Use it only with accounts you own or are authorized to inspect, and respect Preply's terms and privacy requirements.

## Quick Start

1. Install or expose `browser-harness` on `PATH`.
2. Install this CLI:

```bash
python3 -m pip install -e .
```

3. Open Preply in Chrome and make sure the account is logged in.
4. Run:

```bash
preply account
preply --role tutor status
preply --role tutor students
preply --role tutor schedule --days 30
preply --role tutor messages
preply --role tutor analyze
preply --role learner history --limit 100
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

- `account`: show which logged-in Preply tab/account the CLI will use.
- `status`: account totals, wallet balance, loaded student revenue total, status counts.
- `students`: student list with tutoring id, subject, price, confirmed lessons, hours, revenue, timezone.
- `schedule`: upcoming class schedule.
- `wallet`: wallet balance, currency, last payout method.
- `messages`: message thread summaries and last-message previews.
- `history`: learner/tutor payment history where Preply exposes it in `settings/history`.
- `student <tutoring_id>`: per-student details, statistics, upcoming lessons, past lessons, and revenue history.
- `analyze`: summary plus timeline. Add `--deep` for per-student past lesson fetching.
- `snapshot`: local JSON snapshot for later comparison.
- `compare`: compare saved snapshots from different accounts.

## Notes

- Message history is currently a safe metadata/last-message view. Preply full chat history appears to mix GraphQL thread metadata with Agora chat transport, so transcript export should be treated as a separate experimental extension.
- Exported JSON can contain private student and message data. The `data/` directory is ignored by git.
- Global account selectors must appear before the subcommand, for example `preply --role learner history`, not `preply history --role learner`.

## Safety Model

- No credential files, browser cookies, API tokens, or session headers are read from disk or written to the repo.
- All Preply requests run as same-origin browser `fetch()` calls inside an already logged-in Preply tab.
- The CLI is read-only. Do not add mutating commands without a separate review.
- Keep `data/` exports local and private.

# Preply CLI Completion Plan

Goal: make the local Preply CLI role-aware and useful for both the tutor account and the learner account without storing credentials.

## Scope

- Keep all browser access read-only through same-origin `fetch()` inside logged-in Chrome tabs.
- Add account target selection so commands can choose tutor, learner, user id, or visible name when several Preply tabs/accounts exist.
- Add learner payment history export from Preply's `historyWithBilling` and paginated `history` GraphQL operations.
- Preserve tutor commands: status, students, schedule, wallet, messages, student detail, analyze, snapshot, compare.
- Update docs and live verification commands so the next agent can reproduce checks.

## Implementation Tasks

1. Add unit tests for account target selectors and learner payment summary.
2. Add GraphQL operations for account identity and payment history.
3. Thread account selector options through the browser client and CLI.
4. Add `history` command for learner/tutor payment history where available.
5. Add learner snapshot support and compare totals for earned/spent depending on account role.
6. Run unit tests, compile checks, and safe live checks against tutor and learner Chrome targets.

## Verification

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m compileall -q src tests
preply --role tutor status
preply --role learner history --limit 10
preply --role learner snapshot --account-label learner --out data/learner.json
preply --role tutor snapshot --account-label tutor --out data/tutor.json
preply compare data/learner.json data/tutor.json
```

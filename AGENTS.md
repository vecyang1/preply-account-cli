# Preply CLI Agent Notes

This is a local, read-only Preply tutor and learner account CLI.

## Safety

- Do not store cookies, bearer tokens, or session headers.
- Use the logged-in Chrome/Preply tab through `browser-harness`; the CLI executes same-origin `fetch()` inside that tab.
- Treat `data/` snapshots as private student/message data. Keep `data/` ignored and do not commit exports.
- Keep all operations read-only unless the user explicitly asks for a mutating command and approves the exact action.

## Verification

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
preply --version
preply --role tutor status
preply --role tutor students --limit 3
preply --role tutor schedule --days 7
preply --role tutor messages --limit 3
preply --role learner history --limit 5
```

The logged-in Preply page must be open in Chrome before live commands are expected to work.

## Known Limits

- `studentManagementTutorings` silently fails for `count` above 20, so the client paginates in 20-row chunks.
- Several Preply accounts can be open at once. Use global selectors before the command: `--role tutor`, `--role learner`, `--user-id`, or `--name`.
- Learner payment history is available through `historyWithBilling` plus paginated `history(lastId)`.
- Message summaries are available through GraphQL. Full transcript export appears to require additional Agora/chat transport reverse engineering and is intentionally not marked complete here.

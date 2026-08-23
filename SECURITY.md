# Security

This project is for inspection of Preply accounts you own or are authorized to
inspect. It is read-only by default, with one explicitly gated mutation
(lesson confirmation).

## Credential custody (two transports)

The CLI reaches Preply two ways. Both keep secrets out of the repo and off disk
in plaintext.

- **browser** — executes same-origin `fetch()` inside a logged-in Chrome tab via
  `browser-harness`. No cookie is read or stored; the session never leaves Chrome.
- **direct** — replays a stored Preply `sessionid` cookie straight to
  `https://preply.com/graphql/v2`. This is the unattended path. The session token
  is stored **only in 1Password** (the `Agent Automation` vault), one item per
  account, and is read in-process through the 1Password Service Account bridge.
  The token is never written to the repo, a dotfile, an env file, or logs, and is
  never printed to a terminal.

Capture (`preply session capture`) decrypts the live Chrome session once, while
you are present, and writes it to 1Password. This is a deliberate custody choice:
the token lives in a secrets manager instead of a browser tab, so the CLI can run
while you are away. It is the one intentional exception to "do not store tokens".

## What Not To Commit

- Preply exports from `data/` (student names, messages, receipts)
- Browser cookies, session ids, `csrftoken`, or session headers — in any file
- Decrypted cookie values or Keychain output
- 1Password secret values (item *ids* and `op://` references are non-secret and
  may appear in docs; the secret *fields* must never be committed)
- Screenshots containing student names, messages, or receipts

## Handling rules for agents and scripts

- Never print a `sessionid` or `csrftoken` value to stdout/stderr or a report.
  `session_store.read_secret` returns values in memory only.
- Read session secrets through the Service Account bridge (`op read`), not by
  shelling out to bare `op` (which prompts) or by decrypting Chrome on the hot path.
- Chrome cookie decryption (`chrome_cookies.py`) is a present-user setup step; it
  may trigger one macOS Keychain authorization and must not run unattended.

## Mutations

The only state-changing command is `confirmation --confirm --yes`
(`ConfirmPastLesson`), which can trigger tutor payment. It requires explicit
flags and supports `--lesson-id` / `--expect-tutor` / `--expect-datetime` guards.
Do not add mutating commands without a separate review and an explicit
confirmation gate.

## Reporting

If you find a credential exposure or a behavior that mutates Preply account state
unexpectedly, open a private security report or contact the maintainer before
publishing details. If a session token is ever exposed in output or a commit,
revoke it by logging out that Preply session, then re-capture.

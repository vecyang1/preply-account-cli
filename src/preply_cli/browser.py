from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from typing import Any

from .queries import GraphQLOperation


HARNESS_COMMAND = "browser-harness"


class PreplyBrowserError(RuntimeError):
    pass


def harness_available(command: str = HARNESS_COMMAND) -> bool:
    """Whether the browser transport's helper can be found on PATH.

    Exposed so the transport chooser can tell "the browser route is not set up"
    from "the browser route failed while running", instead of discovering it
    only once a command is already mid-flight.
    """
    return shutil.which(command) is not None


@dataclass(frozen=True)
class BrowserTargetSelector:
    role: str = "any"
    user_id: int | None = None
    name: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "user_id": self.user_id,
            "name": self.name,
        }


@dataclass(frozen=True)
class OperationCall:
    key: str
    operation: GraphQLOperation
    variables: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.operation.name,
            "endpoint": self.operation.endpoint,
            "query": self.operation.query,
            "variables": self.variables,
        }


class BrowserHarnessClient:
    marker = "PREPLY_CLI_RESULT="

    def __init__(
        self,
        command: str = HARNESS_COMMAND,
        timeout: int = 90,
        selector: BrowserTargetSelector | None = None,
        fallback_note: str | None = None,
    ):
        self.command = command
        self.timeout = timeout
        self.selector = selector or BrowserTargetSelector()
        # Why this transport is in use at all. Set when `--transport auto` fell
        # back here because the direct route was unavailable: if the browser
        # route then fails too, the user needs both halves, not just this one.
        self.fallback_note = fallback_note

    def fetch_graphql(self, calls: list[OperationCall]) -> dict[str, Any]:
        try:
            return self._fetch_graphql(calls)
        except PreplyBrowserError as exc:
            if not self.fallback_note:
                raise
            # `auto` chose this transport only because direct was unavailable.
            # Reporting the browser failure alone describes the second-choice
            # route's symptom while hiding the first choice's cause.
            raise PreplyBrowserError(
                f"{exc}\n(the direct transport was skipped first: {self.fallback_note})"
            ) from exc

    def _fetch_graphql(self, calls: list[OperationCall]) -> dict[str, Any]:
        if not harness_available(self.command):
            raise PreplyBrowserError(
                f"{self.command} is not on PATH. Install/connect {self.command}, then open a logged-in Preply tab."
            )
        script = self._script([call.as_payload() for call in calls], self.selector.as_payload())
        try:
            proc = subprocess.run(
                [self.command],
                input=script,
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # Was an unguarded traceback at exit 1 after a 90s wait.
            raise PreplyBrowserError(
                f"{self.command} did not respond within {self.timeout}s. "
                "Check that Chrome is running with a logged-in Preply tab."
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise PreplyBrowserError(detail or f"{self.command} exited with {proc.returncode}")
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith(self.marker):
                try:
                    payload = json.loads(line[len(self.marker) :])
                except json.JSONDecodeError as exc:
                    raise PreplyBrowserError(
                        f"{self.command} returned a malformed CLI payload: {exc.msg}"
                    ) from exc
                if payload.get("ok"):
                    return payload["data"]
                raise PreplyBrowserError(payload.get("error") or "Preply browser request failed")
        raise PreplyBrowserError(f"{self.command} did not return a Preply CLI payload")

    def _script(self, operations: list[dict[str, Any]], selector: dict[str, Any]) -> str:
        operations_json = json.dumps(operations)
        selector_json = json.dumps(selector)
        return textwrap.dedent(
            f"""
            import json

            operations = json.loads({operations_json!r})
            selector = json.loads({selector_json!r})

            def emit(payload):
                print({self.marker!r} + json.dumps(payload, ensure_ascii=False))

            try:
                identity_query = '''
                query PreplyCliAccountIdentity {{
                  currentUser {{
                    id
                    firstName
                    fullName
                    tutor {{ id }}
                    profile {{ id timezone {{ tzname }} currency {{ code }} }}
                    wallet {{ id balance }}
                  }}
                }}
                '''

                def read_identity(session_id):
                    expression = '''
                    (async () => {{
                      const response = await fetch('/graphql/v2/PreplyCliAccountIdentity', {{
                        method: 'POST',
                        credentials: 'include',
                        headers: {{ 'content-type': 'application/json' }},
                        body: JSON.stringify({{
                          operationName: 'PreplyCliAccountIdentity',
                          variables: {{}},
                          query: %s
                        }})
                      }});
                      return await response.text();
                    }})()
                    ''' % json.dumps(identity_query)
                    response = cdp(
                        'Runtime.evaluate',
                        session_id=session_id,
                        expression=expression,
                        returnByValue=True,
                        awaitPromise=True,
                    )
                    raw = response.get('result', {{}}).get('value')
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                    if payload.get('errors'):
                        raise RuntimeError(json.dumps(payload.get('errors'))[:600])
                    user = (payload.get('data') or {{}}).get('currentUser') or {{}}
                    user['preplyCliRole'] = 'tutor' if user.get('tutor') else 'learner'
                    return user

                def identity_matches(identity):
                    wanted_role = selector.get('role') or 'any'
                    if wanted_role != 'any' and identity.get('preplyCliRole') != wanted_role:
                        return False
                    wanted_user_id = selector.get('user_id')
                    if wanted_user_id is not None and int(identity.get('id') or -1) != int(wanted_user_id):
                        return False
                    wanted_name = (selector.get('name') or '').strip().lower()
                    full_name = str(identity.get('fullName') or identity.get('firstName') or '').lower()
                    if wanted_name and wanted_name not in full_name:
                        return False
                    return True

                targets = cdp('Target.getTargets').get('targetInfos', [])
                candidates = [
                    t for t in targets
                    if 'preply.com' in (t.get('url') or '')
                    and '/login' not in (t.get('url') or '')
                    and (t.get('type') == 'page')
                ]
                if not candidates:
                    raise RuntimeError('Open a logged-in Preply tab first, then rerun this command.')
                candidates.sort(key=lambda t: (
                    0 if '/home' in (t.get('url') or '') else 1,
                    0 if t.get('attached') else 1,
                ))
                detected = []
                matches = []
                for candidate in candidates:
                    candidate_session_id = cdp('Target.attachToTarget', targetId=candidate['targetId'], flatten=True).get('sessionId')
                    try:
                        identity = read_identity(candidate_session_id)
                    except Exception as identity_error:
                        detected.append({{
                            'url': candidate.get('url'),
                            'error': str(identity_error),
                        }})
                        continue
                    detected.append({{
                        'url': candidate.get('url'),
                        'user_id': identity.get('id'),
                        'name': identity.get('fullName') or identity.get('firstName'),
                        'role': identity.get('preplyCliRole'),
                        'attached': candidate.get('attached'),
                    }})
                    if identity_matches(identity):
                        matches.append((candidate, candidate_session_id, identity))
                if not matches:
                    readable = [d for d in detected if 'error' not in d]
                    if detected and not readable:
                        raise RuntimeError(
                            'Found ' + str(len(detected)) + ' Preply tab(s), but none answered as a '
                            'logged-in account. Log in to Preply in Chrome, then rerun. Detail: '
                            + json.dumps(detected, ensure_ascii=False)
                        )
                    raise RuntimeError('No Preply tab matched selector ' + json.dumps(selector) + '; detected ' + json.dumps(detected, ensure_ascii=False))
                # Several tabs of the *same* account are not ambiguous; several
                # accounts are. The direct transport already refuses this case,
                # and picking silently here would show one account's private
                # data under the other's name -- the tab that happened to be on
                # /home won, purely because of the sort above.
                distinct = sorted(set(str(m[2].get('id')) for m in matches))
                if len(distinct) > 1:
                    listing = ', '.join(
                        str(m[2].get('fullName') or m[2].get('firstName'))
                        + '(' + str(m[2].get('preplyCliRole')) + '/' + str(m[2].get('id')) + ')'
                        for m in matches
                    )
                    raise RuntimeError(
                        'Selector ' + json.dumps(selector) + ' is ambiguous across '
                        + str(len(distinct)) + ' Preply accounts: ' + listing
                        + '. Narrow it with --role, --user-id or --name.'
                    )
                target, session_id, identity = matches[0]
                operations_json = json.dumps(operations, ensure_ascii=False)
                expression = '''
                (async () => {{
                  const operations = JSON.parse(%s);
                  const result = {{}};
                  for (const op of operations) {{
                    const response = await fetch(op.endpoint, {{
                      method: 'POST',
                      credentials: 'include',
                      headers: {{ 'content-type': 'application/json' }},
                      body: JSON.stringify({{
                        operationName: op.name,
                        variables: op.variables || {{}},
                        query: op.query
                      }})
                    }});
                    const text = await response.text();
                    let payload;
                    try {{
                      payload = JSON.parse(text);
                    }} catch (error) {{
                      payload = {{ raw: text }};
                    }}
                    if (!response.ok || payload.errors) {{
                      throw new Error(op.name + ': ' + JSON.stringify(payload).slice(0, 1200));
                    }}
                    result[op.key] = payload.data;
                  }}
                  return JSON.stringify(result);
                }})()
                ''' % json.dumps(operations_json, ensure_ascii=False)
                response = cdp(
                    'Runtime.evaluate',
                    session_id=session_id,
                    expression=expression,
                    returnByValue=True,
                    awaitPromise=True,
                )
                raw_value = response.get('result', {{}}).get('value')
                if raw_value is None:
                    raise RuntimeError('Preply returned no data. Make sure the logged-in tab is still active.')
                value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                value['_account'] = {{
                    'targetUrl': target.get('url'),
                    'userId': identity.get('id'),
                    'name': identity.get('fullName') or identity.get('firstName'),
                    'role': identity.get('preplyCliRole'),
                    'tutorId': (identity.get('tutor') or {{}}).get('id'),
                }}
                emit({{'ok': True, 'data': value}})
            except Exception as exc:
                emit({{'ok': False, 'error': str(exc)}})
            """
        )

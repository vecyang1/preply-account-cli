"""The Preply GraphQL operations this CLI sends.

Split by whose account the operation reads, because that is the axis that
decides whether a shape is *verified*: learner operations are checked against a
live learner account before shipping, tutor operations cannot be (no tutor
session exists) and their shapes remain unconfirmed.

Query text is mined from Preply's public JS bundles; the catalogue those come
from is deliberately not published with this repository. See
``docs/reverse-engineering-notes.md``.

The public surface is unchanged from when this was a single module:
``GraphQLOperation``, ``OPERATIONS``, ``get_operation``, ``operation_names``.
"""

from __future__ import annotations

from ._operation import GraphQLOperation
from .learner import OPERATIONS as _LEARNER
from .shared import OPERATIONS as _SHARED
from .tutor import OPERATIONS as _TUTOR

OPERATIONS: dict[str, GraphQLOperation] = {**_SHARED, **_TUTOR, **_LEARNER}

# A name defined in two groups would be silently shadowed by the merge above,
# and the loser could differ from the document that was actually verified.
_expected = len(_SHARED) + len(_TUTOR) + len(_LEARNER)
if len(OPERATIONS) != _expected:
    _seen: set[str] = set()
    _clashes = sorted(
        name
        for group in (_SHARED, _TUTOR, _LEARNER)
        for name in group
        if name in _seen or _seen.add(name)  # type: ignore[func-returns-value]
    )
    raise RuntimeError(f"duplicate operation name(s) across query modules: {_clashes}")


def get_operation(name: str) -> GraphQLOperation:
    return OPERATIONS[name]


def operation_names() -> list[str]:
    return sorted(OPERATIONS)


__all__ = ["GraphQLOperation", "OPERATIONS", "get_operation", "operation_names"]

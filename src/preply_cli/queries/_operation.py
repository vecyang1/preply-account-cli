"""The operation record every query module builds on."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphQLOperation:
    name: str
    query: str

    @property
    def endpoint(self) -> str:
        return f"/graphql/v2/{self.name}"

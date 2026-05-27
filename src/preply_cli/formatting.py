from __future__ import annotations

from collections.abc import Iterable


def redact_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    prefix = local[:1] or "*"
    return f"{prefix}***@{domain}"


def money(value: object, currency: str = "USD") -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{amount:.2f} {currency}"


def shorten(value: object, width: int = 72) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)].rstrip() + "…"


def format_table(rows: Iterable[dict[str, object]], columns: list[str]) -> str:
    rows = list(rows)
    widths = {column: len(column) for column in columns}
    for row in rows:
        for column in columns:
            widths[column] = max(widths[column], len(shorten(row.get(column), 80)))

    def line(row: dict[str, object]) -> str:
        return "  ".join(shorten(row.get(column), 80).ljust(widths[column]) for column in columns)

    header = "  ".join(column.ljust(widths[column]) for column in columns)
    rule = "  ".join("-" * widths[column] for column in columns)
    body = [line(row) for row in rows]
    return "\n".join([header, rule, *body]) if rows else "\n".join([header, rule])

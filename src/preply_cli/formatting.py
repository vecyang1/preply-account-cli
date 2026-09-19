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


def format_datetime_local(dt_str: object, tzname: str | None = None) -> str:
    """Format an ISO datetime string into human-readable local or specified timezone.

    Examples:
        '2026-09-21T14:00:00+00:00' with +08 -> '2026-09-21 22:00 (UTC+08)'
        '2026-09-21T14:00:00+00:00' with Asia/Ho_Chi_Minh -> '2026-09-21 21:00 (UTC+07)'
        Fallback to original string on parsing error.
    """
    if not dt_str:
        return ""
    val_str = str(dt_str).strip()
    if not val_str:
        return ""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
        if tzname and str(tzname).lower() != "local":
            tz = ZoneInfo(str(tzname))
            loc = dt.astimezone(tz)
        else:
            loc = dt.astimezone()  # system local timezone
        offset_str = loc.strftime("%z")
        if len(offset_str) == 5:
            offset_display = (
                f"UTC{offset_str[:3]}"
                if offset_str[3:] == "00"
                else f"UTC{offset_str[:3]}:{offset_str[3:]}"
            )
        else:
            offset_display = loc.tzname() or ""
        return loc.strftime(f"%Y-%m-%d %H:%M ({offset_display})")
    except Exception:
        return val_str


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


def format_csv(rows: Iterable[dict[str, object]], columns: list[str]) -> str:
    import csv
    import io
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        formatted_row = {}
        for col in columns:
            val = row.get(col)
            formatted_row[col] = "" if val is None else str(val)
        writer.writerow(formatted_row)
    return output.getvalue()

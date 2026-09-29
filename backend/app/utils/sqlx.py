"""Small dialect helpers for grouping timestamps in the shop's local time."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session


def utc_offset_minutes(tz: ZoneInfo, at: datetime | None = None) -> int:
    at = at or datetime.now(UTC)
    off = at.astimezone(tz).utcoffset() or timedelta(0)
    return int(off.total_seconds() // 60)


def local_bucket(db: Session, column, offset_minutes: int, granularity: str):  # noqa: ANN001, ANN201
    """SQL expression that maps a UTC timestamp to a local 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY' / hour bucket string."""
    fmt = {"hour": ("%Y-%m-%d %H:00", "YYYY-MM-DD HH24:00"), "day": ("%Y-%m-%d", "YYYY-MM-DD"),
           "month": ("%Y-%m", "YYYY-MM"), "year": ("%Y", "YYYY")}
    if granularity == "week":
        # ISO-like week start (Monday) as a date string
        if db.get_bind().dialect.name == "sqlite":
            shifted = func.date(column, f"{offset_minutes:+d} minutes")
            return func.date(shifted, "weekday 0", "-6 days")
        return func.to_char(func.date_trunc("week", column + timedelta(minutes=offset_minutes)), "YYYY-MM-DD")
    sqlite_fmt, pg_fmt = fmt[granularity]
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime(sqlite_fmt, column, f"{offset_minutes:+d} minutes")
    return func.to_char(column + timedelta(minutes=offset_minutes), pg_fmt)

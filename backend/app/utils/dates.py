from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.errors import ValidationFailed

DEFAULT_TZ = "Asia/Dhaka"


def get_tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except Exception:  # unknown timezone name / missing tzdata
        return ZoneInfo(DEFAULT_TZ)


def to_utc_naive(local_dt: datetime, tz: ZoneInfo) -> datetime:
    return local_dt.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def local_today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def day_bounds(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """UTC-naive [start, end) covering the shop-local calendar day."""
    start = to_utc_naive(datetime.combine(d, time.min), tz)
    end = to_utc_naive(datetime.combine(d + timedelta(days=1), time.min), tz)
    return start, end


def range_bounds(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    if end < start:
        raise ValidationFailed("End date must not be before start date")
    return day_bounds(start, tz)[0], day_bounds(end, tz)[1]


def resolve_period(
    period: str | None, start: date | None, end: date | None, tz: ZoneInfo
) -> tuple[date, date]:
    """Inclusive local date range for named periods used by the dashboard and reports."""
    today = local_today(tz)
    period = (period or "today").lower()
    if period == "today":
        return today, today
    if period == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if period in ("last_7_days", "7d"):
        return today - timedelta(days=6), today
    if period in ("last_30_days", "30d"):
        return today - timedelta(days=29), today
    if period == "this_week":
        return today - timedelta(days=today.weekday()), today
    if period == "this_month":
        return today.replace(day=1), today
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    if period == "this_year":
        return today.replace(month=1, day=1), today
    if period == "custom" or (start and end):
        if not start or not end:
            raise ValidationFailed("Custom range requires start and end dates")
        return start, end
    if period == "all":
        return date(2000, 1, 1), today
    raise ValidationFailed(f"Unknown period '{period}'")

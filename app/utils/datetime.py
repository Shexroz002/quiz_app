from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

APP_TIME_ZONE = "Asia/Tashkent"
APP_TZ = ZoneInfo(APP_TIME_ZONE)
UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc_datetime(value: datetime, assume_tz=APP_TZ) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=assume_tz).astimezone(UTC)
    return value.astimezone(UTC)


def as_tashkent_datetime(value: datetime, assume_tz=APP_TZ) -> datetime:
    return as_utc_datetime(value, assume_tz=assume_tz).astimezone(APP_TZ)


def tashkent_now() -> datetime:
    return utc_now().astimezone(APP_TZ)


def tashkent_day_end_utc(days_ago: int = 0) -> datetime:
    local_now = tashkent_now()
    local_day = local_now.date() - timedelta(days=days_ago)
    return datetime.combine(local_day, time.max, tzinfo=APP_TZ).astimezone(UTC)


def tashkent_week_start_utc(reference: datetime | None = None) -> datetime:
    local_reference = as_tashkent_datetime(reference) if reference else tashkent_now()
    week_start_date = local_reference.date() - timedelta(days=local_reference.weekday())
    return datetime.combine(week_start_date, time.min, tzinfo=APP_TZ).astimezone(UTC)

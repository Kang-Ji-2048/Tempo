"""UTC sensor sample timestamps. Receipt time must never substitute for one."""
from datetime import datetime, timezone


def normalize(value):
    if not isinstance(value, str):
        raise ValueError('sampled_at must be an ISO 8601 timestamp including a timezone')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('sampled_at must be ISO 8601') from exc
    if parsed.tzinfo is None:
        raise ValueError('sampled_at must include a timezone')
    return parsed.astimezone(timezone.utc).isoformat()


def require_recent(value, max_age_seconds=300):
    normalized = normalize(value)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(normalized)).total_seconds()
    if age < -30 or age > max_age_seconds:
        raise ValueError('Watch sample is stale or in the future. Run the iPhone Shortcut for a recent reading.')
    return normalized

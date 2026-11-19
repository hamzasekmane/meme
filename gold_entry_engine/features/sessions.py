"""Timezone-aware session windows, including daylight-saving transitions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

DEFAULT_SESSIONS = {
    "Asia": {"timezone": "UTC", "start": "00:00", "end": "09:00"},
    "London": {"timezone": "Europe/London", "start": "08:00", "end": "17:00"},
    "New_York": {"timezone": "America/New_York", "start": "08:00", "end": "17:00"},
}


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Invalid session time: {value}") from exc


def active_session_flags(
    index: pd.DatetimeIndex,
    sessions: Mapping[str, Mapping[str, str]] | None = None,
) -> pd.DataFrame:
    """Return one boolean column per active session; overlaps are preserved."""
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("Session features require a DatetimeIndex")
    if index.tz is None:
        raise ValueError("Session timestamps must be timezone-aware")
    definitions = sessions or DEFAULT_SESSIONS
    flags: dict[str, list[bool]] = {}
    utc_index = index.tz_convert("UTC")
    for name, definition in definitions.items():
        try:
            zone = ZoneInfo(str(definition.get("timezone", "UTC")))
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone for session {name}: {definition.get('timezone')}") from exc
        start = _parse_time(definition["start"])
        end = _parse_time(definition["end"])
        column: list[bool] = []
        for timestamp in utc_index:
            local_time = timestamp.tz_convert(zone).time().replace(tzinfo=None)
            if start <= end:
                column.append(start <= local_time < end)
            else:  # Overnight window, e.g. 22:00 through 06:00.
                column.append(local_time >= start or local_time < end)
        flags[str(name)] = column
    return pd.DataFrame(flags, index=index)


def classify_session(
    timestamp: pd.Timestamp,
    sessions: Mapping[str, Mapping[str, str]] | None = None,
    *,
    priority: tuple[str, ...] = ("New_York", "London", "Asia"),
) -> str:
    """Return the highest-priority active session, ``"Off"`` if none applies."""
    stamp = pd.Timestamp(timestamp)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    flags = active_session_flags(pd.DatetimeIndex([stamp]), sessions).iloc[0]
    for name in priority:
        if name in flags.index and bool(flags[name]):
            return name
    for name, active in flags.items():
        if bool(active):
            return str(name)
    return "Off"

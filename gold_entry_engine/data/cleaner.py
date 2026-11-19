"""OHLCV validation, timestamp normalization, duplicate handling, and gap reports."""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

_REQUIRED = ("open", "high", "low", "close")
_ALIASES = {
    "date": "time",
    "datetime": "time",
    "timestamp": "time",
    "tick_volume": "volume",
    "real_volume": "volume",
}


def _utc_index(values: Any, source_timezone: str) -> pd.DatetimeIndex:
    """Parse timestamps and interpret naive values in the declared source zone."""
    parsed = pd.to_datetime(values, errors="coerce")
    if isinstance(parsed, pd.Series):
        if parsed.isna().any():
            raise ValueError("One or more timestamps could not be parsed")
        zone = parsed.dt.tz
        if zone is None:
            parsed = parsed.dt.tz_localize(
                source_timezone, ambiguous="NaT", nonexistent="shift_forward"
            )
        if parsed.isna().any():
            raise ValueError("One or more timestamps are ambiguous in the source timezone")
        parsed = parsed.dt.tz_convert("UTC")
        return pd.DatetimeIndex(parsed, name="time")

    index = pd.DatetimeIndex(parsed)
    if index.isna().any():
        raise ValueError("One or more timestamps could not be parsed")
    if index.tz is None:
        index = index.tz_localize(
            source_timezone, ambiguous="NaT", nonexistent="shift_forward"
        )
    if index.isna().any():
        raise ValueError("One or more timestamps are ambiguous in the source timezone")
    return index.tz_convert("UTC").rename("time")


def clean_ohlcv(
    data: pd.DataFrame,
    *,
    timestamp_column: str | None = None,
    source_timezone: str = "UTC",
    drop_invalid: bool = True,
) -> pd.DataFrame:
    """Return chronologically sorted, UTC-indexed OHLCV bars.

    Duplicate timestamps keep the last row after a stable sort. Invalid OHLC
    geometry/non-finite rows are dropped with a warning by default; pass
    ``drop_invalid=False`` to fail fast. Missing intervals are never synthesized.
    Auxiliary columns such as a broker's ``spread`` are retained when numeric.
    """
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("OHLCV input must be a non-empty pandas DataFrame")

    frame = data.copy()
    normalized_names = {column: str(column).strip().lower() for column in frame.columns}
    volume_columns = [
        column for column, normalized in normalized_names.items()
        if normalized in ("volume", "tick_volume", "real_volume")
    ]
    volume_source = None
    for preferred in ("volume", "tick_volume", "real_volume"):
        volume_source = next(
            (column for column in volume_columns if normalized_names[column] == preferred),
            None,
        )
        if volume_source is not None:
            break
    drop_columns = [column for column in volume_columns if column != volume_source]
    if drop_columns:
        frame = frame.drop(columns=drop_columns)
    rename: dict[Any, str] = {}
    for original, normalized in normalized_names.items():
        if original in drop_columns:
            continue
        target = "volume" if original == volume_source else _ALIASES.get(normalized, normalized)
        if target != original:
            rename[original] = target
    frame = frame.rename(columns=rename)

    selected_time = timestamp_column
    if selected_time is None:
        for candidate in ("time", "timestamp", "datetime", "date"):
            if candidate in frame.columns:
                selected_time = candidate
                break
    if selected_time is not None:
        if selected_time not in frame.columns:
            # The caller may name a column using its pre-normalized spelling.
            selected_time = _ALIASES.get(str(selected_time).lower(), str(selected_time).lower())
        if selected_time not in frame.columns:
            raise ValueError(f"Timestamp column not found: {timestamp_column}")
        index = _utc_index(frame.pop(selected_time), source_timezone)
    elif isinstance(frame.index, pd.DatetimeIndex):
        index = _utc_index(frame.index, source_timezone)
    else:
        raise ValueError("Provide a timestamp column or a DatetimeIndex")

    frame.index = index
    frame.index.name = "time"
    frame.columns = [str(column).strip().lower() for column in frame.columns]

    missing = [column for column in _REQUIRED if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing OHLC columns: {', '.join(missing)}")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0

    # Prefer tick volume when a source exposes both broker volume fields.
    for column in (*_REQUIRED, "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in frame.columns.difference([*_REQUIRED, "volume"]):
        if not pd.api.types.is_numeric_dtype(frame[column]):
            converted = pd.to_numeric(frame[column], errors="coerce")
            if converted.notna().any():
                frame[column] = converted

    values = frame.loc[:, [*_REQUIRED, "volume"]].to_numpy(dtype=float)
    finite = np.isfinite(values).all(axis=1)
    geometry = (
        (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["high"] >= frame["low"])
        & (frame["volume"] >= 0)
    ).to_numpy()
    valid = finite & geometry
    if not valid.all():
        count = int((~valid).sum())
        if not drop_invalid:
            raise ValueError(f"Found {count} invalid OHLCV row(s)")
        warnings.warn(f"Dropped {count} invalid OHLCV row(s)", RuntimeWarning, stacklevel=2)
        frame = frame.loc[valid]

    frame = frame.sort_index(kind="stable")
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    if frame.empty:
        raise ValueError("No valid OHLCV rows remain after cleaning")
    return frame


def find_gaps(data: pd.DataFrame, expected_interval: str | pd.Timedelta) -> pd.DataFrame:
    """Report observed intervals longer than expected without filling them.

    The returned rows identify the bar after each gap and include the elapsed
    duration and approximate number of missing bars. Session/weekend closures
    are intentionally reported too; callers decide whether they are expected.
    """
    if not isinstance(data.index, pd.DatetimeIndex) or len(data.index) < 2:
        return pd.DataFrame(columns=["previous_time", "elapsed", "missing_bars"])
    expected = pd.Timedelta(expected_interval)
    if expected <= pd.Timedelta(0):
        raise ValueError("expected_interval must be positive")
    elapsed = data.index.to_series().diff()
    mask = elapsed > expected
    gaps = pd.DataFrame(index=data.index[mask])
    gaps["previous_time"] = data.index.to_series().shift(1).loc[mask].to_numpy()
    gaps["elapsed"] = elapsed.loc[mask].to_numpy()
    gaps["missing_bars"] = (elapsed.loc[mask] / expected).round().astype(int) - 1
    gaps.index.name = "next_time"
    return gaps

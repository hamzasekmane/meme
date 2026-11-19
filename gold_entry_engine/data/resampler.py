"""UTC-aligned OHLCV resampling for common intraday and calendar frames."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

_TIMEFRAME_RULES = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1D",
    "W1": "1W",
}


def timeframe_duration(timeframe: str) -> pd.Timedelta:
    """Return the fixed duration for a supported frame (calendar months excluded)."""
    key = str(timeframe).upper()
    if key not in _TIMEFRAME_RULES:
        try:
            return pd.Timedelta(timeframe)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unsupported timeframe: {timeframe}") from exc
    if key == "W1":
        return pd.Timedelta(days=7)
    return pd.Timedelta(_TIMEFRAME_RULES[key])


def timeframe_rule(timeframe: str) -> str:
    key = str(timeframe).upper()
    if key in _TIMEFRAME_RULES:
        return _TIMEFRAME_RULES[key]
    # Allow pandas rules such as "2h" or "45min", but reject month/quarter rules.
    if any(token in key for token in ("MO", "MONTH", "Q", "Y", "A")):
        raise ValueError("Calendar-month/year resampling is not supported")
    try:
        rule = pd.tseries.frequencies.to_offset(timeframe)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe}") from exc
    if rule.nanos <= 0:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return rule.freqstr


def _aggregation(frame: pd.DataFrame) -> dict[str, str]:
    result = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if "spread" in frame.columns:
        # Keep the worst observed spread for a conservative aggregate filter.
        result["spread"] = "max"
    for column in frame.columns:
        if column not in result and column not in {"open", "high", "low", "close", "volume"}:
            result[column] = "last"
    return result


def resample_ohlcv(
    frame: pd.DataFrame,
    timeframe: str,
    *,
    source_timeframe: str | None = None,
    complete_only: bool = False,
) -> pd.DataFrame:
    """Build candles using left-labeled, left-closed UTC buckets.

    By default a partial first/last bucket is retained. Set ``complete_only``
    when ``source_timeframe`` is known to drop groups that contain fewer rows
    than expected. This simple count rule is best suited to continuous feeds;
    exchange/FX session closures should be reviewed before enabling it.
    """
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("Input bars must use a DatetimeIndex")
    if frame.empty:
        return frame.copy()
    target = timeframe_rule(timeframe)
    rule_delta = timeframe_duration(timeframe)
    source_delta = timeframe_duration(source_timeframe) if source_timeframe else None
    if source_delta is not None and source_delta > rule_delta:
        raise ValueError("Cannot upsample a coarser source timeframe")
    if complete_only and source_delta is None:
        raise ValueError("source_timeframe is required when complete_only=True")
    if source_delta is not None and rule_delta.value % source_delta.value != 0:
        raise ValueError("Target timeframe must be an integer multiple of source timeframe")

    resampler = frame.resample(target, label="left", closed="left", origin="start_day")
    bars = resampler.agg(_aggregation(frame))
    bars = bars.dropna(subset=["open", "high", "low", "close"])
    if complete_only and source_delta is not None:
        expected = int(rule_delta / source_delta)
        count = frame["close"].resample(target, label="left", closed="left", origin="start_day").count()
        bars = bars.loc[count.reindex(bars.index, fill_value=0) >= expected]
    bars.index.name = frame.index.name or "time"
    return bars


def build_timeframes(
    frame: pd.DataFrame,
    timeframes: Iterable[str] = ("M5", "M15", "H1", "H4", "D1"),
    *,
    source_timeframe: str,
    complete_only: bool = False,
) -> dict[str, pd.DataFrame]:
    """Return one independently resampled DataFrame per requested timeframe."""
    result: dict[str, pd.DataFrame] = {}
    source_duration = timeframe_duration(source_timeframe)
    for timeframe in timeframes:
        if timeframe_duration(timeframe) < source_duration:
            raise ValueError(f"{timeframe} is finer than source timeframe {source_timeframe}")
        result[str(timeframe).upper()] = resample_ohlcv(
            frame,
            timeframe,
            source_timeframe=source_timeframe,
            complete_only=complete_only,
        )
    return result

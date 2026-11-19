"""Confirmed swing points and close-based BOS/CHoCH labels.

A pivot at bar ``i`` is exposed only on bar ``i + right`` after its right-side
confirmation candles have closed. This keeps downstream logic from using future
bars to label earlier decisions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _validate_bars(frame: pd.DataFrame) -> None:
    missing = {"high", "low", "close"}.difference(frame.columns)
    if missing:
        raise ValueError(f"Bars are missing columns: {sorted(missing)}")


def detect_swings(frame: pd.DataFrame, *, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Return swing events indexed by their confirmation bar, not pivot bar.

    Equal highs/lows do not qualify as strict swing points. Pivot timestamps are
    retained separately so callers can distinguish formation from confirmation.
    """
    _validate_bars(frame)
    if left < 1 or right < 1:
        raise ValueError("left and right must both be at least one")
    length = len(frame)
    swing_high = np.full(length, np.nan)
    swing_low = np.full(length, np.nan)
    high_pivot = np.full(length, np.datetime64("NaT"), dtype="datetime64[ns]")
    low_pivot = np.full(length, np.datetime64("NaT"), dtype="datetime64[ns]")
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    timestamps = frame.index

    for pivot in range(left, length - right):
        left_highs = highs[pivot - left : pivot]
        right_highs = highs[pivot + 1 : pivot + right + 1]
        left_lows = lows[pivot - left : pivot]
        right_lows = lows[pivot + 1 : pivot + right + 1]
        confirmed_at = pivot + right
        if highs[pivot] > left_highs.max() and highs[pivot] > right_highs.max():
            swing_high[confirmed_at] = highs[pivot]
            high_pivot[confirmed_at] = timestamps[pivot].to_datetime64().astype("datetime64[ns]")
        if lows[pivot] < left_lows.min() and lows[pivot] < right_lows.min():
            swing_low[confirmed_at] = lows[pivot]
            low_pivot[confirmed_at] = timestamps[pivot].to_datetime64().astype("datetime64[ns]")

    # Preserve timezone-aware timestamps in object columns rather than stripping
    # the UTC zone from the pivot metadata.
    high_times = [pd.NaT] * length
    low_times = [pd.NaT] * length
    for index in range(length):
        if not np.isnat(high_pivot[index]):
            high_times[index] = timestamps[index - right]
        if not np.isnat(low_pivot[index]):
            low_times[index] = timestamps[index - right]
    return pd.DataFrame(
        {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "swing_high_pivot_time": high_times,
            "swing_low_pivot_time": low_times,
        },
        index=frame.index,
    )


def market_structure(frame: pd.DataFrame, *, left: int = 2, right: int = 2) -> pd.DataFrame:
    """Label first close-throughs of known swings as BOS or CHoCH.

    Break checks use levels known before the current bar's newly confirmed pivots
    are incorporated. A single level can be broken once; a fresh confirmed swing
    resets that side's break state.
    """
    _validate_bars(frame)
    swings = detect_swings(frame, left=left, right=right)
    length = len(frame)
    close = frame["close"].to_numpy(dtype=float)
    last_high = np.full(length, np.nan)
    last_low = np.full(length, np.nan)
    event = np.full(length, "", dtype=object)
    direction = np.zeros(length, dtype=np.int8)
    high_level = np.nan
    low_level = np.nan
    high_broken = False
    low_broken = False
    trend = 0

    for index in range(length):
        previous_close = close[index - 1] if index else np.nan
        break_up = (
            np.isfinite(high_level)
            and not high_broken
            and close[index] > high_level
            and (not np.isfinite(previous_close) or previous_close <= high_level)
        )
        break_down = (
            np.isfinite(low_level)
            and not low_broken
            and close[index] < low_level
            and (not np.isfinite(previous_close) or previous_close >= low_level)
        )
        if break_up and not break_down:
            event[index] = "BOS_UP" if trend >= 0 else "CHOCH_UP"
            trend = 1
            high_broken = True
        elif break_down and not break_up:
            event[index] = "BOS_DOWN" if trend <= 0 else "CHOCH_DOWN"
            trend = -1
            low_broken = True
        elif break_up and break_down:
            event[index] = "DUAL_BREAK"

        # A pivot is usable from its confirmation candle onward.
        new_high = swings["swing_high"].iloc[index]
        new_low = swings["swing_low"].iloc[index]
        if np.isfinite(new_high):
            high_level = float(new_high)
            high_broken = False
        if np.isfinite(new_low):
            low_level = float(new_low)
            low_broken = False
        last_high[index] = high_level
        last_low[index] = low_level
        direction[index] = trend

    return pd.DataFrame(
        {
            "swing_high": swings["swing_high"],
            "swing_low": swings["swing_low"],
            "swing_high_pivot_time": swings["swing_high_pivot_time"],
            "swing_low_pivot_time": swings["swing_low_pivot_time"],
            "last_swing_high": last_high,
            "last_swing_low": last_low,
            "structure_event": event,
            "structure_direction": direction,
        },
        index=frame.index,
    )

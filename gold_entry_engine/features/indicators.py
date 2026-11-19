"""Vectorized, closed-bar technical indicators with explicit warm-up NaNs."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _positive_period(period: int) -> int:
    if not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    return period


def true_range(frame: pd.DataFrame) -> pd.Series:
    """Wilder true range, including the first candle's high-low range."""
    required = {"high", "low", "close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Bars must contain {sorted(required)}")
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    result = ranges.max(axis=1, skipna=True).astype(float)
    result.name = "true_range"
    return result


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR using the classic SMA seed followed by Wilder smoothing."""
    period = _positive_period(period)
    tr = true_range(frame).to_numpy(dtype=float)
    values = np.full(len(tr), np.nan, dtype=float)
    if len(tr) >= period:
        seed = tr[:period]
        if np.isfinite(seed).all():
            values[period - 1] = float(seed.mean())
            for index in range(period, len(tr)):
                if np.isfinite(tr[index]):
                    values[index] = values[index - 1] + (tr[index] - values[index - 1]) / period
    result = pd.Series(values, index=frame.index, name=f"atr_{period}")
    return result


def ema(values: pd.Series, period: int) -> pd.Series:
    """Exponential moving average with a full-period warm-up."""
    period = _positive_period(period)
    result = values.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()
    result.name = f"ema_{period}"
    return result


def rsi(values: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI; flat windows return 50 and one-sided windows 0 or 100."""
    period = _positive_period(period)
    delta = values.astype(float).diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    average_gain = gains.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + relative_strength))
    result = result.mask((average_loss == 0) & (average_gain > 0), 100.0)
    result = result.mask((average_loss == 0) & (average_gain == 0), 50.0)
    result.name = f"rsi_{period}"
    return result


def vwap(frame: pd.DataFrame, *, anchor: str = "D") -> pd.Series:
    """Calculate volume-weighted average price, reset at each time anchor.

    The default resets at midnight UTC. ``anchor`` can be any pandas-supported
    ``DatetimeIndex.floor`` interval, for example ``"D"`` or ``"4h"``.
    """
    if not {"high", "low", "close", "volume"}.issubset(frame.columns):
        raise ValueError("VWAP requires high, low, close, and volume columns")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("VWAP requires a DatetimeIndex")
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    volume = frame["volume"].astype(float).clip(lower=0.0)
    try:
        buckets = frame.index.floor(anchor)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Unsupported VWAP anchor: {anchor}") from exc
    products = (typical * volume).groupby(buckets).cumsum()
    cumulative_volume = volume.groupby(buckets).cumsum().replace(0.0, np.nan)
    result = products / cumulative_volume
    result.name = "vwap"
    return result


def add_indicators(
    frame: pd.DataFrame,
    *,
    atr_period: int = 14,
    ema_periods: tuple[int, ...] = (20, 50),
    rsi_period: int = 14,
    include_vwap: bool = True,
) -> pd.DataFrame:
    """Return a copy with common indicator columns appended."""
    enriched = frame.copy()
    enriched[f"atr_{atr_period}"] = atr(frame, atr_period)
    for period in ema_periods:
        enriched[f"ema_{period}"] = ema(frame["close"], period)
    enriched[f"rsi_{rsi_period}"] = rsi(frame["close"], rsi_period)
    if include_vwap and "volume" in frame.columns:
        enriched["vwap"] = vwap(frame)
    return enriched

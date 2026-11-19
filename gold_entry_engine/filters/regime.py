"""Simple close-confirmed trend/range/high-volatility market regime filter."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

import numpy as np
import pandas as pd

from ..features.indicators import atr, ema
from ..signals.base import TradeSignal


class Regime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


def classify_regime(
    frame: pd.DataFrame,
    *,
    atr_period: int = 14,
    ema_period: int = 50,
    slope_lookback: int = 5,
    volatility_window: int = 100,
    high_volatility_quantile: float = 0.8,
    trend_atr_threshold: float = 0.5,
) -> pd.Series:
    """Classify each bar using ATR percentile and normalized EMA slope.

    Current-bar information is used only at that bar's close; all rolling
    thresholds are trailing and never centered.
    """
    if min(atr_period, ema_period, slope_lookback, volatility_window) < 1:
        raise ValueError("Periods must be positive")
    if not 0 < high_volatility_quantile < 1 or trend_atr_threshold < 0:
        raise ValueError("Invalid volatility quantile or trend threshold")
    volatility = atr(frame, atr_period)
    average = ema(frame["close"], ema_period)
    normalized_vol = volatility / frame["close"].replace(0.0, np.nan)
    min_periods = min(volatility_window, max(10, atr_period))
    vol_threshold = normalized_vol.rolling(
        volatility_window,
        min_periods=min_periods,
    ).quantile(high_volatility_quantile)
    slope = (average - average.shift(slope_lookback)).abs() / volatility.replace(0.0, np.nan)

    labels = np.full(len(frame), Regime.UNKNOWN.value, dtype=object)
    vol_values = normalized_vol.to_numpy(dtype=float)
    vol_limits = vol_threshold.to_numpy(dtype=float)
    slope_values = slope.to_numpy(dtype=float)
    for index in range(len(frame)):
        if not np.isfinite([vol_values[index], vol_limits[index], slope_values[index]]).all():
            continue
        if vol_values[index] >= vol_limits[index]:
            labels[index] = Regime.HIGH_VOLATILITY.value
        elif slope_values[index] >= trend_atr_threshold:
            labels[index] = Regime.TREND.value
        else:
            labels[index] = Regime.RANGE.value
    return pd.Series(labels, index=frame.index, name="regime", dtype="object")


def filter_by_regime(
    signals: Iterable[TradeSignal],
    regimes: pd.Series,
    *,
    allowed: Iterable[Regime | str] = (Regime.TREND,),
    fail_closed: bool = True,
) -> list[TradeSignal]:
    """Keep signals whose timestamp's regime is explicitly allowed."""
    allowed_values = {str(value.value if isinstance(value, Regime) else value) for value in allowed}
    accepted: list[TradeSignal] = []
    for signal in signals:
        if signal.timestamp not in regimes.index:
            if not fail_closed:
                accepted.append(signal)
            continue
        value = str(regimes.loc[signal.timestamp])
        if value in allowed_values:
            accepted.append(signal)
    return accepted

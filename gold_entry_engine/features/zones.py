"""Support/resistance, order-block, and three-candle FVG zone detectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .indicators import atr
from .structure import detect_swings

ZoneKind = Literal["support", "resistance", "order_block", "fvg"]
ZoneSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class Zone:
    kind: ZoneKind
    side: ZoneSide
    lower: float
    upper: float
    formed_at: pd.Timestamp
    source_at: pd.Timestamp | None = None
    invalidated_at: pd.Timestamp | None = None
    mitigated_at: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        if not np.isfinite([self.lower, self.upper]).all() or self.lower > self.upper:
            raise ValueError("Zone boundaries must be finite and lower <= upper")

    def active_at(self, timestamp: pd.Timestamp) -> bool:
        """Whether the zone was still uninvalidated/unmitigated at this time."""
        stamp = pd.Timestamp(timestamp)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        for event in (self.invalidated_at, self.mitigated_at):
            if event is None or pd.isna(event):
                continue
            event_time = pd.Timestamp(event)
            event_time = (
                event_time.tz_localize("UTC")
                if event_time.tzinfo is None
                else event_time.tz_convert("UTC")
            )
            if event_time <= stamp:
                return False
        return True

    def overlaps(self, low: float, high: float) -> bool:
        return high >= self.lower and low <= self.upper


def find_support_resistance(
    frame: pd.DataFrame,
    *,
    left: int = 2,
    right: int = 2,
    atr_period: int = 14,
    width_atr: float = 0.1,
) -> list[Zone]:
    """Create local support/resistance zones around confirmed swing points."""
    if width_atr < 0:
        raise ValueError("width_atr must be non-negative")
    swings = detect_swings(frame, left=left, right=right)
    volatility = atr(frame, atr_period)
    zones: list[Zone] = []
    for position, timestamp in enumerate(swings.index):
        local_atr = volatility.iloc[position]
        width = float(local_atr) * width_atr if np.isfinite(local_atr) else 0.0
        high_value = swings["swing_high"].iloc[position]
        low_value = swings["swing_low"].iloc[position]
        if np.isfinite(high_value):
            price = float(high_value)
            zones.append(
                Zone(
                    "resistance", "sell", price - width, price + width, timestamp,
                    swings["swing_high_pivot_time"].iloc[position],
                )
            )
        if np.isfinite(low_value):
            price = float(low_value)
            zones.append(
                Zone(
                    "support", "buy", price - width, price + width, timestamp,
                    swings["swing_low_pivot_time"].iloc[position],
                )
            )
    return zones


def find_fvgs(frame: pd.DataFrame, *, min_gap: float = 0.0) -> list[Zone]:
    """Detect closed three-candle fair-value gaps and first later mitigation.

    Bullish FVG: current low is above the high two candles earlier. Bearish FVG:
    current high is below the low two candles earlier. Mitigation timestamps are
    recorded only when a later closed candle first overlaps the gap.
    """
    required = {"high", "low"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Bars are missing columns: {sorted(required)}")
    if min_gap < 0:
        raise ValueError("min_gap must be non-negative")
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    zones: list[Zone] = []
    for index in range(2, len(frame)):
        bullish_gap = lows[index] - highs[index - 2]
        bearish_gap = lows[index - 2] - highs[index]
        if bullish_gap > 0 and bullish_gap >= min_gap:
            lower, upper, side = highs[index - 2], lows[index], "buy"
            kind: ZoneKind = "fvg"
        elif bearish_gap > 0 and bearish_gap >= min_gap:
            lower, upper, side = highs[index], lows[index - 2], "sell"
            kind = "fvg"
        else:
            continue
        mitigated_at = None
        for later in range(index + 1, len(frame)):
            if highs[later] >= lower and lows[later] <= upper:
                mitigated_at = frame.index[later]
                break
        zones.append(
            Zone(
                kind,
                side,
                float(lower),
                float(upper),
                frame.index[index],
                frame.index[index - 2],
                mitigated_at=mitigated_at,
            )
        )
    return zones


def find_order_blocks(
    frame: pd.DataFrame,
    *,
    atr_period: int = 14,
    displacement_atr: float = 1.0,
    lookback: int = 8,
) -> list[Zone]:
    """Find the nearest opposing candle before an ATR-sized displacement.

    The displacement candle must close beyond the previous candle's extreme.
    An order block becomes invalid after a later close passes its far boundary;
    first later overlap is recorded as mitigation. Use ``Zone.active_at`` to
    query lifecycle state as-of a historical timestamp.
    """
    if lookback < 1 or displacement_atr <= 0:
        raise ValueError("lookback and displacement_atr must be positive")
    if not {"open", "high", "low", "close"}.issubset(frame.columns):
        raise ValueError("Order blocks require OHLC columns")
    volatility = atr(frame, atr_period).to_numpy(dtype=float)
    opening = frame["open"].to_numpy(dtype=float)
    closing = frame["close"].to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    zones: list[Zone] = []

    for index in range(1, len(frame)):
        if not np.isfinite(volatility[index]):
            continue
        displacement = closing[index] - opening[index]
        if displacement >= displacement_atr * volatility[index] and closing[index] > highs[index - 1]:
            side: ZoneSide = "buy"
            opposing = np.flatnonzero(closing[max(0, index - lookback) : index] < opening[max(0, index - lookback) : index])
        elif displacement <= -displacement_atr * volatility[index] and closing[index] < lows[index - 1]:
            side = "sell"
            opposing = np.flatnonzero(closing[max(0, index - lookback) : index] > opening[max(0, index - lookback) : index])
        else:
            continue
        if len(opposing) == 0:
            continue
        start = max(0, index - lookback)
        source_index = start + int(opposing[-1])
        lower, upper = float(lows[source_index]), float(highs[source_index])
        invalidated_at = None
        mitigated_at = None
        for later in range(index + 1, len(frame)):
            if side == "buy" and closing[later] < lower:
                invalidated_at = frame.index[later]
                break
            if side == "sell" and closing[later] > upper:
                invalidated_at = frame.index[later]
                break
            if mitigated_at is None and highs[later] >= lower and lows[later] <= upper:
                mitigated_at = frame.index[later]
        zones.append(
            Zone(
                "order_block",
                side,
                lower,
                upper,
                frame.index[index],
                frame.index[source_index],
                invalidated_at,
                mitigated_at,
            )
        )
    return zones

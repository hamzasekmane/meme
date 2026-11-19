"""Equal-high/low pools, prior-period levels, and wick/close sweep detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .indicators import atr
from .structure import detect_swings

PoolSide = Literal["high", "low"]
TradeSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class LiquidityPool:
    kind: str
    side: PoolSide
    price: float
    formed_at: pd.Timestamp
    available_at: pd.Timestamp
    touches: int = 1


@dataclass(frozen=True)
class LiquiditySweep:
    side: TradeSide
    pool: LiquidityPool
    timestamp: pd.Timestamp
    extreme: float
    invalidated_at: pd.Timestamp | None = None

    def valid_at(self, timestamp: pd.Timestamp) -> bool:
        return self.invalidated_at is None or pd.Timestamp(timestamp) < self.invalidated_at


def find_equal_highs_lows(
    frame: pd.DataFrame,
    *,
    left: int = 2,
    right: int = 2,
    lookback: int = 200,
    atr_period: int = 14,
    tolerance_atr: float = 0.1,
    min_touches: int = 2,
) -> list[LiquidityPool]:
    """Cluster confirmed swing prices into equal-high/equal-low liquidity pools."""
    if lookback < 1 or min_touches < 2 or tolerance_atr < 0:
        raise ValueError("lookback/min_touches must be positive and tolerance_atr non-negative")
    swings = detect_swings(frame, left=left, right=right)
    volatility = atr(frame, atr_period)
    cutoff = max(0, len(frame) - lookback)
    pools: list[LiquidityPool] = []

    for side, price_column, kind in (
        ("high", "swing_high", "EQH"),
        ("low", "swing_low", "EQL"),
    ):
        points: list[tuple[int, float, pd.Timestamp]] = []
        for index in range(cutoff, len(frame)):
            value = swings[price_column].iloc[index]
            if np.isfinite(value):
                points.append((index, float(value), frame.index[index]))
        clusters: list[list[tuple[int, float, pd.Timestamp]]] = []
        for point in points:
            index, price, _ = point
            local_atr = volatility.iloc[index]
            tolerance = float(local_atr) * tolerance_atr if np.isfinite(local_atr) else 0.0
            destination = None
            for cluster in clusters:
                cluster_price = float(np.mean([member[1] for member in cluster]))
                prior_index = cluster[-1][0]
                prior_atr = volatility.iloc[prior_index]
                prior_tolerance = float(prior_atr) * tolerance_atr if np.isfinite(prior_atr) else 0.0
                if abs(price - cluster_price) <= max(tolerance, prior_tolerance):
                    destination = cluster
                    break
            if destination is None:
                clusters.append([point])
            else:
                destination.append(point)

        for cluster in clusters:
            if len(cluster) < min_touches:
                continue
            # A pool is actionable only after the last swing in its cluster has
            # itself been confirmed (event indices, not pivot indices).
            latest = cluster[-1]
            formed_at = cluster[0][2]
            pools.append(
                LiquidityPool(
                    kind=kind,
                    side=side,  # type: ignore[arg-type]
                    price=float(np.mean([member[1] for member in cluster])),
                    formed_at=formed_at,
                    available_at=latest[2],
                    touches=len(cluster),
                )
            )
    return pools


def previous_period_levels(frame: pd.DataFrame, *, period: Literal["D", "W"] = "D") -> pd.DataFrame:
    """Attach the previous completed UTC day's or week's high and low to each bar."""
    if not {"high", "low"}.issubset(frame.columns):
        raise ValueError("Previous-period levels require high and low columns")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("Previous-period levels require a DatetimeIndex")
    if period == "D":
        keys = frame.index.normalize()
    elif period == "W":
        keys = frame.index.to_period("W-SUN")
    else:
        raise ValueError("period must be 'D' or 'W'")
    grouped = frame.groupby(keys).agg(period_high=("high", "max"), period_low=("low", "min"))
    previous = grouped.shift(1)
    lookup_high = previous["period_high"].to_dict()
    lookup_low = previous["period_low"].to_dict()
    result = pd.DataFrame(index=frame.index)
    result["previous_high"] = [lookup_high.get(key, np.nan) for key in keys]
    result["previous_low"] = [lookup_low.get(key, np.nan) for key in keys]
    return result


def previous_day_levels(frame: pd.DataFrame) -> pd.DataFrame:
    """Convenience wrapper returning ``pdh`` and ``pdl`` columns."""
    levels = previous_period_levels(frame, period="D")
    return levels.rename(columns={"previous_high": "pdh", "previous_low": "pdl"})


def previous_week_levels(frame: pd.DataFrame) -> pd.DataFrame:
    """Convenience wrapper returning ``pwh`` and ``pwl`` columns."""
    levels = previous_period_levels(frame, period="W")
    return levels.rename(columns={"previous_high": "pwh", "previous_low": "pwl"})


def detect_sweeps(
    frame: pd.DataFrame,
    pools: list[LiquidityPool],
    *,
    min_wick_atr: float = 0.15,
    atr_period: int = 14,
) -> list[LiquiditySweep]:
    """Find wick-through/close-back events after a pool becomes available.

    A later close beyond the pool, or a newer wick through it, marks an earlier
    sweep invalidated. The returned event preserves that timestamp so historical
    consumers can query validity with ``LiquiditySweep.valid_at``.
    """
    if min_wick_atr < 0:
        raise ValueError("min_wick_atr must be non-negative")
    if not {"high", "low", "close"}.issubset(frame.columns):
        raise ValueError("Sweep detection requires high, low, and close columns")
    volatility = atr(frame, atr_period).to_numpy(dtype=float)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    events: list[LiquiditySweep] = []

    for pool in pools:
        available_index = int(frame.index.searchsorted(pool.available_at, side="right"))
        for index in range(available_index, len(frame)):
            if min_wick_atr > 0 and not np.isfinite(volatility[index]):
                continue
            threshold = (volatility[index] if np.isfinite(volatility[index]) else 0.0) * min_wick_atr
            if pool.side == "high":
                swept = highs[index] >= pool.price + threshold and closes[index] < pool.price
                side: TradeSide = "sell"
                extreme = highs[index]
            else:
                swept = lows[index] <= pool.price - threshold and closes[index] > pool.price
                side = "buy"
                extreme = lows[index]
            if not swept:
                continue
            invalidated = None
            for later in range(index + 1, len(frame)):
                if pool.side == "high":
                    consumed = closes[later] > pool.price or highs[later] > pool.price
                else:
                    consumed = closes[later] < pool.price or lows[later] < pool.price
                if consumed:
                    invalidated = frame.index[later]
                    break
            events.append(
                LiquiditySweep(side, pool, frame.index[index], float(extreme), invalidated)
            )
    return events

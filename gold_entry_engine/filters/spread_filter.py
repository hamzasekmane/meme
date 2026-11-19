"""Spread checks for signals using broker-provided spread points."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..signals.base import TradeSignal


@dataclass(frozen=True)
class SpreadFilter:
    max_spread_points: float
    point_size: float
    fail_closed: bool = False

    def __post_init__(self) -> None:
        if self.max_spread_points < 0 or self.point_size <= 0:
            raise ValueError("max spread must be non-negative and point size positive")

    def allows(self, spread_points: float | None) -> bool:
        if spread_points is None or not np.isfinite(spread_points):
            return not self.fail_closed
        return float(spread_points) <= self.max_spread_points

    def price_to_points(self, spread_price: float) -> float:
        if not np.isfinite(spread_price) or spread_price < 0:
            raise ValueError("spread_price must be finite and non-negative")
        return float(spread_price) / self.point_size


def filter_by_spread(
    signals: Iterable[TradeSignal],
    frame: pd.DataFrame,
    *,
    max_spread_points: float,
    point_size: float,
    spread_column: str = "spread",
    fail_closed: bool = False,
) -> list[TradeSignal]:
    """Apply a timestamp-aligned spread gate; a missing column is explicit policy."""
    gate = SpreadFilter(max_spread_points, point_size, fail_closed)
    if spread_column not in frame.columns:
        return [] if fail_closed else list(signals)
    values = frame[spread_column]
    accepted: list[TradeSignal] = []
    for signal in signals:
        if signal.timestamp not in values.index:
            spread = None
        else:
            raw = values.loc[signal.timestamp]
            spread = float(raw) if np.isscalar(raw) and pd.notna(raw) else None
        if gate.allows(spread):
            accepted.append(signal)
    return accepted

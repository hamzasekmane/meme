"""Common immutable signal contract for all entry strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class TradeSignal:
    """A proposed trade plan; it is not an order and cannot place one."""

    strategy: str
    side: Side
    timestamp: pd.Timestamp
    entry: float
    stop_loss: float
    take_profit: float
    confidence: float
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        timestamp = pd.Timestamp(self.timestamp)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        object.__setattr__(self, "timestamp", timestamp)
        prices = np.asarray([self.entry, self.stop_loss, self.take_profit], dtype=float)
        if not np.isfinite(prices).all() or np.any(prices <= 0):
            raise ValueError("entry, stop_loss, and take_profit must be finite positive prices")
        if self.side == "buy" and not (self.stop_loss < self.entry < self.take_profit):
            raise ValueError("A buy signal requires stop_loss < entry < take_profit")
        if self.side == "sell" and not (self.take_profit < self.entry < self.stop_loss):
            raise ValueError("A sell signal requires take_profit < entry < stop_loss")
        if not np.isfinite(self.confidence) or not 0.0 <= self.confidence <= 100.0:
            raise ValueError("confidence must be in [0, 100]")
        if not self.strategy.strip():
            raise ValueError("strategy name cannot be empty")

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry - self.stop_loss)

    @property
    def reward_risk(self) -> float:
        reward = self.take_profit - self.entry if self.side == "buy" else self.entry - self.take_profit
        return reward / self.risk_per_unit


class BaseStrategy(ABC):
    """Base class requiring a pure historical signal-generation interface."""

    name = "base"

    @abstractmethod
    def generate(
        self,
        frame: pd.DataFrame,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> list[TradeSignal]:
        """Generate closed-bar signals from normalized OHLCV data."""
        raise NotImplementedError

"""Prior-range breakout followed by a later, closed-candle retest."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ..features.indicators import atr
from ..risk.sl_tp import build_bracket
from .base import BaseStrategy, TradeSignal


class BreakoutRetestStrategy(BaseStrategy):
    name = "breakout_retest"

    def __init__(
        self,
        *,
        range_lookback: int = 20,
        max_retest_bars: int = 8,
        retest_tolerance_atr: float = 0.15,
        atr_period: int = 14,
        stop_atr: float = 1.5,
        reward_risk: float = 2.0,
        tick_size: float = 0.01,
    ) -> None:
        if min(range_lookback, max_retest_bars, atr_period) < 1:
            raise ValueError("Lookback and periods must be positive")
        if retest_tolerance_atr < 0 or stop_atr <= 0 or reward_risk <= 0:
            raise ValueError("Tolerance must be non-negative and stop/RR positive")
        self.range_lookback = range_lookback
        self.max_retest_bars = max_retest_bars
        self.retest_tolerance_atr = retest_tolerance_atr
        self.atr_period = atr_period
        self.stop_atr = stop_atr
        self.reward_risk = reward_risk
        self.tick_size = tick_size

    def generate(
        self,
        frame: pd.DataFrame,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> list[TradeSignal]:
        if frame.empty:
            return []
        volatility = atr(frame, self.atr_period).to_numpy(dtype=float)
        highs = frame["high"].to_numpy(dtype=float)
        lows = frame["low"].to_numpy(dtype=float)
        opens = frame["open"].to_numpy(dtype=float)
        closes = frame["close"].to_numpy(dtype=float)
        previous_high = frame["high"].shift(1).rolling(self.range_lookback).max().to_numpy(dtype=float)
        previous_low = frame["low"].shift(1).rolling(self.range_lookback).min().to_numpy(dtype=float)
        signals: list[TradeSignal] = []
        pending: dict[str, tuple[int, float]] = {}

        for index in range(len(frame)):
            if not np.isfinite(volatility[index]) or volatility[index] <= 0:
                continue
            tolerance = volatility[index] * self.retest_tolerance_atr
            # Process prior breakout states before registering a breakout on this
            # candle, so a same-bar range break is never called a retest.
            for side in tuple(pending):
                breakout_index, level = pending[side]
                age = index - breakout_index
                if age > self.max_retest_bars:
                    del pending[side]
                    continue
                if side == "buy":
                    invalid = closes[index] < level - tolerance
                    touched = lows[index] <= level + tolerance and closes[index] >= level and closes[index] >= opens[index]
                else:
                    invalid = closes[index] > level + tolerance
                    touched = highs[index] >= level - tolerance and closes[index] <= level and closes[index] <= opens[index]
                if invalid:
                    del pending[side]
                    continue
                if not touched or age < 1:
                    continue

                start = max(0, index - self.range_lookback + 1)
                swing_low = float(np.min(lows[start : index + 1]))
                swing_high = float(np.max(highs[start : index + 1]))
                entry = closes[index]
                try:
                    bracket = build_bracket(
                        side,  # type: ignore[arg-type]
                        entry=entry,
                        atr_value=volatility[index],
                        tick_size=self.tick_size,
                        reward_risk=self.reward_risk,
                        stop_atr=self.stop_atr,
                        swing_low=swing_low if side == "buy" else None,
                        swing_high=swing_high if side == "sell" else None,
                    )
                except ValueError:
                    del pending[side]
                    continue
                signals.append(
                    TradeSignal(
                        strategy=self.name,
                        side=side,  # type: ignore[arg-type]
                        timestamp=frame.index[index],
                        entry=entry,
                        stop_loss=bracket.stop_loss,
                        take_profit=bracket.take_profit,
                        confidence=76.0,
                        reason=f"Confirmed {side} breakout retest of prior range level",
                        metadata={"breakout_at": frame.index[breakout_index], "level": level},
                    )
                )
                del pending[side]

            if index == 0:
                continue
            if "buy" not in pending and np.isfinite(previous_high[index]) and closes[index] > previous_high[index]:
                pending["buy"] = (index, float(previous_high[index]))
            if "sell" not in pending and np.isfinite(previous_low[index]) and closes[index] < previous_low[index]:
                pending["sell"] = (index, float(previous_low[index]))
        return signals

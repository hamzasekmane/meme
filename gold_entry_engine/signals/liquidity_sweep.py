"""Local liquidity-pool wick sweep with close-back and reversal confirmation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ..features.indicators import atr
from ..risk.sl_tp import build_bracket
from .base import BaseStrategy, TradeSignal


class LiquiditySweepStrategy(BaseStrategy):
    name = "liquidity_sweep"

    def __init__(
        self,
        *,
        lookback: int = 20,
        min_sweep_atr: float = 0.15,
        stop_buffer_atr: float = 0.25,
        atr_period: int = 14,
        reward_risk: float = 2.0,
        require_reversal_candle: bool = True,
        tick_size: float = 0.01,
    ) -> None:
        if min(lookback, atr_period) < 1:
            raise ValueError("lookback and atr_period must be positive")
        if min_sweep_atr < 0 or stop_buffer_atr < 0 or reward_risk <= 0:
            raise ValueError("Sweep/buffer values must be non-negative and reward_risk positive")
        self.lookback = lookback
        self.min_sweep_atr = min_sweep_atr
        self.stop_buffer_atr = stop_buffer_atr
        self.atr_period = atr_period
        self.reward_risk = reward_risk
        self.require_reversal_candle = require_reversal_candle
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
        prior_high = frame["high"].shift(1).rolling(self.lookback).max().to_numpy(dtype=float)
        prior_low = frame["low"].shift(1).rolling(self.lookback).min().to_numpy(dtype=float)
        opening = frame["open"].to_numpy(dtype=float)
        highs = frame["high"].to_numpy(dtype=float)
        lows = frame["low"].to_numpy(dtype=float)
        closes = frame["close"].to_numpy(dtype=float)
        signals: list[TradeSignal] = []

        for index in range(len(frame)):
            if not np.isfinite(volatility[index]) or volatility[index] <= 0:
                continue
            min_wick = volatility[index] * self.min_sweep_atr
            sell_sweep = (
                np.isfinite(prior_high[index])
                and highs[index] >= prior_high[index] + min_wick
                and closes[index] < prior_high[index]
                and (not self.require_reversal_candle or closes[index] < opening[index])
            )
            buy_sweep = (
                np.isfinite(prior_low[index])
                and lows[index] <= prior_low[index] - min_wick
                and closes[index] > prior_low[index]
                and (not self.require_reversal_candle or closes[index] > opening[index])
            )
            if not sell_sweep and not buy_sweep:
                continue
            side = "sell" if sell_sweep else "buy"
            entry = closes[index]
            try:
                bracket = build_bracket(
                    side,
                    entry=entry,
                    atr_value=volatility[index],
                    tick_size=self.tick_size,
                    reward_risk=self.reward_risk,
                    stop_atr=1.5,
                    stop_buffer_atr=self.stop_buffer_atr,
                    swing_high=highs[index] if side == "sell" else None,
                    swing_low=lows[index] if side == "buy" else None,
                )
            except ValueError:
                continue
            excess = (
                highs[index] - prior_high[index]
                if side == "sell"
                else prior_low[index] - lows[index]
            ) / volatility[index]
            confidence = min(95.0, 70.0 + max(0.0, excess - self.min_sweep_atr) * 10.0)
            signals.append(
                TradeSignal(
                    strategy=self.name,
                    side=side,
                    timestamp=frame.index[index],
                    entry=entry,
                    stop_loss=bracket.stop_loss,
                    take_profit=bracket.take_profit,
                    confidence=confidence,
                    reason=f"{side.title()}-side liquidity swept and candle closed back through the pool",
                    metadata={
                        "pool_price": float(prior_high[index] if side == "sell" else prior_low[index]),
                        "sweep_extreme": float(highs[index] if side == "sell" else lows[index]),
                        "atr": float(volatility[index]),
                    },
                )
            )
        return signals

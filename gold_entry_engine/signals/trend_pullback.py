"""EMA-trend pullback strategy with ATR/structure bracket construction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from ..features.indicators import add_indicators
from ..risk.sl_tp import build_bracket
from .base import BaseStrategy, TradeSignal


class TrendPullbackStrategy(BaseStrategy):
    name = "trend_pullback"

    def __init__(
        self,
        *,
        fast_ema: int = 20,
        slow_ema: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
        rsi_buy_min: float = 45.0,
        rsi_buy_max: float = 70.0,
        rsi_sell_min: float = 30.0,
        rsi_sell_max: float = 55.0,
        stop_atr: float = 1.5,
        swing_lookback: int = 8,
        reward_risk: float = 2.0,
        tick_size: float = 0.01,
    ) -> None:
        if min(fast_ema, slow_ema, rsi_period, atr_period, swing_lookback) < 1:
            raise ValueError("Indicator periods must be positive")
        if fast_ema >= slow_ema:
            raise ValueError("fast_ema must be less than slow_ema")
        if rsi_buy_min > rsi_buy_max or rsi_sell_min > rsi_sell_max:
            raise ValueError("RSI lower bounds cannot exceed upper bounds")
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.rsi_buy_min = rsi_buy_min
        self.rsi_buy_max = rsi_buy_max
        self.rsi_sell_min = rsi_sell_min
        self.rsi_sell_max = rsi_sell_max
        self.stop_atr = stop_atr
        self.swing_lookback = swing_lookback
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
        bars = add_indicators(
            frame,
            atr_period=self.atr_period,
            ema_periods=(self.fast_ema, self.slow_ema),
            rsi_period=self.rsi_period,
            include_vwap=False,
        )
        fast = bars[f"ema_{self.fast_ema}"].to_numpy(dtype=float)
        slow = bars[f"ema_{self.slow_ema}"].to_numpy(dtype=float)
        oscillator = bars[f"rsi_{self.rsi_period}"].to_numpy(dtype=float)
        volatility = bars[f"atr_{self.atr_period}"].to_numpy(dtype=float)
        opening = bars["open"].to_numpy(dtype=float)
        highs = bars["high"].to_numpy(dtype=float)
        lows = bars["low"].to_numpy(dtype=float)
        closes = bars["close"].to_numpy(dtype=float)
        signals: list[TradeSignal] = []

        for index in range(len(bars)):
            if not np.isfinite([fast[index], slow[index], oscillator[index], volatility[index]]).all():
                continue
            entry = closes[index]
            start = max(0, index - self.swing_lookback + 1)
            recent_low = float(np.min(lows[start : index + 1]))
            recent_high = float(np.max(highs[start : index + 1]))
            buy_setup = (
                fast[index] > slow[index]
                and lows[index] <= fast[index]
                and entry > fast[index]
                and entry >= opening[index]
                and self.rsi_buy_min <= oscillator[index] <= self.rsi_buy_max
            )
            sell_setup = (
                fast[index] < slow[index]
                and highs[index] >= fast[index]
                and entry < fast[index]
                and entry <= opening[index]
                and self.rsi_sell_min <= oscillator[index] <= self.rsi_sell_max
            )
            if not buy_setup and not sell_setup:
                continue
            side = "buy" if buy_setup else "sell"
            try:
                bracket = build_bracket(
                    side,
                    entry=entry,
                    atr_value=volatility[index],
                    tick_size=self.tick_size,
                    reward_risk=self.reward_risk,
                    stop_atr=self.stop_atr,
                    swing_low=recent_low if side == "buy" else None,
                    swing_high=recent_high if side == "sell" else None,
                )
            except ValueError:
                continue
            trend_strength = min(4.0, abs(fast[index] - slow[index]) / volatility[index])
            confidence = min(92.0, 65.0 + trend_strength * 5.0)
            signals.append(
                TradeSignal(
                    strategy=self.name,
                    side=side,
                    timestamp=bars.index[index],
                    entry=entry,
                    stop_loss=bracket.stop_loss,
                    take_profit=bracket.take_profit,
                    confidence=confidence,
                    reason="EMA trend with close-confirmed pullback and RSI filter",
                    metadata={
                        "fast_ema": float(fast[index]),
                        "slow_ema": float(slow[index]),
                        "rsi": float(oscillator[index]),
                        "atr": float(volatility[index]),
                    },
                )
            )
        return signals

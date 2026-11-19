"""ATR/structure-aware stop and target construction on a symbol tick grid."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

BracketSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class TradeBracket:
    side: BracketSide
    entry: float
    stop_loss: float
    take_profit: float
    risk_distance: float
    reward_risk: float


def _floor_tick(price: float, tick_size: float) -> float:
    return math.floor(price / tick_size + 1e-10) * tick_size


def _ceil_tick(price: float, tick_size: float) -> float:
    return math.ceil(price / tick_size - 1e-10) * tick_size


def build_bracket(
    side: BracketSide,
    *,
    entry: float,
    atr_value: float,
    tick_size: float,
    reward_risk: float = 2.0,
    stop_atr: float = 1.5,
    stop_buffer_atr: float = 0.25,
    swing_low: float | None = None,
    swing_high: float | None = None,
    external_target: float | None = None,
) -> TradeBracket:
    """Build and validate a bracket, preserving structural stops.

    If an external target is provided but does not meet the requested R multiple,
    the plan is rejected; no synthetic target is substituted. When there is no
    structural swing, the configured ATR distance is used for the stop.
    """
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    numeric = (entry, atr_value, tick_size, reward_risk, stop_atr, stop_buffer_atr)
    if any(not math.isfinite(float(value)) for value in numeric):
        raise ValueError("Bracket inputs must be finite")
    if entry <= 0 or atr_value <= 0 or tick_size <= 0 or reward_risk <= 0 or stop_atr <= 0:
        raise ValueError("entry, ATR, tick size, reward_risk, and stop_atr must be positive")
    if stop_buffer_atr < 0:
        raise ValueError("stop_buffer_atr must be non-negative")

    if side == "buy":
        structural = (
            float(swing_low) - atr_value * stop_buffer_atr
            if swing_low is not None and 0 < float(swing_low) < entry
            else entry - atr_value * stop_atr
        )
        stop = _floor_tick(structural, tick_size)
        risk = entry - stop
        target = (
            float(external_target)
            if external_target is not None
            else entry + risk * reward_risk
        )
        take_profit = _ceil_tick(target, tick_size)
        reward = take_profit - entry
    else:
        structural = (
            float(swing_high) + atr_value * stop_buffer_atr
            if swing_high is not None and float(swing_high) > entry
            else entry + atr_value * stop_atr
        )
        stop = _ceil_tick(structural, tick_size)
        risk = stop - entry
        target = (
            float(external_target)
            if external_target is not None
            else entry - risk * reward_risk
        )
        take_profit = _floor_tick(target, tick_size)
        reward = entry - take_profit

    if risk <= 0 or reward <= 0:
        raise ValueError("Bracket has invalid stop/target direction")
    actual_rr = reward / risk
    if external_target is not None and actual_rr + 1e-10 < reward_risk:
        raise ValueError("External target does not meet minimum reward/risk")
    if side == "buy" and not stop < entry < take_profit:
        raise ValueError("Invalid buy bracket geometry")
    if side == "sell" and not take_profit < entry < stop:
        raise ValueError("Invalid sell bracket geometry")
    return TradeBracket(side, float(entry), float(stop), float(take_profit), float(risk), float(actual_rr))

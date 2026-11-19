"""Risk-based position sizing using broker tick and volume specifications."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSize:
    lots: float
    risk_cash: float
    estimated_loss_at_stop: float
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.lots > 0.0


def size_position(
    *,
    equity: float,
    risk_percent: float,
    entry: float,
    stop_loss: float,
    tick_size: float,
    tick_value_per_lot: float,
    volume_min: float = 0.01,
    volume_max: float = 100.0,
    volume_step: float = 0.01,
) -> PositionSize:
    """Floor lot size to the broker step and never exceed the risk budget.

    ``tick_value_per_lot`` is the account-currency value of one tick for one
    standard lot. It must come from the broker's contract specification; the
    function does not guess currency conversion or contract size.
    """
    values = (equity, risk_percent, entry, stop_loss, tick_size, tick_value_per_lot,
              volume_min, volume_max, volume_step)
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("Sizing inputs must be finite")
    if equity <= 0 or not 0 < risk_percent <= 100:
        raise ValueError("equity must be positive and risk_percent in (0, 100]")
    if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
        raise ValueError("entry and stop_loss must be positive and distinct")
    if min(tick_size, tick_value_per_lot, volume_min, volume_max, volume_step) <= 0:
        raise ValueError("Tick and volume specifications must be positive")
    if volume_max < volume_min:
        raise ValueError("volume_max cannot be lower than volume_min")

    risk_cash = equity * risk_percent / 100.0
    loss_per_lot = abs(entry - stop_loss) / tick_size * tick_value_per_lot
    raw_lots = risk_cash / loss_per_lot
    stepped_lots = math.floor((raw_lots + volume_step * 1e-10) / volume_step) * volume_step
    maximum_step_aligned = math.floor((volume_max + volume_step * 1e-10) / volume_step) * volume_step
    stepped_lots = min(stepped_lots, maximum_step_aligned)
    # Avoid binary floating-point crumbs that can violate the broker's step.
    precision = max(0, min(10, round(-math.log10(volume_step)) + 2))
    lots = round(stepped_lots, precision)
    if lots < volume_min:
        return PositionSize(0.0, risk_cash, 0.0, "risk budget is below broker minimum volume")
    estimated_loss = lots * loss_per_lot
    if estimated_loss > risk_cash + max(1e-8, risk_cash * 1e-10):
        # A defensive second floor for unusual non-decimal volume steps.
        lots = max(0.0, round(lots - volume_step, precision))
        if lots < volume_min:
            return PositionSize(0.0, risk_cash, 0.0, "risk budget is below broker minimum volume")
        estimated_loss = lots * loss_per_lot
    return PositionSize(lots, risk_cash, estimated_loss, "")

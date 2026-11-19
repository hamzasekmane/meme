"""Stateful daily and peak-to-trough drawdown guard for new entries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


@dataclass(frozen=True)
class DrawdownDecision:
    allowed: bool
    reason: str
    daily_drawdown_pct: float
    peak_drawdown_pct: float


class DailyDrawdownGuard:
    """Block new trades after a daily loss or account peak-drawdown threshold.

    The daily baseline resets at the start of each local calendar day. Peak
    equity and a max-drawdown lock are account-lifetime state and do not reset.
    This is an entry gate only; it does not liquidate existing positions.
    """

    def __init__(
        self,
        daily_limit_pct: float,
        *,
        max_drawdown_pct: float | None = None,
        timezone: str = "UTC",
    ) -> None:
        if daily_limit_pct <= 0 or daily_limit_pct > 100:
            raise ValueError("daily_limit_pct must be in (0, 100]")
        if max_drawdown_pct is not None and not 0 < max_drawdown_pct <= 100:
            raise ValueError("max_drawdown_pct must be in (0, 100]")
        try:
            self._zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {timezone}") from exc
        self.daily_limit_pct = float(daily_limit_pct)
        self.max_drawdown_pct = float(max_drawdown_pct) if max_drawdown_pct is not None else None
        self._day: date | None = None
        self._day_start_equity: float | None = None
        self._peak_equity: float | None = None
        self._daily_locked = False
        self._max_locked = False

    def check(self, equity: float, timestamp: pd.Timestamp) -> DrawdownDecision:
        if not math.isfinite(float(equity)) or equity <= 0:
            raise ValueError("equity must be finite and positive")
        stamp = pd.Timestamp(timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        local_day = stamp.tz_convert(self._zone).date()

        if self._peak_equity is None:
            self._peak_equity = float(equity)
        else:
            self._peak_equity = max(self._peak_equity, float(equity))
        if self._day != local_day:
            self._day = local_day
            self._day_start_equity = float(equity)
            self._daily_locked = False

        assert self._day_start_equity is not None and self._peak_equity is not None
        daily_dd = max(0.0, (self._day_start_equity - equity) / self._day_start_equity * 100.0)
        peak_dd = max(0.0, (self._peak_equity - equity) / self._peak_equity * 100.0)
        if daily_dd >= self.daily_limit_pct:
            self._daily_locked = True
        if self.max_drawdown_pct is not None and peak_dd >= self.max_drawdown_pct:
            self._max_locked = True

        if self._max_locked:
            return DrawdownDecision(False, "maximum drawdown limit reached", daily_dd, peak_dd)
        if self._daily_locked:
            return DrawdownDecision(False, "daily drawdown limit reached", daily_dd, peak_dd)
        return DrawdownDecision(True, "", daily_dd, peak_dd)

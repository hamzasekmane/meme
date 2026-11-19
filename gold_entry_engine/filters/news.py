"""Manual calendar-based high-impact news blackout filter.

No news vendor is contacted. Supply a CSV or events explicitly; an empty
calendar blocks nothing unless ``require_calendar=True`` is set.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..signals.base import TradeSignal


@dataclass(frozen=True)
class NewsEvent:
    timestamp: pd.Timestamp
    currency: str = "USD"
    impact: str = "high"
    title: str = ""

    def __post_init__(self) -> None:
        stamp = pd.Timestamp(self.timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        object.__setattr__(self, "timestamp", stamp)
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(self, "impact", self.impact.lower())


class NewsFilter:
    def __init__(
        self,
        events: Iterable[NewsEvent] = (),
        *,
        currencies: Iterable[str] = ("USD",),
        impacts: Iterable[str] = ("high",),
        before_minutes: int = 30,
        after_minutes: int = 15,
        require_calendar: bool = False,
    ) -> None:
        if before_minutes < 0 or after_minutes < 0:
            raise ValueError("News blackout windows must be non-negative")
        self.events = tuple(sorted(events, key=lambda event: event.timestamp))
        self.currencies = {str(currency).upper() for currency in currencies}
        self.impacts = {str(impact).lower() for impact in impacts}
        self.before = pd.Timedelta(minutes=before_minutes)
        self.after = pd.Timedelta(minutes=after_minutes)
        self.require_calendar = require_calendar

    @classmethod
    def from_csv(cls, path: str | Path, **kwargs: object) -> NewsFilter:
        """Load columns ``time,currency,impact,title`` from a caller-owned CSV."""
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        frame = pd.read_csv(source)
        if "time" not in frame:
            for column in ("timestamp", "datetime", "date"):
                if column in frame:
                    frame = frame.rename(columns={column: "time"})
                    break
        if "time" not in frame:
            raise ValueError("News CSV must include a time/timestamp column")
        events = [
            NewsEvent(
                timestamp=row["time"],
                currency=str(row.get("currency", "USD")),
                impact=str(row.get("impact", "high")),
                title=str(row.get("title", "")),
            )
            for _, row in frame.iterrows()
        ]
        return cls(events, **kwargs)

    def is_blocked(self, timestamp: pd.Timestamp, *, currencies: Iterable[str] | None = None) -> bool:
        if not self.events:
            return self.require_calendar
        stamp = pd.Timestamp(timestamp)
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        else:
            stamp = stamp.tz_convert("UTC")
        relevant = {str(value).upper() for value in currencies} if currencies is not None else self.currencies
        for event in self.events:
            if event.currency not in relevant or event.impact not in self.impacts:
                continue
            if event.timestamp - self.before <= stamp <= event.timestamp + self.after:
                return True
        return False

    def filter_signals(
        self,
        signals: Iterable[TradeSignal],
        *,
        currencies: Iterable[str] | None = None,
    ) -> list[TradeSignal]:
        return [
            signal
            for signal in signals
            if not self.is_blocked(signal.timestamp, currencies=currencies)
        ]

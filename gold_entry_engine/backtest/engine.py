"""Single-position OHLC backtester with spread, slippage, and pessimistic fills."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from ..risk.drawdown import DailyDrawdownGuard
from ..risk.sizing import size_position
from ..signals.base import TradeSignal

ExitReason = Literal["stop_loss", "take_profit", "end_of_data"]


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: float = 10_000.0
    risk_percent: float = 0.5
    tick_size: float = 0.01
    tick_value_per_lot: float = 1.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    spread_price: float = 0.0
    slippage_price: float = 0.0
    commission_per_lot_per_side: float = 0.0
    daily_drawdown_limit_pct: float | None = None
    max_drawdown_limit_pct: float | None = None
    max_positions: int = 1

    def __post_init__(self) -> None:
        if self.initial_equity <= 0 or not 0 < self.risk_percent <= 100:
            raise ValueError("initial_equity must be positive and risk_percent in (0, 100]")
        if min(self.tick_size, self.tick_value_per_lot, self.volume_min, self.volume_max, self.volume_step) <= 0:
            raise ValueError("Tick and volume specifications must be positive")
        if min(self.spread_price, self.slippage_price, self.commission_per_lot_per_side) < 0:
            raise ValueError("Costs cannot be negative")
        if self.max_positions != 1:
            raise ValueError("This reference backtester currently supports one open position")
        if self.daily_drawdown_limit_pct is not None and not 0 < self.daily_drawdown_limit_pct <= 100:
            raise ValueError("daily_drawdown_limit_pct must be in (0, 100]")
        if self.max_drawdown_limit_pct is not None and not 0 < self.max_drawdown_limit_pct <= 100:
            raise ValueError("max_drawdown_limit_pct must be in (0, 100]")


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.Series
    starting_equity: float


@dataclass
class _Position:
    signal: TradeSignal
    entry_time: pd.Timestamp
    entry_price: float
    lots: float
    risk_cash: float
    initial_risk_cash: float


class BacktestEngine:
    """Simulate market signals at the next bar open; no same-bar lookahead.

    Both stop and target touched in one candle is resolved as a stop. Entry and
    exit are charged half-spread plus adverse slippage each way. This is a
    conservative OHLC reference model, not a tick-accurate broker simulator.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    @staticmethod
    def _signal_bar(signal: TradeSignal, index: pd.DatetimeIndex) -> int:
        return int(index.searchsorted(signal.timestamp, side="right"))

    def _price_pnl(self, side: str, entry: float, exit_price: float, lots: float) -> float:
        direction = 1.0 if side == "buy" else -1.0
        return direction * (exit_price - entry) / self.config.tick_size * self.config.tick_value_per_lot * lots

    def _exit_fill(self, side: str, raw_price: float) -> float:
        direction = 1.0 if side == "buy" else -1.0
        return raw_price - direction * (self.config.spread_price / 2.0 + self.config.slippage_price)

    def _bar_exit(self, position: _Position, row: pd.Series) -> tuple[float, ExitReason] | None:
        signal = position.signal
        side = signal.side
        open_price = float(row["open"])
        if side == "buy":
            hit_stop = float(row["low"]) <= signal.stop_loss
            hit_target = float(row["high"]) >= signal.take_profit
            if hit_stop:
                return min(open_price, signal.stop_loss), "stop_loss"
            if hit_target:
                return max(open_price, signal.take_profit), "take_profit"
        else:
            hit_stop = float(row["high"]) >= signal.stop_loss
            hit_target = float(row["low"]) <= signal.take_profit
            if hit_stop:
                return max(open_price, signal.stop_loss), "stop_loss"
            if hit_target:
                return min(open_price, signal.take_profit), "take_profit"
        return None

    def run(self, frame: pd.DataFrame, signals: Iterable[TradeSignal]) -> BacktestResult:
        if frame.empty:
            raise ValueError("Cannot backtest an empty OHLCV frame")
        required = {"open", "high", "low", "close"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Bars are missing columns: {sorted(missing)}")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise TypeError("Backtest bars require a DatetimeIndex")
        if frame.index.tz is None:
            raise ValueError("Backtest timestamps must be timezone-aware; normalize input to UTC first")
        frame = frame.copy()
        frame.index = frame.index.tz_convert("UTC")
        if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
            raise ValueError("Backtest index must be strictly increasing and unique")
        prices = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
        if not np.isfinite(prices).all():
            raise ValueError("Backtest OHLC values must be finite")
        invalid_geometry = (
            (frame["high"] < frame[["open", "close"]].max(axis=1))
            | (frame["low"] > frame[["open", "close"]].min(axis=1))
            | (frame["high"] < frame["low"])
        )
        if invalid_geometry.any():
            raise ValueError("Backtest bars contain invalid OHLC geometry")

        signal_map: dict[int, list[TradeSignal]] = {}
        for signal in signals:
            bar = self._signal_bar(signal, frame.index)
            if bar < len(frame):
                signal_map.setdefault(bar, []).append(signal)

        guard = None
        if self.config.daily_drawdown_limit_pct is not None or self.config.max_drawdown_limit_pct is not None:
            guard = DailyDrawdownGuard(
                self.config.daily_drawdown_limit_pct or 100.0,
                max_drawdown_pct=self.config.max_drawdown_limit_pct,
            )

        cash_equity = float(self.config.initial_equity)
        position: _Position | None = None
        trade_rows: list[dict[str, object]] = []
        curve: list[float] = []
        curve_index: list[pd.Timestamp] = []

        def close_position(
            active: _Position,
            raw_exit: float,
            exit_time: pd.Timestamp,
            reason: ExitReason,
        ) -> float:
            nonlocal cash_equity
            exit_price = self._exit_fill(active.signal.side, raw_exit)
            gross = self._price_pnl(active.signal.side, active.entry_price, exit_price, active.lots)
            commission = 2.0 * self.config.commission_per_lot_per_side * active.lots
            pnl = gross - commission
            cash_equity += pnl
            trade_rows.append(
                {
                    "strategy": active.signal.strategy,
                    "side": active.signal.side,
                    "signal_time": active.signal.timestamp,
                    "entry_time": active.entry_time,
                    "exit_time": exit_time,
                    "entry_price": active.entry_price,
                    "exit_price": exit_price,
                    "stop_loss": active.signal.stop_loss,
                    "take_profit": active.signal.take_profit,
                    "lots": active.lots,
                    "confidence": active.signal.confidence,
                    "gross_pnl": gross,
                    "commission": commission,
                    "pnl": pnl,
                    "risk_cash": active.initial_risk_cash,
                    "r_multiple": pnl / active.initial_risk_cash if active.initial_risk_cash else np.nan,
                    "exit_reason": reason,
                }
            )
            return pnl

        for index, (timestamp, row) in enumerate(frame.iterrows()):
            flat_at_open = position is None
            if position is not None:
                exit_info = self._bar_exit(position, row)
                if exit_info is not None:
                    raw_exit, reason = exit_info
                    close_position(position, raw_exit, timestamp, reason)
                    position = None

            if flat_at_open and position is None:
                candidates = signal_map.get(index, [])
                sides = {candidate.side for candidate in candidates}
                if len(sides) == 1 and candidates:
                    selected = max(candidates, key=lambda item: item.confidence)
                    if guard is None or guard.check(cash_equity, timestamp).allowed:
                        direction = 1.0 if selected.side == "buy" else -1.0
                        fill = float(row["open"]) + direction * (
                            self.config.spread_price / 2.0 + self.config.slippage_price
                        )
                        correctly_sided = (
                            selected.stop_loss < fill < selected.take_profit
                            if selected.side == "buy"
                            else selected.take_profit < fill < selected.stop_loss
                        )
                        if correctly_sided:
                            size = size_position(
                                equity=cash_equity,
                                risk_percent=self.config.risk_percent,
                                entry=fill,
                                stop_loss=selected.stop_loss,
                                tick_size=self.config.tick_size,
                                tick_value_per_lot=self.config.tick_value_per_lot,
                                volume_min=self.config.volume_min,
                                volume_max=self.config.volume_max,
                                volume_step=self.config.volume_step,
                            )
                            if size.allowed:
                                risk_cash = abs(fill - selected.stop_loss) / self.config.tick_size
                                risk_cash *= self.config.tick_value_per_lot * size.lots
                                position = _Position(
                                    selected,
                                    timestamp,
                                    fill,
                                    size.lots,
                                    size.risk_cash,
                                    risk_cash,
                                )
                                # An entry candle may hit a stop or target. The
                                # same pessimistic, OHLC-only rule is applied.
                                exit_info = self._bar_exit(position, row)
                                if exit_info is not None:
                                    raw_exit, reason = exit_info
                                    close_position(position, raw_exit, timestamp, reason)
                                    position = None

            marked_equity = cash_equity
            if position is not None:
                direction = 1.0 if position.signal.side == "buy" else -1.0
                mark = float(row["close"]) - direction * (
                    self.config.spread_price / 2.0 + self.config.slippage_price
                )
                marked_equity += self._price_pnl(
                    position.signal.side, position.entry_price, mark, position.lots
                )
                marked_equity -= 2.0 * self.config.commission_per_lot_per_side * position.lots
            curve.append(float(marked_equity))
            curve_index.append(timestamp)

        if position is not None:
            last_time = frame.index[-1]
            raw_exit = float(frame["close"].iloc[-1])
            close_position(position, raw_exit, last_time, "end_of_data")
            curve[-1] = cash_equity

        trades = pd.DataFrame(
            trade_rows,
            columns=[
                "strategy", "side", "signal_time", "entry_time", "exit_time",
                "entry_price", "exit_price", "stop_loss", "take_profit", "lots",
                "confidence", "gross_pnl", "commission", "pnl", "risk_cash",
                "r_multiple", "exit_reason",
            ],
        )
        equity_curve = pd.Series(curve, index=pd.DatetimeIndex(curve_index), name="equity")
        return BacktestResult(trades, equity_curve, self.config.initial_equity)

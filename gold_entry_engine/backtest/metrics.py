"""Performance metrics with explicit behavior for empty and zero-loss samples."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .engine import BacktestResult


def _infer_periods_per_year(curve: pd.Series) -> float:
    """Infer a practical annualization factor from the median bar spacing."""
    if not isinstance(curve.index, pd.DatetimeIndex) or len(curve.index) < 2:
        return 252.0
    elapsed = curve.index.to_series().diff().dropna().dt.total_seconds()
    elapsed = elapsed[elapsed > 0]
    if elapsed.empty:
        return 252.0
    median_seconds = float(elapsed.median())
    if median_seconds >= 4 * 24 * 60 * 60:
        return 52.0
    # Use 252 trading days; for intraday data this scales by bars per 24h day.
    return 252.0 * 24.0 * 60.0 * 60.0 / median_seconds


def calculate_metrics(
    result: BacktestResult | pd.DataFrame,
    equity_curve: pd.Series | None = None,
    *,
    periods_per_year: float | None = None,
) -> dict[str, Any]:
    """Calculate trade/equity metrics; infer Sharpe annualization when omitted."""
    if isinstance(result, BacktestResult):
        trades = result.trades
        curve = result.equity_curve
        starting_equity = result.starting_equity
    else:
        trades = result
        curve = equity_curve if equity_curve is not None else pd.Series(dtype=float)
        starting_equity = float(curve.iloc[0]) if len(curve) else 0.0
    if periods_per_year is None:
        periods_per_year = _infer_periods_per_year(curve)
    if not math.isfinite(float(periods_per_year)) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be finite and positive")

    pnl = trades["pnl"].astype(float) if "pnl" in trades else pd.Series(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    total_trades = len(pnl)
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    final_equity = float(curve.iloc[-1]) if len(curve) else starting_equity
    total_return = (final_equity / starting_equity - 1.0) if starting_equity > 0 else 0.0

    if len(curve) and starting_equity > 0:
        values = np.concatenate(([float(starting_equity)], curve.astype(float).to_numpy()))
        running_peak = np.maximum.accumulate(values)
        drawdowns = np.divide(
            running_peak - values,
            running_peak,
            out=np.zeros_like(values),
            where=running_peak != 0,
        )
        maximum_drawdown = float(np.max(drawdowns))
        returns = np.diff(values) / values[:-1]
        returns = returns[np.isfinite(returns)]
        volatility = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
        sharpe = (
            float(np.mean(returns) / volatility * math.sqrt(periods_per_year))
            if volatility > 0
            else 0.0
        )
    else:
        maximum_drawdown = 0.0
        sharpe = 0.0
    average_r = float(trades["r_multiple"].mean()) if "r_multiple" in trades and total_trades else 0.0
    expectancy = float(pnl.mean()) if total_trades else 0.0

    return {
        "trades": total_trades,
        "wins": int((pnl > 0).sum()),
        "losses": int((pnl < 0).sum()),
        "win_rate": float((pnl > 0).mean()) if total_trades else 0.0,
        "profit_factor": float(profit_factor),
        "net_profit": float(pnl.sum()) if total_trades else 0.0,
        "total_return": float(total_return),
        "max_drawdown": maximum_drawdown,
        "sharpe": sharpe,
        "periods_per_year": float(periods_per_year),
        "expectancy_per_trade": expectancy,
        "average_r_multiple": average_r,
        "final_equity": final_equity,
    }

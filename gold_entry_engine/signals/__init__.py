"""Signal contracts, strategy implementations, and confluence aggregation."""

from .aggregator import SignalAggregator, aggregate_signals
from .base import BaseStrategy, TradeSignal
from .breakout_retest import BreakoutRetestStrategy
from .liquidity_sweep import LiquiditySweepStrategy
from .trend_pullback import TrendPullbackStrategy

__all__ = [
    "BaseStrategy",
    "BreakoutRetestStrategy",
    "LiquiditySweepStrategy",
    "SignalAggregator",
    "TradeSignal",
    "TrendPullbackStrategy",
    "aggregate_signals",
]

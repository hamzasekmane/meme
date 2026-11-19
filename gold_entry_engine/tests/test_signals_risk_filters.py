from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from gold_entry_engine.filters.news import NewsEvent, NewsFilter
from gold_entry_engine.filters.regime import Regime, classify_regime, filter_by_regime
from gold_entry_engine.filters.spread_filter import SpreadFilter, filter_by_spread
from gold_entry_engine.risk.drawdown import DailyDrawdownGuard
from gold_entry_engine.risk.sizing import size_position
from gold_entry_engine.risk.sl_tp import build_bracket
from gold_entry_engine.signals.aggregator import SignalAggregator
from gold_entry_engine.signals.base import TradeSignal
from gold_entry_engine.signals.breakout_retest import BreakoutRetestStrategy
from gold_entry_engine.signals.liquidity_sweep import LiquiditySweepStrategy
from gold_entry_engine.signals.trend_pullback import TrendPullbackStrategy


def make_signal(side="buy", *, timestamp="2024-01-01T00:00:00Z", strategy="test", confidence=70):
    return TradeSignal(
        strategy=strategy,
        side=side,
        timestamp=pd.Timestamp(timestamp),
        entry=100.0,
        stop_loss=95.0 if side == "buy" else 105.0,
        take_profit=110.0 if side == "buy" else 90.0,
        confidence=confidence,
        reason="fixture",
    )


def make_bars(index, opening, high, low, close):
    return pd.DataFrame(
        {"open": opening, "high": high, "low": low, "close": close, "volume": [1.0] * len(index)},
        index=index,
    )


class SignalTests(unittest.TestCase):
    def test_signal_contract_and_bracket_rounding(self):
        with self.assertRaises(ValueError):
            TradeSignal("x", "buy", pd.Timestamp("2024-01-01"), 100, 101, 110, 50)
        buy = build_bracket(
            "buy", entry=100.03, atr_value=2, tick_size=0.1,
            reward_risk=2, swing_low=98, stop_buffer_atr=0.25,
        )
        self.assertLess(buy.stop_loss, 98)
        self.assertGreaterEqual(buy.reward_risk, 2)
        with self.assertRaises(ValueError):
            build_bracket(
                "sell", entry=100, atr_value=1, tick_size=0.01,
                reward_risk=2, external_target=99,
            )

    def test_strategy_implementations_generate_closed_bar_signals(self):
        index = pd.date_range("2024-01-01", periods=7, freq="15min", tz="UTC")
        breakout_bars = make_bars(
            index,
            [8.5, 9, 9.2, 10, 9.9, 10.1, 10],
            [9, 10, 9.8, 12, 10.5, 10.8, 10.6],
            [8, 8.5, 8.7, 9.5, 9.8, 9.9, 9.7],
            [8.8, 9.5, 9.3, 11, 10.2, 10.3, 10.1],
        )
        breakout = BreakoutRetestStrategy(
            range_lookback=3, max_retest_bars=3, atr_period=1,
            retest_tolerance_atr=0.2, tick_size=0.01,
        ).generate(breakout_bars)
        self.assertTrue(any(signal.side == "buy" for signal in breakout))

        sweep_bars = make_bars(
            index[:5],
            [3, 4, 4, 4, 5],
            [4, 5, 4.8, 4.9, 6],
            [2, 3, 3.5, 3.6, 4],
            [3.5, 4.5, 4, 4.2, 4.7],
        )
        sweep = LiquiditySweepStrategy(
            lookback=3, min_sweep_atr=0.1, atr_period=1, reward_risk=1,
            require_reversal_candle=True,
        ).generate(sweep_bars)
        self.assertTrue(any(signal.side == "sell" for signal in sweep))

        trend_bars = make_bars(
            pd.date_range("2024-01-01", periods=9, freq="15min", tz="UTC"),
            [99, 100, 101, 101.9, 102, 102.5, 103, 103.5, 104],
            [100, 101, 102, 102.1, 103, 103.1, 104, 104.1, 105],
            [98, 99, 100, 101.4, 101.8, 102.1, 102.8, 103.1, 103.8],
            [99.5, 100.5, 101.5, 102, 102.8, 102.5, 103.7, 103.4, 104.7],
        )
        trend = TrendPullbackStrategy(
            fast_ema=2, slow_ema=3, rsi_period=2, atr_period=1,
            swing_lookback=3, reward_risk=1, tick_size=0.01,
        ).generate(trend_bars)
        self.assertIsInstance(trend, list)

    def test_aggregator_scores_agreement_and_rejects_directional_conflict(self):
        timestamp = "2024-01-01T00:00:00Z"
        buy1 = make_signal(timestamp=timestamp, strategy="a", confidence=70)
        buy2 = make_signal(timestamp=timestamp, strategy="b", confidence=80)
        aggregated = SignalAggregator(
            minimum_confidence=70, minimum_agreement=2, agreement_bonus=5,
            weights={"a": 1, "b": 2},
        ).aggregate([buy1, buy2])
        self.assertEqual(len(aggregated), 1)
        self.assertAlmostEqual(aggregated[0].confidence, 81.6666666667)
        self.assertEqual(aggregated[0].metadata["agreement_count"], 2)
        sell = make_signal("sell", timestamp=timestamp, strategy="c")
        self.assertEqual(SignalAggregator().aggregate([buy1, sell]), [])


class RiskAndFilterTests(unittest.TestCase):
    def test_risk_sizing_floors_and_skips_below_minimum(self):
        size = size_position(
            equity=10_000, risk_percent=0.5, entry=2_000, stop_loss=1_990,
            tick_size=0.01, tick_value_per_lot=1, volume_min=0.01,
            volume_step=0.01, volume_max=100,
        )
        self.assertAlmostEqual(size.lots, 0.05)
        self.assertLessEqual(size.estimated_loss_at_stop, size.risk_cash)
        too_small = size_position(
            equity=100, risk_percent=0.1, entry=2_000, stop_loss=1_000,
            tick_size=0.01, tick_value_per_lot=1, volume_min=0.01,
            volume_step=0.01, volume_max=100,
        )
        self.assertEqual(too_small.lots, 0)

    def test_drawdown_guard_locks_day_and_keeps_account_max_drawdown(self):
        guard = DailyDrawdownGuard(3, max_drawdown_pct=10)
        first = pd.Timestamp("2024-01-01T00:00:00Z")
        self.assertTrue(guard.check(10_000, first).allowed)
        daily_loss = guard.check(9_700, first + pd.Timedelta(hours=2))
        self.assertFalse(daily_loss.allowed)
        self.assertTrue(guard.check(9_700, first + pd.Timedelta(days=1)).allowed)
        max_loss = guard.check(8_900, first + pd.Timedelta(days=1, hours=1))
        self.assertFalse(max_loss.allowed)
        self.assertIn("maximum", max_loss.reason)

    def test_news_spread_and_regime_filters_are_fail_explicit(self):
        signal = make_signal(timestamp="2024-01-01T12:00:00Z")
        news = NewsFilter(
            [NewsEvent(pd.Timestamp("2024-01-01T12:15:00Z"), currency="USD", impact="high")],
            before_minutes=30, after_minutes=15,
        )
        self.assertTrue(news.is_blocked(signal.timestamp))
        self.assertEqual(news.filter_signals([signal]), [])
        self.assertTrue(NewsFilter(require_calendar=True).is_blocked(signal.timestamp))

        gate = SpreadFilter(max_spread_points=60, point_size=0.01, fail_closed=True)
        self.assertTrue(gate.allows(60))
        self.assertFalse(gate.allows(61))
        self.assertFalse(gate.allows(None))
        frame = pd.DataFrame({"spread": [61]}, index=pd.DatetimeIndex([signal.timestamp]))
        self.assertEqual(filter_by_spread([signal], frame, max_spread_points=60, point_size=0.01), [])

        index = pd.date_range("2024-01-01", periods=80, freq="h", tz="UTC")
        close = np.linspace(100, 140, len(index))
        bars = make_bars(index, close - 0.1, close + 0.5, close - 0.5, close)
        regimes = classify_regime(
            bars, atr_period=3, ema_period=5, slope_lookback=2,
            volatility_window=10, trend_atr_threshold=0.1,
        )
        trend_signal = make_signal(timestamp=index[-1], strategy="trend")
        self.assertEqual(filter_by_regime([trend_signal], regimes, allowed=[Regime.TREND]), [trend_signal])


if __name__ == "__main__":
    unittest.main(verbosity=2)

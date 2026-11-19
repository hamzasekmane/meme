from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from gold_entry_engine.backtest.engine import BacktestConfig, BacktestEngine
from gold_entry_engine.backtest.metrics import calculate_metrics
from gold_entry_engine.backtest.walk_forward import (
    run_walk_forward,
    walk_forward_splits,
)
from gold_entry_engine.output.formatter import (
    format_signal,
    signal_to_dict,
    to_json_compatible,
)
from gold_entry_engine.output.notifier import FileNotifier, MT5Notifier
from gold_entry_engine.signals.base import TradeSignal


def signal_at(timestamp, *, side="buy", entry=100, stop=95, target=103):
    return TradeSignal(
        strategy="test", side=side, timestamp=timestamp, entry=entry,
        stop_loss=stop, take_profit=target, confidence=75, reason="fixture",
    )


def backtest_bars(index, opens, highs, lows, closes):
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1] * len(index)},
        index=index,
    )


class BacktestTests(unittest.TestCase):
    def _engine(self):
        return BacktestEngine(
            BacktestConfig(
                initial_equity=1_000, risk_percent=10, tick_size=1,
                tick_value_per_lot=1, volume_min=1, volume_step=1,
                volume_max=100, spread_price=0, slippage_price=0,
            )
        )

    def test_entry_occurs_next_bar_and_target_closes_trade(self):
        index = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
        frame = backtest_bars(index, [100, 100, 103], [101, 104, 104], [99, 99, 102], [100, 103, 103])
        signal = signal_at(index[0])
        result = self._engine().run(frame, [signal])
        self.assertEqual(len(result.trades), 1)
        trade = result.trades.iloc[0]
        self.assertEqual(trade["entry_time"], index[1])
        self.assertEqual(trade["exit_reason"], "take_profit")
        self.assertGreater(trade["pnl"], 0)

    def test_same_candle_stop_and_target_uses_stop_first(self):
        index = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
        frame = backtest_bars(index, [100, 100], [101, 104], [99, 94], [100, 101])
        result = self._engine().run(frame, [signal_at(index[0])])
        self.assertEqual(result.trades.iloc[0]["exit_reason"], "stop_loss")
        self.assertLess(result.trades.iloc[0]["pnl"], 0)
        self.assertAlmostEqual(calculate_metrics(result)["max_drawdown"], 0.1)

    def test_spread_slippage_and_end_of_data_are_recorded(self):
        index = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
        frame = backtest_bars(index, [100, 100, 101], [101, 102, 102], [99, 99, 100], [100, 101, 101])
        config = BacktestConfig(
            initial_equity=1_000, risk_percent=10, tick_size=1, tick_value_per_lot=1,
            volume_min=1, volume_step=1, volume_max=100, spread_price=0.2,
            slippage_price=0.1,
        )
        result = BacktestEngine(config).run(frame, [signal_at(index[0], target=110)])
        self.assertEqual(result.trades.iloc[0]["exit_reason"], "end_of_data")
        self.assertEqual(len(result.equity_curve), len(frame))

    def test_metrics_handle_empty_and_nonempty_samples(self):
        index = pd.date_range("2024-01-01", periods=3, freq="h", tz="UTC")
        frame = backtest_bars(index, [100, 100, 103], [101, 104, 104], [99, 99, 102], [100, 103, 103])
        result = self._engine().run(frame, [signal_at(index[0])])
        metrics = calculate_metrics(result)
        self.assertEqual(metrics["trades"], 1)
        self.assertGreater(metrics["profit_factor"], 0)
        empty = calculate_metrics(pd.DataFrame(columns=["pnl"]), pd.Series(dtype=float))
        self.assertEqual(empty["trades"], 0)
        self.assertEqual(empty["win_rate"], 0)


class WalkForwardAndOutputTests(unittest.TestCase):
    def test_walk_forward_windows_are_chronological_and_held_out(self):
        index = pd.date_range("2024-01-01", periods=20, freq="h", tz="UTC")
        frame = pd.DataFrame({"close": range(20)}, index=index)
        splits = walk_forward_splits(frame, train_bars=8, test_bars=4, step_bars=4)
        self.assertEqual(len(splits), 3)
        self.assertLess(splits[0].train_end, splits[0].test_start)
        self.assertEqual(len(splits[1].train), 8)

        seen = []
        result = run_walk_forward(
            frame,
            train_bars=8,
            test_bars=4,
            fit=lambda train: (seen.append((train.index[0], train.index[-1])) or train["close"].mean()),
            evaluate=lambda model, test: {"train_mean": model, "test_mean": test["close"].mean()},
            step_bars=4,
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(len(seen), 3)

    def test_formatter_serializes_numpy_and_notifiers_write_without_trading(self):
        signal = signal_at(pd.Timestamp("2024-01-01T00:00:00Z"))
        self.assertIn("SIGNAL PLAN", format_signal(signal))
        payload = signal_to_dict(signal)
        self.assertEqual(payload["side"], "buy")
        self.assertEqual(to_json_compatible({"n": np.int64(5), "bad": float("inf")}), {"n": 5, "bad": None})
        json.dumps(payload, allow_nan=False)
        captured = []
        MT5Notifier(captured.append).send("test message")
        self.assertEqual(captured, ["test message"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "alerts.txt"
            FileNotifier(target).send("proposal only")
            self.assertEqual(target.read_text(encoding="utf-8"), "proposal only\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)

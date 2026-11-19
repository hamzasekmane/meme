from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from gold_entry_engine.backtest.engine import BacktestConfig
from gold_entry_engine.main import run_research
from gold_entry_engine.research import (
    parameter_grid_search,
    walk_forward_parameter_search,
)


class CliResearchTests(unittest.TestCase):
    def test_main_pipeline_reads_csv_and_writes_json_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = pd.date_range("2024-01-01", periods=40, freq="15min", tz="UTC")
            close = [2000 + i * 0.2 for i in range(len(index))]
            frame = pd.DataFrame(
                {
                    "time": index.astype(str),
                    "open": close,
                    "high": [value + 0.5 for value in close],
                    "low": [value - 0.5 for value in close],
                    "close": close,
                    "volume": [100] * len(index),
                }
            )
            csv_path = root / "prices.csv"
            frame.to_csv(csv_path, index=False)
            settings_path = root / "settings.yaml"
            settings_path.write_text(
                yaml.safe_dump(
                    {
                        "symbol": "XAUUSD",
                        "source_timezone": "UTC",
                        "strategy": "liquidity_sweep",
                        "risk": {
                            "starting_equity": 10000,
                            "risk_per_trade_pct": 0.5,
                            "tick_size": 0.01,
                            "tick_value_per_lot": 1,
                            "volume_min": 0.01,
                            "volume_max": 100,
                            "volume_step": 0.01,
                        },
                        "backtest": {"max_positions": 1},
                        "filters": {},
                        "output": {"log_file": str(root / "engine.log")},
                    }
                ),
                encoding="utf-8",
            )
            strategies_path = root / "strategies.yaml"
            strategies_path.write_text(yaml.safe_dump({"liquidity_sweep": {"lookback": 5, "atr_period": 2}}), encoding="utf-8")
            report_path = root / "report.json"
            report = run_research(
                csv_path,
                settings_path=settings_path,
                strategies_path=strategies_path,
                output_path=report_path,
            )
            disk_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["bars"], 40)
            self.assertEqual(disk_report["note"], "Historical simulation only; no live orders were sent.")
            self.assertTrue((root / "engine.log").is_file())

    def test_grid_search_and_walk_forward_output_shape(self):
        index = pd.date_range("2024-01-01", periods=120, freq="h", tz="UTC")
        close = [100 + i * 0.05 + (0.3 if (i // 4) % 2 else 0) for i in range(len(index))]
        frame = pd.DataFrame(
            {
                "open": close,
                "high": [value + 0.5 for value in close],
                "low": [value - 0.5 for value in close],
                "close": close,
                "volume": [10] * len(index),
            },
            index=index,
        )
        config = BacktestConfig(tick_size=0.01, tick_value_per_lot=1)
        grid = parameter_grid_search(frame, backtest_config=config, fast_periods=(2, 3), slow_periods=(5, 8))
        self.assertGreaterEqual(len(grid), 1)
        walk = walk_forward_parameter_search(
            frame,
            backtest_config=config,
            train_bars=60,
            test_bars=20,
            fast_periods=(2, 3),
            slow_periods=(5, 8),
            step_bars=20,
        )
        self.assertEqual(len(walk), 3)
        self.assertIn("test_start", walk.columns)
        self.assertIn("fast_ema", walk.columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)

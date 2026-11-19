"""Small parameter-sweep and walk-forward utilities (not investment advice)."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

from gold_entry_engine.backtest.engine import BacktestConfig, BacktestEngine
from gold_entry_engine.backtest.metrics import calculate_metrics
from gold_entry_engine.backtest.walk_forward import walk_forward_splits
from gold_entry_engine.config import default_settings_path, load_yaml
from gold_entry_engine.data.loader import load_csv
from gold_entry_engine.signals.trend_pullback import TrendPullbackStrategy


def _make_strategy(parameters: dict[str, int], tick_size: float) -> TrendPullbackStrategy:
    return TrendPullbackStrategy(
        fast_ema=parameters["fast_ema"],
        slow_ema=parameters["slow_ema"],
        tick_size=tick_size,
    )


def parameter_grid_search(
    frame: pd.DataFrame,
    *,
    backtest_config: BacktestConfig,
    fast_periods: Iterable[int] = (10, 20),
    slow_periods: Iterable[int] = (40, 50, 60),
    objective: str = "total_return",
) -> pd.DataFrame:
    """Evaluate an explicit EMA parameter grid on the supplied sample."""
    rows: list[dict[str, Any]] = []
    for fast, slow in product(fast_periods, slow_periods):
        if fast >= slow:
            continue
        params = {"fast_ema": int(fast), "slow_ema": int(slow)}
        strategy = _make_strategy(params, backtest_config.tick_size)
        signals = strategy.generate(frame)
        result = BacktestEngine(backtest_config).run(frame, signals)
        metrics = calculate_metrics(result)
        rows.append({**params, **metrics, "objective": objective})
    if not rows:
        return pd.DataFrame(columns=["fast_ema", "slow_ema", "trades", objective])
    results = pd.DataFrame(rows)
    if objective not in results.columns:
        raise ValueError(f"Unknown objective: {objective}")
    return results.sort_values(objective, ascending=False, kind="stable").reset_index(drop=True)


def walk_forward_parameter_search(
    frame: pd.DataFrame,
    *,
    backtest_config: BacktestConfig,
    train_bars: int,
    test_bars: int,
    fast_periods: Iterable[int] = (10, 20),
    slow_periods: Iterable[int] = (40, 50, 60),
    step_bars: int | None = None,
    expanding: bool = False,
    objective: str = "total_return",
) -> pd.DataFrame:
    """Select EMA values on each train fold, then evaluate only its test fold.

    The training history is included as indicator warm-up for test signal
    generation; only signals timestamped inside the held-out test window can
    enter the test backtest.
    """
    rows: list[dict[str, Any]] = []
    for split in walk_forward_splits(
        frame,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        expanding=expanding,
    ):
        training_grid = parameter_grid_search(
            split.train,
            backtest_config=backtest_config,
            fast_periods=fast_periods,
            slow_periods=slow_periods,
            objective=objective,
        )
        if training_grid.empty:
            continue
        selected = {
            "fast_ema": int(training_grid.iloc[0]["fast_ema"]),
            "slow_ema": int(training_grid.iloc[0]["slow_ema"]),
        }
        warm_and_test = pd.concat([split.train, split.test])
        strategy = _make_strategy(selected, backtest_config.tick_size)
        all_signals = strategy.generate(warm_and_test)
        test_signals = [
            signal for signal in all_signals
            if split.test_start <= signal.timestamp <= split.test_end
        ]
        test_result = BacktestEngine(backtest_config).run(split.test, test_signals)
        metrics = calculate_metrics(test_result)
        rows.append(
            {
                "fold": split.fold,
                "train_start": split.train_start,
                "train_end": split.train_end,
                "test_start": split.test_start,
                "test_end": split.test_end,
                **selected,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _backtest_config(settings: dict[str, Any]) -> BacktestConfig:
    risk = settings.get("risk", {})
    costs = settings.get("backtest", {})
    return BacktestConfig(
        initial_equity=float(risk.get("starting_equity", 10_000)),
        risk_percent=float(risk.get("risk_per_trade_pct", 0.5)),
        tick_size=float(risk.get("tick_size", 0.01)),
        tick_value_per_lot=float(risk.get("tick_value_per_lot", 1.0)),
        volume_min=float(risk.get("volume_min", 0.01)),
        volume_max=float(risk.get("volume_max", 100)),
        volume_step=float(risk.get("volume_step", 0.01)),
        spread_price=float(costs.get("spread_price", 0.0)),
        slippage_price=float(costs.get("slippage_price", 0.0)),
        commission_per_lot_per_side=float(costs.get("commission_per_lot", 0.0)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="OHLCV CSV path")
    parser.add_argument("--settings", default=str(default_settings_path()))
    parser.add_argument("--output", default="results/research.csv")
    parser.add_argument("--train-bars", type=int, help="Enable walk-forward mode with this training window")
    parser.add_argument("--test-bars", type=int, help="Required with --train-bars")
    parser.add_argument("--step-bars", type=int)
    parser.add_argument("--objective", default="total_return")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_yaml(args.settings)
    frame = load_csv(args.data, source_timezone=str(settings.get("source_timezone", "UTC")))
    config = _backtest_config(settings)
    if args.train_bars is not None:
        if args.test_bars is None:
            raise SystemExit("--test-bars is required with --train-bars")
        results = walk_forward_parameter_search(
            frame,
            backtest_config=config,
            train_bars=args.train_bars,
            test_bars=args.test_bars,
            step_bars=args.step_bars,
            objective=args.objective,
        )
    else:
        results = parameter_grid_search(frame, backtest_config=config, objective=args.objective)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(destination, index=False)
    print(f"Wrote {len(results)} research row(s) to {destination}")
    print("Exploratory historical statistics only; parameter selection is not evidence of future performance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

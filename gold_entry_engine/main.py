"""CSV-to-signal-to-backtest command-line entry point (research only)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gold_entry_engine.backtest.engine import BacktestConfig, BacktestEngine
from gold_entry_engine.backtest.metrics import calculate_metrics
from gold_entry_engine.config import (
    default_settings_path,
    default_strategies_path,
    load_yaml,
)
from gold_entry_engine.data.loader import load_csv
from gold_entry_engine.filters.news import NewsFilter
from gold_entry_engine.filters.regime import classify_regime, filter_by_regime
from gold_entry_engine.filters.spread_filter import filter_by_spread
from gold_entry_engine.output.formatter import signal_to_dict, to_json_compatible
from gold_entry_engine.output.logger import get_logger
from gold_entry_engine.signals.aggregator import SignalAggregator
from gold_entry_engine.signals.breakout_retest import BreakoutRetestStrategy
from gold_entry_engine.signals.liquidity_sweep import LiquiditySweepStrategy
from gold_entry_engine.signals.trend_pullback import TrendPullbackStrategy

_STRATEGIES = {
    "trend_pullback": TrendPullbackStrategy,
    "breakout_retest": BreakoutRetestStrategy,
    "liquidity_sweep": LiquiditySweepStrategy,
}


def _build_strategy(name: str, options: dict[str, Any], tick_size: float):
    if name not in _STRATEGIES:
        raise ValueError(f"Unknown strategy {name!r}; choose from {', '.join(_STRATEGIES)}")
    arguments = dict(options)
    arguments.setdefault("tick_size", tick_size)
    return _STRATEGIES[name](**arguments)


def _backtest_config(settings: dict[str, Any]) -> BacktestConfig:
    risk = settings.get("risk", {})
    backtest = settings.get("backtest", {})
    return BacktestConfig(
        initial_equity=float(risk.get("starting_equity", 10_000.0)),
        risk_percent=float(risk.get("risk_per_trade_pct", 0.5)),
        tick_size=float(risk.get("tick_size", 0.01)),
        tick_value_per_lot=float(risk.get("tick_value_per_lot", 1.0)),
        volume_min=float(risk.get("volume_min", 0.01)),
        volume_max=float(risk.get("volume_max", 100.0)),
        volume_step=float(risk.get("volume_step", 0.01)),
        spread_price=float(backtest.get("spread_price", 0.0)),
        slippage_price=float(backtest.get("slippage_price", 0.0)),
        commission_per_lot_per_side=float(backtest.get("commission_per_lot", 0.0)),
        daily_drawdown_limit_pct=risk.get("daily_drawdown_limit_pct"),
        max_positions=int(backtest.get("max_positions", 1)),
    )


def run_research(
    data_path: str | Path,
    *,
    settings_path: str | Path | None = None,
    strategies_path: str | Path | None = None,
    strategy_names: Sequence[str] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load a CSV, generate/filter signals, and run the offline simulator."""
    settings_file = Path(settings_path) if settings_path else default_settings_path()
    strategies_file = Path(strategies_path) if strategies_path else default_strategies_path()
    settings = load_yaml(settings_file)
    strategy_settings = load_yaml(strategies_file)
    source_timezone = str(settings.get("source_timezone", "UTC"))
    bars = load_csv(data_path, source_timezone=source_timezone)
    if len(bars) < 2:
        raise ValueError("At least two valid bars are required")

    names = list(strategy_names or [str(settings.get("strategy", "liquidity_sweep"))])
    if not names:
        raise ValueError("At least one strategy must be selected")
    tick_size = float(settings.get("risk", {}).get("tick_size", 0.01))
    signals = []
    for name in names:
        options = dict(strategy_settings.get(name, {}))
        strategy = _build_strategy(name, options, tick_size)
        signals.extend(strategy.generate(bars))

    filters = settings.get("filters", {})
    if bool(filters.get("use_regime_filter", False)):
        indicator_config = settings.get("indicators", {})
        regimes = classify_regime(
            bars,
            atr_period=int(indicator_config.get("atr_period", 14)),
        )
        allowed = filters.get("allowed_regimes", ["trend"])
        signals = filter_by_regime(signals, regimes, allowed=allowed)

    if "spread" in bars.columns:
        signals = filter_by_spread(
            signals,
            bars,
            max_spread_points=float(filters.get("max_spread_points", 60)),
            point_size=float(filters.get("point_size", tick_size)),
            fail_closed=bool(filters.get("spread_fail_closed", False)),
        )

    news_path = filters.get("news_csv")
    if news_path:
        news_file = Path(news_path)
        if not news_file.is_absolute():
            news_file = Path.cwd() / news_file
        news_filter = NewsFilter.from_csv(
            news_file,
            before_minutes=int(filters.get("news_blackout_before_minutes", 30)),
            after_minutes=int(filters.get("news_blackout_after_minutes", 15)),
            require_calendar=bool(filters.get("require_news_calendar", False)),
        )
        signals = news_filter.filter_signals(signals)
    elif bool(filters.get("require_news_calendar", False)):
        signals = NewsFilter(
            require_calendar=True,
            before_minutes=int(filters.get("news_blackout_before_minutes", 30)),
            after_minutes=int(filters.get("news_blackout_after_minutes", 15)),
        ).filter_signals(signals)

    if len(names) > 1:
        aggregation = strategy_settings.get("aggregator", {})
        signals = SignalAggregator(
            minimum_confidence=float(aggregation.get("minimum_confidence", 60)),
            minimum_agreement=int(aggregation.get("minimum_agreement", 1)),
            agreement_bonus=float(aggregation.get("agreement_bonus", 5)),
            weights=aggregation.get("weights", {}),
        ).aggregate(signals)

    result = BacktestEngine(_backtest_config(settings)).run(bars, signals)
    metrics = calculate_metrics(result)
    report = {
        "symbol": settings.get("symbol", "XAUUSD"),
        "data_file": str(Path(data_path)),
        "bars": len(bars),
        "strategies": names,
        "signals": [signal_to_dict(signal) for signal in signals],
        "metrics": metrics,
        "trades": result.trades,
        "equity_curve": result.equity_curve,
        "note": "Historical simulation only; no live orders were sent.",
    }

    destination = output_path or settings.get("output", {}).get("report_file")
    logger_path = settings.get("output", {}).get("log_file")
    logger = get_logger(log_file=logger_path)
    logger.info("Backtest complete: %d bars, %d signals, %d trades", len(bars), len(signals), len(result.trades))
    if destination:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(to_json_compatible(report), indent=2, allow_nan=False),
            encoding="utf-8",
        )
        logger.info("Report written to %s", target)
    return to_json_compatible(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="OHLCV CSV path")
    parser.add_argument("--settings", default=str(default_settings_path()))
    parser.add_argument("--strategies", default=str(default_strategies_path()))
    parser.add_argument(
        "--strategy",
        help="Comma-separated strategy names; defaults to config setting",
    )
    parser.add_argument("--output", help="JSON report path; overrides settings")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    names = [name.strip() for name in args.strategy.split(",") if name.strip()] if args.strategy else None
    report = run_research(
        args.data,
        settings_path=args.settings,
        strategies_path=args.strategies,
        strategy_names=names,
        output_path=args.output,
    )
    print(json.dumps(report["metrics"], indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

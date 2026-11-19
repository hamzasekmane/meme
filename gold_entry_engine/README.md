# Gold Entry Engine (research toolkit)

This Python package implements the requested modular XAUUSD research pipeline:
CSV / optional MT5 / caller-provided API data, UTC normalization, M5–D1
resampling, indicators and market-structure/liquidity features, independent
signal strategies, safety filters, risk calculations, an OHLC backtester,
metrics, and chronological walk-forward tools.

> **Important:** this is a research/backtesting toolkit, not financial advice and
> not a live trading bot. No module places orders. Historical results are not a
> forecast. XAUUSD tick value, tick size, lot contract, spread, and commission
> are broker-specific; the YAML values are examples only. Verify the exact
> broker symbol contract and validate the rule set on out-of-sample/demo data.

## Install and run

From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\\Scripts\\activate
pip install -r gold_entry_engine/requirements.txt
python -m gold_entry_engine.main --data path/to/XAUUSD_M15.csv
```

The CSV should have a timestamp column (`time`, `timestamp`, `datetime`, or
`date`) plus `open,high,low,close`; `volume` is optional. A `spread` column is
interpreted as broker points when applying the spread filter. Naive timestamps
are interpreted using `source_timezone` in `config/settings.yaml`; all internal
timestamps are converted to UTC. Missing bars are reported, never fabricated.

Select any one strategy or combine several (conflicting same-time buy/sell
signals are rejected):

```bash
python -m gold_entry_engine.main --data prices.csv \\
  --strategy trend_pullback,liquidity_sweep --output results/report.json
```

Available strategies: `trend_pullback`, `breakout_retest`, and
`liquidity_sweep`. Strategy parameters and example settings live in
`config/strategies.yaml` and `config/settings.yaml`.

Parameter exploration and walk-forward testing:

```bash
python -m gold_entry_engine.research --data prices.csv --output results/grid.csv
python -m gold_entry_engine.research --data prices.csv \\
  --train-bars 5000 --test-bars 1000 --step-bars 1000
```

Walk-forward mode selects EMA parameters only on each training window, then
simulates only the following held-out window. It is still vulnerable to data
quality issues and repeated research/selection; treat it as a validation tool,
not proof of profitability.

## Design notes

- `data/cleaner.py` enforces valid OHLC geometry, sorts bars, normalizes to UTC,
  removes duplicate timestamps (last record wins), and does not fill gaps.
- `features/structure.py` publishes a swing only at its confirmation bar;
  `features/zones.py` and `features/liquidity.py` retain formation/mitigation
  times so features can be queried as-of a historical timestamp.
- Every strategy implements `BaseStrategy.generate(...) -> list[TradeSignal]`.
  A `TradeSignal` is a proposed plan, not an execution instruction.
- The backtester enters at the next bar's open, charges half-spread/slippage on
  each side, and resolves a candle that hits both SL and TP in favor of the
  stop. It is a conservative bar-level model, not tick-accurate execution.
- Risk sizing floors to the configured volume step and skips a trade if minimum
  lot size would exceed the requested risk budget.
- `load_mt5_rates` lazily imports MetaTrader5 and uses an already-initialized
  terminal connection. `load_api` accepts a user-supplied fetch function; no
  API key, terminal connection, or news calendar is embedded in the package.
- Telegram notifications use `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from
  the environment. `MT5Notifier` only invokes a caller-injected message
  callback; it does not send orders.

## Tests

Run the package tests and existing MQL5 source tests from the repository root:

```bash
.venv/bin/python -m unittest discover -s gold_entry_engine/tests -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/static_mql_analysis.py
```

The portable Python tests validate calculations/contracts, not MetaTrader
compilation, broker behavior, live feeds, profitability, or strategy validity.

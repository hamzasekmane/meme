"""CSV, MetaTrader 5, and caller-supplied API adapters for OHLCV data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .cleaner import clean_ohlcv

_MT5_TIMEFRAMES = {
    "M1": "TIMEFRAME_M1",
    "M2": "TIMEFRAME_M2",
    "M3": "TIMEFRAME_M3",
    "M4": "TIMEFRAME_M4",
    "M5": "TIMEFRAME_M5",
    "M6": "TIMEFRAME_M6",
    "M10": "TIMEFRAME_M10",
    "M12": "TIMEFRAME_M12",
    "M15": "TIMEFRAME_M15",
    "M20": "TIMEFRAME_M20",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H2": "TIMEFRAME_H2",
    "H3": "TIMEFRAME_H3",
    "H4": "TIMEFRAME_H4",
    "H6": "TIMEFRAME_H6",
    "H8": "TIMEFRAME_H8",
    "H12": "TIMEFRAME_H12",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
    "MN1": "TIMEFRAME_MN1",
}


def load_csv(
    path: str | Path,
    *,
    timestamp_column: str | None = None,
    source_timezone: str = "UTC",
    **read_csv_kwargs: Any,
) -> pd.DataFrame:
    """Read a CSV and return the shared, validated UTC OHLCV representation."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    frame = pd.read_csv(source, **read_csv_kwargs)
    return clean_ohlcv(
        frame,
        timestamp_column=timestamp_column,
        source_timezone=source_timezone,
    )


def load_mt5_rates(
    symbol: str,
    timeframe: str,
    count: int,
    *,
    start_pos: int = 0,
    mt5_module: Any | None = None,
) -> pd.DataFrame:
    """Fetch rates from an already initialized MetaTrader5 Python connection.

    ``MetaTrader5`` is imported lazily, so CSV research does not require the
    Windows-only terminal package. This function neither initializes nor shuts
    down the caller's terminal connection.
    """
    if count <= 0 or start_pos < 0:
        raise ValueError("count must be positive and start_pos non-negative")
    mt5 = mt5_module
    if mt5 is None:
        try:
            import MetaTrader5 as mt5  # type: ignore[no-redef, import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 package is optional and unavailable; install it in a supported MT5 environment"
            ) from exc

    code_name = _MT5_TIMEFRAMES.get(str(timeframe).upper())
    if code_name is None or not hasattr(mt5, code_name):
        raise ValueError(f"Unsupported MT5 timeframe: {timeframe}")
    rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, code_name), start_pos, count)
    if rates is None:
        error = mt5.last_error() if hasattr(mt5, "last_error") else "unknown terminal error"
        raise RuntimeError(f"MT5 returned no rates for {symbol} {timeframe}: {error}")
    if len(rates) == 0:
        raise ValueError(f"MT5 returned an empty rate set for {symbol} {timeframe}")

    frame = pd.DataFrame(rates)
    if "time" not in frame:
        raise ValueError("MT5 rates did not include the required epoch 'time' field")
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    return clean_ohlcv(frame, timestamp_column="time")


def load_api(
    fetcher: Callable[..., Any],
    *,
    timestamp_column: str | None = None,
    source_timezone: str = "UTC",
    **fetch_kwargs: Any,
) -> pd.DataFrame:
    """Normalize results from a user-provided market-data API callable.

    The fetcher should return a DataFrame or an iterable of OHLCV mappings. The
    engine intentionally leaves authentication, rate limits, and vendor schema
    handling with that adapter instead of embedding vendor credentials.
    """
    payload = fetcher(**fetch_kwargs)
    if payload is None:
        raise RuntimeError("Market-data API returned no payload")
    if isinstance(payload, pd.DataFrame):
        frame = payload
    elif isinstance(payload, Mapping) and "data" in payload:
        frame = pd.DataFrame(payload["data"])
    else:
        frame = pd.DataFrame(payload)
    return clean_ohlcv(
        frame,
        timestamp_column=timestamp_column,
        source_timezone=source_timezone,
    )

"""Normalize strategy signals and pandas/numpy values for logs and JSON."""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from ..signals.base import TradeSignal


def signal_to_dict(signal: TradeSignal) -> dict[str, Any]:
    return {
        "timestamp": signal.timestamp.isoformat(),
        "strategy": signal.strategy,
        "side": signal.side,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "reward_risk": signal.reward_risk,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "metadata": to_json_compatible(dict(signal.metadata)),
    }


def format_signal(signal: TradeSignal) -> str:
    """Human-readable notification; label it as a proposal, not an execution."""
    return (
        f"SIGNAL PLAN | {signal.side.upper()} {signal.strategy} | "
        f"{signal.timestamp.isoformat()} | entry={signal.entry:.2f} "
        f"SL={signal.stop_loss:.2f} TP={signal.take_profit:.2f} "
        f"RR={signal.reward_risk:.2f} confidence={signal.confidence:.0f}/100"
    )


def to_json_compatible(value: Any) -> Any:
    """Recursively convert pandas, numpy, dataclasses, and non-finite floats."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return to_json_compatible(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_compatible(item) for item in value]
    if is_dataclass(value):
        return to_json_compatible(asdict(value))
    if isinstance(value, pd.DataFrame):
        return [to_json_compatible(record) for record in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return [to_json_compatible(item) for item in value.to_list()]
    if hasattr(value, "value"):
        return to_json_compatible(value.value)
    return str(value)

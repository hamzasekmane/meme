"""Chronological train/test slicing and callback-based walk-forward evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class WalkForwardSplit:
    fold: int
    train: pd.DataFrame
    test: pd.DataFrame
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def walk_forward_splits(
    frame: pd.DataFrame,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    expanding: bool = False,
) -> list[WalkForwardSplit]:
    """Create ordered train/test folds; no row appears in its own training fold."""
    if train_bars < 1 or test_bars < 1:
        raise ValueError("train_bars and test_bars must be positive")
    step = test_bars if step_bars is None else step_bars
    if step < 1:
        raise ValueError("step_bars must be positive")
    if not isinstance(frame.index, pd.DatetimeIndex) or not frame.index.is_monotonic_increasing:
        raise ValueError("Walk-forward data must have a sorted DatetimeIndex")

    splits: list[WalkForwardSplit] = []
    test_start = train_bars
    fold = 0
    while test_start + test_bars <= len(frame):
        train_start = 0 if expanding else test_start - train_bars
        train = frame.iloc[train_start:test_start].copy()
        test = frame.iloc[test_start : test_start + test_bars].copy()
        splits.append(
            WalkForwardSplit(
                fold=fold,
                train=train,
                test=test,
                train_start=train.index[0],
                train_end=train.index[-1],
                test_start=test.index[0],
                test_end=test.index[-1],
            )
        )
        test_start += step
        fold += 1
    return splits


def run_walk_forward(
    frame: pd.DataFrame,
    *,
    train_bars: int,
    test_bars: int,
    fit: Callable[[pd.DataFrame], Any],
    evaluate: Callable[[Any, pd.DataFrame], Any],
    step_bars: int | None = None,
    expanding: bool = False,
) -> pd.DataFrame:
    """Fit on each training window and report callback results on its test only.

    The ``fit`` callback owns parameter selection; it only receives training
    rows. ``evaluate`` receives the fitted object and held-out test rows. Its
    result may be a mapping of metrics or a scalar score.
    """
    splits = walk_forward_splits(
        frame,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        expanding=expanding,
    )
    records: list[dict[str, Any]] = []
    for split in splits:
        model = fit(split.train.copy())
        outcome = evaluate(model, split.test.copy())
        record: dict[str, Any] = {
            "fold": split.fold,
            "train_start": split.train_start,
            "train_end": split.train_end,
            "test_start": split.test_start,
            "test_end": split.test_end,
        }
        if isinstance(outcome, dict):
            record.update(outcome)
        else:
            record["score"] = outcome
        records.append(record)
    return pd.DataFrame(records)

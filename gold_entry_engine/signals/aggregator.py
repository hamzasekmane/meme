"""Confluence scoring with explicit conflict rejection."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .base import TradeSignal


@dataclass
class SignalAggregator:
    minimum_confidence: float = 60.0
    minimum_agreement: int = 1
    agreement_bonus: float = 5.0
    weights: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_confidence <= 100:
            raise ValueError("minimum_confidence must be in [0, 100]")
        if self.minimum_agreement < 1 or self.agreement_bonus < 0:
            raise ValueError("minimum_agreement must be >= 1 and agreement_bonus non-negative")
        if any(value <= 0 for value in self.weights.values()):
            raise ValueError("strategy weights must be positive")

    def aggregate(self, signals: Iterable[TradeSignal]) -> list[TradeSignal]:
        by_time: dict[object, dict[str, dict[str, TradeSignal]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for signal in signals:
            current = by_time[signal.timestamp][signal.side].get(signal.strategy)
            if current is None or signal.confidence > current.confidence:
                by_time[signal.timestamp][signal.side][signal.strategy] = signal

        combined: list[TradeSignal] = []
        for timestamp in sorted(by_time):
            sides = by_time[timestamp]
            # A simultaneous directional conflict is ambiguous; fail closed.
            if len(sides) != 1:
                continue
            side, strategy_map = next(iter(sides.items()))
            contributors = list(strategy_map.values())
            if len(contributors) < self.minimum_agreement:
                continue
            weights = [float(self.weights.get(signal.strategy, 1.0)) for signal in contributors]
            base_score = sum(signal.confidence * weight for signal, weight in zip(contributors, weights)) / sum(weights)
            score = min(100.0, base_score + self.agreement_bonus * (len(contributors) - 1))
            if score < self.minimum_confidence:
                continue
            leader = max(contributors, key=lambda signal: (signal.confidence, self.weights.get(signal.strategy, 1.0)))
            names = sorted(signal.strategy for signal in contributors)
            metadata = dict(leader.metadata)
            metadata["supporting_strategies"] = names
            metadata["strategy_confidences"] = {
                signal.strategy: signal.confidence for signal in contributors
            }
            metadata["base_confidence"] = base_score
            metadata["agreement_count"] = len(contributors)
            combined.append(
                TradeSignal(
                    strategy="+".join(names),
                    side=side,
                    timestamp=timestamp,
                    entry=leader.entry,
                    stop_loss=leader.stop_loss,
                    take_profit=leader.take_profit,
                    confidence=score,
                    reason="Confluence: " + "; ".join(
                        signal.reason or signal.strategy for signal in contributors
                    ),
                    metadata=metadata,
                )
            )
        return combined


def aggregate_signals(
    signals: Iterable[TradeSignal],
    *,
    minimum_confidence: float = 60.0,
    minimum_agreement: int = 1,
    agreement_bonus: float = 5.0,
    weights: Mapping[str, float] | None = None,
) -> list[TradeSignal]:
    """Convenience wrapper around :class:`SignalAggregator`."""
    return SignalAggregator(
        minimum_confidence=minimum_confidence,
        minimum_agreement=minimum_agreement,
        agreement_bonus=agreement_bonus,
        weights=weights or {},
    ).aggregate(signals)

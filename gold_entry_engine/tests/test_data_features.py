from __future__ import annotations

import unittest
import warnings

import numpy as np
import pandas as pd

from gold_entry_engine.data.cleaner import clean_ohlcv, find_gaps
from gold_entry_engine.data.loader import load_api, load_mt5_rates
from gold_entry_engine.data.resampler import build_timeframes, resample_ohlcv
from gold_entry_engine.features.indicators import atr, ema, rsi, vwap
from gold_entry_engine.features.liquidity import (
    detect_sweeps,
    find_equal_highs_lows,
    previous_day_levels,
)
from gold_entry_engine.features.sessions import active_session_flags, classify_session
from gold_entry_engine.features.structure import detect_swings, market_structure
from gold_entry_engine.features.zones import (
    find_fvgs,
    find_order_blocks,
    find_support_resistance,
)


def bars(index, opening, high, low, close, volume=None):
    return pd.DataFrame(
        {
            "open": opening,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume or [1.0] * len(index),
        },
        index=index,
    )


class DataPipelineTests(unittest.TestCase):
    def test_cleaner_sorts_deduplicates_converts_timezone_and_prefers_tick_volume(self):
        frame = pd.DataFrame(
            {
                "DateTime": ["2024-01-02 09:31", "2024-01-02 09:30", "2024-01-02 09:30"],
                "Open": [2011, 2010, 2010],
                "High": [2013, 2012, 2012.5],
                "Low": [2010, 2009, 2008.5],
                "Close": [2012, 2011, 2012],
                "tick_volume": [10, 20, 30],
                "real_volume": [1, 2, 3],
            }
        )
        cleaned = clean_ohlcv(frame, source_timezone="America/New_York")
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(str(cleaned.index.tz), "UTC")
        self.assertEqual(cleaned.index[0], pd.Timestamp("2024-01-02 14:30", tz="UTC"))
        self.assertEqual(cleaned.iloc[0]["volume"], 30)
        self.assertTrue(cleaned.index.is_monotonic_increasing)

    def test_cleaner_drops_invalid_geometry_with_warning_and_gap_report(self):
        index = pd.date_range("2024-01-01", periods=4, freq="min", tz="UTC")
        raw = pd.DataFrame(
            {
                "time": [index[0], index[1], index[3]],
                "open": [10, 10, 10],
                "high": [11, 9, 11],  # the middle bar is invalid
                "low": [9, 10, 9],
                "close": [10, 10, 10],
                "volume": [1, 1, 1],
            }
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cleaned = clean_ohlcv(raw)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(len(caught), 1)
        gaps = find_gaps(cleaned, "1min")
        self.assertEqual(int(gaps.iloc[0]["missing_bars"]), 2)
        with self.assertRaises(ValueError):
            clean_ohlcv(raw, drop_invalid=False)

    def test_load_api_and_mt5_adapters_are_lazy_and_normalized(self):
        api_data = [
            {"time": "2024-02-01T00:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5},
        ]
        api_frame = load_api(lambda **kwargs: api_data)
        self.assertEqual(len(api_frame), 1)
        self.assertEqual(api_frame.iloc[0]["volume"], 0.0)

        class FakeMT5:
            TIMEFRAME_M15 = 15

            @staticmethod
            def copy_rates_from_pos(symbol, timeframe, start_pos, count):
                return np.array(
                    [(1706745600, 1.0, 2.0, 0.5, 1.5, 100, 90, 12)],
                    dtype=[
                        ("time", "i8"), ("open", "f8"), ("high", "f8"),
                        ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"),
                        ("spread", "i8"), ("real_volume", "i8"),
                    ],
                )

        mt5_frame = load_mt5_rates("XAUUSD", "M15", 10, mt5_module=FakeMT5)
        self.assertEqual(mt5_frame.iloc[0]["volume"], 100)
        self.assertEqual(mt5_frame.iloc[0]["spread"], 90)

    def test_resampler_aggregates_ohlcv_and_can_drop_partial_groups(self):
        index = pd.date_range("2024-01-01", periods=12, freq="min", tz="UTC")
        frame = bars(index, list(range(100, 112)), list(range(101, 113)),
                     list(range(99, 111)), list(range(100, 112)))
        frame["spread"] = [2] * 11 + [10]
        five = resample_ohlcv(frame, "M5", source_timeframe="M1", complete_only=True)
        self.assertEqual(len(five), 2)
        self.assertEqual(five.iloc[0]["open"], 100)
        self.assertEqual(five.iloc[0]["close"], 104)
        self.assertEqual(five.iloc[0]["volume"], 5)
        self.assertEqual(five.iloc[1]["spread"], 2)
        with self.assertRaises(ValueError):
            resample_ohlcv(frame, "M1", source_timeframe="M5")
        frames = build_timeframes(frame, ("M5", "M15"), source_timeframe="M1")
        self.assertEqual(set(frames), {"M5", "M15"})


class FeatureTests(unittest.TestCase):
    def test_indicator_warmups_and_values(self):
        index = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
        frame = bars(index, [9, 10, 11, 12], [10, 12, 13, 14], [8, 9, 11, 11], [9, 11, 12, 13], [1, 3, 2, 4])
        values = atr(frame, 2)
        self.assertTrue(np.isnan(values.iloc[0]))
        self.assertAlmostEqual(values.iloc[1], 2.5)
        self.assertAlmostEqual(values.iloc[2], 2.25)
        self.assertTrue(np.isnan(ema(frame["close"], 3).iloc[0]))
        self.assertEqual(rsi(pd.Series([1, 2, 3, 4], index=index), 2).iloc[-1], 100.0)
        self.assertAlmostEqual(vwap(frame).iloc[0], (10 + 8 + 9) / 3)

    def test_swings_appear_only_after_right_side_confirmation_and_breaks(self):
        index = pd.date_range("2024-01-01", periods=7, freq="h", tz="UTC")
        frame = bars(
            index,
            [1.5, 2, 3, 3, 3, 5, 5],
            [2, 3, 5, 3.5, 4, 6, 5.5],
            [1, 1.5, 2, 2.5, 2.8, 3, 4],
            [1.5, 2.5, 4, 3, 3.2, 5.5, 5],
        )
        swings = detect_swings(frame, left=1, right=1)
        self.assertTrue(np.isnan(swings.loc[index[2], "swing_high"]))
        self.assertEqual(swings.loc[index[3], "swing_high"], 5)
        self.assertEqual(swings.loc[index[3], "swing_high_pivot_time"], index[2])
        structure = market_structure(frame, left=1, right=1)
        self.assertEqual(structure.loc[index[5], "structure_event"], "BOS_UP")

    def test_fvg_and_order_block_zones_keep_lifecycle_timestamps(self):
        index = pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC")
        fvg_bars = bars(index, [9, 10, 12, 12, 10], [10, 11, 14, 13, 12],
                        [8, 9, 12, 11, 9], [9, 10, 13, 12, 10])
        fvgs = find_fvgs(fvg_bars)
        bullish = next(zone for zone in fvgs if zone.side == "buy")
        self.assertEqual((bullish.lower, bullish.upper), (10.0, 12.0))
        self.assertEqual(bullish.mitigated_at, index[3])
        self.assertFalse(bullish.active_at(index[3]))
        self.assertTrue(bullish.active_at(index[2]))

        ob_bars = bars(
            index,
            [10, 10.5, 10, 12.8, 12.5],
            [11, 11, 10.5, 13, 13],
            [9, 9, 9.5, 10.5, 10],
            [10.5, 10, 12.8, 12, 11],
        )
        order_blocks = find_order_blocks(ob_bars, atr_period=1, displacement_atr=0.5, lookback=3)
        self.assertTrue(any(zone.side == "buy" and zone.source_at == index[1] for zone in order_blocks))

    def test_support_resistance_and_equal_liquidity_pools(self):
        index = pd.date_range("2024-01-01", periods=8, freq="h", tz="UTC")
        frame = bars(
            index,
            [8.5, 9, 8.5, 8.7, 9.3, 8.5, 9.8, 8.5],
            [9, 10, 9, 9.4, 10.05, 9.2, 10.6, 9],
            [8, 8.5, 8.2, 8.3, 8.4, 8.2, 8.3, 8.1],
            [8.5, 9.5, 8.8, 9, 9.6, 8.8, 9.8, 8.7],
        )
        pools = find_equal_highs_lows(frame, left=1, right=1, lookback=20, atr_period=1,
                                      tolerance_atr=0.2, min_touches=2)
        eqh = next(pool for pool in pools if pool.kind == "EQH")
        self.assertAlmostEqual(eqh.price, 10.025)
        self.assertEqual(eqh.available_at, index[5])
        sweeps = detect_sweeps(frame, [eqh], min_wick_atr=0.1, atr_period=1)
        self.assertTrue(any(event.side == "sell" and event.timestamp == index[6] for event in sweeps))
        zones = find_support_resistance(frame, left=1, right=1, atr_period=1)
        self.assertTrue(any(zone.kind == "resistance" for zone in zones))

    def test_previous_day_levels_are_previous_completed_day_only(self):
        index = pd.date_range("2024-01-01", periods=6, freq="12h", tz="UTC")
        frame = bars(index, [1] * 6, [2, 3, 4, 5, 6, 7], [0, -0.1, 1, 2, 3, 4], [1] * 6)
        levels = previous_day_levels(frame)
        self.assertTrue(np.isnan(levels.iloc[0]["pdh"]))
        self.assertEqual(levels.iloc[2]["pdh"], 3)
        self.assertEqual(levels.iloc[2]["pdl"], -0.1)

    def test_session_flags_preserve_overlap_and_dst(self):
        timestamps = pd.DatetimeIndex(
            [pd.Timestamp("2024-01-02 08:30", tz="UTC"), pd.Timestamp("2024-06-03 13:00", tz="UTC")]
        )
        flags = active_session_flags(timestamps)
        self.assertTrue(flags.loc[timestamps[0], "London"])
        self.assertTrue(flags.loc[timestamps[0], "Asia"])
        self.assertEqual(classify_session(timestamps[0]), "London")
        self.assertTrue(flags.loc[timestamps[1], "New_York"])
        self.assertTrue(flags.loc[timestamps[1], "London"])
        self.assertEqual(classify_session(timestamps[1]), "New_York")


if __name__ == "__main__":
    unittest.main(verbosity=2)

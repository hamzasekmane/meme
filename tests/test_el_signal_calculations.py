"""Deterministic signal/plan calculations for the documented EL rule contract.

This is a Python reference model with source-contract assertions, not execution of
MQL bytecode. MetaEditor/MT5 integration is still required for compiler/runtime proof.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def make_plan(side, zone_top, zone_bottom, sweep_extreme, atr, sl_buffer_atr,
              external_target, current_price, minimum_rr):
    entry = (zone_top + zone_bottom) / 2.0
    sl = sweep_extreme - atr * sl_buffer_atr if side == "buy" else sweep_extreme + atr * sl_buffer_atr
    risk = entry - sl if side == "buy" else sl - entry
    if risk <= 0:
        return None
    if side == "buy":
        if current_price <= entry or external_target <= max(entry + risk * minimum_rr, current_price):
            return None
        reward = external_target - entry
    else:
        if current_price >= entry or external_target >= min(entry - risk * minimum_rr, current_price):
            return None
        reward = entry - external_target
    rr = reward / risk
    if rr + 1e-8 < minimum_rr:
        return None
    return {"entry": entry, "sl": sl, "tp": external_target, "risk": risk,
            "reward": reward, "rr": rr, "side": side}


def floor_tick(price, tick):
    import math
    return round(math.floor(price / tick + 1e-10) * tick, 8)


def ceil_tick(price, tick):
    import math
    return round(math.ceil(price / tick - 1e-10) * tick, 8)


def valid_limit_plan(plan, bid, ask, tick, stop_points=0, point=0.01, rr_min=2.0):
    if plan is None:
        return False
    side = plan["side"]
    entry = floor_tick(plan["entry"], tick) if side == "buy" else ceil_tick(plan["entry"], tick)
    sl = floor_tick(plan["sl"], tick) if side == "buy" else ceil_tick(plan["sl"], tick)
    tp = round(round(plan["tp"] / tick) * tick, 8)
    distance = max(stop_points * point, tick)
    if side == "buy":
        if not (entry < ask - distance and sl < entry - distance and tp > entry + distance):
            return False
        risk, reward = entry - sl, tp - entry
    else:
        if not (entry > bid + distance and sl > entry + distance and tp < entry - distance):
            return False
        risk, reward = sl - entry, entry - tp
    return risk > 0 and reward / risk + 1e-8 >= rr_min


class SignalCalculationTests(unittest.TestCase):
    def test_sell_plan_uses_zone_midpoint_sweep_extreme_and_external_target(self):
        plan = make_plan("sell", 3955, 3950, 4010, 10, 0.25, 3830, 3900, 2.0)
        self.assertEqual(plan["entry"], 3952.5)
        self.assertEqual(plan["sl"], 4012.5)
        self.assertEqual(plan["tp"], 3830)
        self.assertAlmostEqual(plan["rr"], 122.5 / 60.0)
        source = (ROOT / "Include/EL/EL_Signal.mqh").read_text()
        self.assertIn("double entry=(zt+zb)*0.5;", source)
        self.assertIn("sw.extreme+buf", source)

    def test_buy_plan_uses_zone_midpoint_sweep_extreme_and_external_target(self):
        plan = make_plan("buy", 3780, 3770, 3720, 10, 0.25, 3895, 3800, 2.0)
        self.assertEqual(plan["entry"], 3775)
        self.assertEqual(plan["sl"], 3717.5)
        self.assertEqual(plan["tp"], 3895)
        self.assertAlmostEqual(plan["rr"], 120 / 57.5)
        source = (ROOT / "Include/EL/EL_Signal.mqh").read_text()
        self.assertIn("sw.extreme-buf", source)

    def test_target_without_rr_or_current_side_confluence_produces_no_plan(self):
        self.assertIsNone(make_plan("sell", 3955, 3950, 4010, 10, 0.25, 3900, 3905, 2.0))
        self.assertIsNone(make_plan("buy", 3780, 3770, 3720, 10, 0.25, 3800, 3801, 2.0))
        src = (ROOT / "Include/EL/EL_Signal.mqh").read_text()
        self.assertIn("if(tp<=0) return;", src)
        self.assertNotIn("fixed-R fallback", src.split("double tp=0;", 1)[-1].split("if(tp<=0)", 1)[0])

    def test_sell_limit_geometry_and_structural_stop_round_outward(self):
        plan = make_plan("sell", 3955, 3950, 4010, 10, 0.25, 3830, 3900, 2.0)
        self.assertTrue(valid_limit_plan(plan, bid=3900, ask=3900.1, tick=0.01))
        self.assertGreaterEqual(ceil_tick(plan["sl"], 0.01), plan["sl"])
        self.assertFalse(valid_limit_plan(plan, bid=3953, ask=3953.1, tick=0.01))

    def test_buy_limit_geometry_and_structural_stop_round_outward(self):
        plan = make_plan("buy", 3780, 3770, 3720, 10, 0.25, 3895, 3800, 2.0)
        self.assertTrue(valid_limit_plan(plan, bid=3800, ask=3800.1, tick=0.01))
        self.assertLessEqual(floor_tick(plan["sl"], 0.01), plan["sl"])
        self.assertFalse(valid_limit_plan(plan, bid=3774.9, ask=3775, tick=0.01))

    def test_rr_is_recomputed_after_price_grid_mapping(self):
        plan = make_plan("sell", 3955.01, 3950.02, 4010, 10, 0.25, 3830, 3900, 2.0)
        self.assertIsNotNone(plan)
        self.assertTrue(valid_limit_plan(plan, bid=3900, ask=3900.1, tick=0.01))
        src = (ROOT / "Include/EL/EL_Validation.mqh").read_text()
        self.assertIn("reward/risk+1e-8<rrMin", src)

    def test_final_plan_fields_flow_to_shared_engine_indicator_and_ea(self):
        signal = (ROOT / "Include/EL/EL_Signal.mqh").read_text()
        engine = (ROOT / "Include/EL/EL_Engine.mqh").read_text()
        indicator = (ROOT / "Indicators/EL_Indicator.mq5").read_text()
        ea = (ROOT / "Experts/EL_EA.mq5").read_text()
        self.assertIn("s.entry=entry; s.sl=sl; s.tp=tp;", signal)
        self.assertIn("EL_ValidateLimitPlan(sym,sig.dir,sig.entry,sig.sl,sig.tp", engine)
        self.assertIn("Line(\"EL_ENTRY\", tNow, s.entry", indicator)
        self.assertIn("trd.PlaceLimit(_Symbol, s, lots, expiry)", ea)


if __name__ == "__main__":
    unittest.main(verbosity=2)

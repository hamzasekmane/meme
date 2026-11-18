"""Portable regression contracts for EL source.

These tests do not emulate the MetaTrader terminal. They exercise price-plan
geometry using XAUUSD-style fixture specs and assert that the MQL5 implementation
contains the corresponding guards. Compile/runtime behavior still requires MT5.
"""
from pathlib import Path
import math
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def plan_valid(side, entry, sl, tp, bid, ask, point=0.01, tick=0.01,
               stops_points=0, min_rr=2.0):
    """Mirror EL_ValidateLimitPlan's XAUUSD geometry for deterministic fixtures."""
    distance = max(stops_points * point, tick)
    if side == "sell":
        if entry <= bid + distance or sl <= entry + distance or tp >= entry - distance:
            return False
        risk, reward = sl - entry, entry - tp
    elif side == "buy":
        if entry >= ask - distance or sl >= entry - distance or tp <= entry + distance:
            return False
        risk, reward = entry - sl, tp - entry
    else:
        return False
    return risk > 0 and reward > 0 and reward / risk + 1e-8 >= min_rr


def market_entry_matches_quote(side, entry, bid, ask, tick=0.01):
    executable = ask if side == "buy" else bid if side == "sell" else None
    return executable is not None and abs(entry - executable) <= tick


def order_block_valid(side, top, bottom, later_closes):
    if side == "sell":
        return not any(close > top for close in later_closes)
    if side == "buy":
        return not any(close < bottom for close in later_closes)
    return False


def sweep_still_current(side, pool, sweep_high, sweep_low, sweep_close,
                        later_bars, min_wick):
    if side == "sell":
        if not (sweep_high > pool + min_wick and sweep_close < pool):
            return False
        return not any(close > pool or high > pool for high, low, close in later_bars)
    if side == "buy":
        if not (sweep_low < pool - min_wick and sweep_close > pool):
            return False
        return not any(close < pool or low < pool for high, low, close in later_bars)
    return False


def displacement_confirmed(body, atr, min_atr):
    return atr > 0 and body >= atr * min_atr


def mss_confirmed(side, post_sweep_closes, broken_level):
    if side == "sell":
        return any(close < broken_level for close in post_sweep_closes)
    if side == "buy":
        return any(close > broken_level for close in post_sweep_closes)
    return False


def execution_timeframe_allowed(tf):
    return tf == "M15"


class ELRegressionContracts(unittest.TestCase):
    def test_01_sell_entry_far_above_market_is_only_a_pending_candidate(self):
        # The entry is 185.53 above the displayed market: a retracement-limit candidate,
        # not an immediate market SELL. D1 remains analytical-only.
        self.assertAlmostEqual(3952.86 - 3767.33, 185.53)
        self.assertFalse(market_entry_matches_quote("sell", 3952.86, 3767.33, 3767.43))
        self.assertFalse(execution_timeframe_allowed("D1"))
        # The provided prices are ~1.99995R, so a strict 2R gate rejects them;
        # one more valid tick of target distance makes the geometry acceptable.
        self.assertFalse(plan_valid("sell", 3952.86, 4170.84, 3516.91, 3767.33, 3767.43))
        self.assertTrue(plan_valid("sell", 3952.86, 4170.84, 3516.90, 3767.33, 3767.43))
        engine = read("Include/EL/EL_Engine.mqh")
        self.assertIn("if(tf!=PERIOD_M15)", engine)
        self.assertIn("ANALYTICAL ONLY", engine)

    def test_02_buy_entry_far_below_market_is_only_a_pending_candidate(self):
        self.assertAlmostEqual(3767.33 - 3700.00, 67.33)
        self.assertTrue(plan_valid("buy", 3700.00, 3600.00, 3900.00, 3767.33, 3767.43))
        self.assertFalse(market_entry_matches_quote("buy", 3700.00, 3767.33, 3767.43))
        self.assertIn("if(tf!=PERIOD_M15)", read("Include/EL/EL_Engine.mqh"))

    def test_03_valid_sell_limit_retracement(self):
        self.assertTrue(plan_valid("sell", 3780, 3800, 3730, 3767, 3768, min_rr=2.0))

    def test_04_valid_buy_limit_retracement(self):
        self.assertTrue(plan_valid("buy", 3750, 3730, 3790, 3767, 3768, min_rr=2.0))

    def test_05_invalid_market_entry_and_wrong_side_limits_are_rejected(self):
        self.assertFalse(market_entry_matches_quote("sell", 3952.86, 3767.33, 3767.43))
        self.assertFalse(market_entry_matches_quote("buy", 3700.00, 3767.33, 3767.43))
        self.assertFalse(plan_valid("sell", 3760, 3780, 3720, 3767, 3768))
        self.assertFalse(plan_valid("buy", 3770, 3750, 3810, 3767, 3768))
        types = read("Include/EL/EL_Types.mqh")
        trade = read("Include/EL/EL_Trade.mqh")
        self.assertIn("EL_ENTRY_MARKET", types)
        self.assertIn("s.entryKind!=EL_ENTRY_BUY_LIMIT", trade)
        self.assertIn("s.entryKind!=EL_ENTRY_SELL_LIMIT", trade)
        self.assertIn("EL_ValidateLimitPlan", trade)

    def test_06_stale_or_invalidated_order_block_is_rejected(self):
        # Bearish OB high is invalidated by a newer closed close above its top;
        # a later close still inside the range leaves the candidate valid.
        self.assertTrue(order_block_valid("sell", 3820, 3800, [3812, 3819]))
        self.assertFalse(order_block_valid("sell", 3820, 3800, [3812, 3821]))
        self.assertTrue(order_block_valid("buy", 3780, 3760, [3764, 3770]))
        self.assertFalse(order_block_valid("buy", 3780, 3760, [3764, 3759]))
        zones = read("Include/EL/EL_Zones.mqh")
        self.assertIn("for(int j=1;j<i;j++)", zones)
        self.assertIn("if(invalidated) continue;", zones)

    def test_07_invalidated_liquidity_sweep_is_not_reused(self):
        self.assertTrue(sweep_still_current("sell", 100, 102, 99, 99, [], 1))
        self.assertFalse(sweep_still_current("sell", 100, 102, 99, 99, [(100.2, 98, 99)], 1))
        self.assertTrue(sweep_still_current("buy", 100, 101, 98, 101, [], 1))
        self.assertFalse(sweep_still_current("buy", 100, 101, 98, 101, [(102, 99.8, 101)], 1))
        sweep = read("Include/EL/EL_Sweep.mqh")
        self.assertIn("r[k].close > pools[pi].price || r[k].high > pools[pi].price", sweep)
        self.assertIn("r[k].close < pools[pi].price || r[k].low < pools[pi].price", sweep)
        self.assertIn("pools[pi].available > r[s].time", sweep)

    def test_08_missing_displacement_blocks_signal_plan(self):
        self.assertFalse(displacement_confirmed(body=4.9, atr=10, min_atr=0.5))
        self.assertTrue(displacement_confirmed(body=5.0, atr=10, min_atr=0.5))
        signal = read("Include/EL/EL_Signal.mqh")
        self.assertIn("body<breakAtr*p.minDisplacementATR", signal)
        self.assertIn("s.displacementConfirmed=true", signal)

    def test_09_missing_mss_blocks_signal_plan(self):
        self.assertFalse(mss_confirmed("sell", [101, 100.5, 100.1], 100))
        self.assertTrue(mss_confirmed("sell", [101, 99.9], 100))
        self.assertFalse(mss_confirmed("buy", [99, 99.5, 99.9], 100))
        self.assertTrue(mss_confirmed("buy", [99, 100.1], 100))
        signal = read("Include/EL/EL_Signal.mqh")
        self.assertIn("if(!bk.found) return;", signal)
        self.assertIn("s.structureConfirmed=true", signal)

    def test_10_incorrect_timeframe_reference_cannot_authorize_execution(self):
        self.assertTrue(execution_timeframe_allowed("M15"))
        for wrong_tf in ("D1", "H4", "H1", "M5", "M30"):
            self.assertFalse(execution_timeframe_allowed(wrong_tf))
        mtf = read("Include/EL/EL_MTF.mqh")
        engine = read("Include/EL/EL_Engine.mqh")
        self.assertIn("PERIOD_D1", mtf)
        self.assertIn("PERIOD_H4", mtf)
        self.assertIn("PERIOD_H1", mtf)
        self.assertIn("CopyRates(sym,PERIOD_M5", mtf)
        self.assertIn("if(tf!=PERIOD_M15)", engine)

    def test_11_wide_structural_stop_is_not_arbitrarily_clipped(self):
        risk = read("Include/EL/EL_Risk.mqh")
        self.assertIn("double dist = MathAbs(entry - sl);", risk)
        self.assertNotIn("MathMin(dist", risk)
        # Geometry accepts the structural stop when target RR is adequate.
        self.assertTrue(plan_valid("sell", 3800, 4000, 3350, 3760, 3761, min_rr=2.0))

    def test_12_invalid_tp_direction_is_rejected(self):
        self.assertFalse(plan_valid("sell", 3780, 3800, 3790, 3767, 3768))
        self.assertFalse(plan_valid("buy", 3750, 3730, 3740, 3767, 3768))

    def test_13_incorrect_rr_is_rejected_without_fixed_rr_fallback(self):
        self.assertFalse(plan_valid("sell", 3780, 3800, 3750, 3767, 3768, min_rr=2.0))
        signal = read("Include/EL/EL_Signal.mqh")
        self.assertIn("if(tp<=0) return;", signal)
        self.assertNotIn("tp=(dir==EL_BUY)? entry+risk*p.rrMin", signal)

    def test_14_indicator_and_ea_require_shared_execution_ready_flag(self):
        types = read("Include/EL/EL_Types.mqh")
        engine = read("Include/EL/EL_Engine.mqh")
        ea = read("Experts/EL_EA.mq5")
        indicator = read("Indicators/EL_Indicator.mq5")
        self.assertIn("bool executionReady;", types)
        self.assertIn("sig.executionReady=true;", engine)
        self.assertIn("if(!s.executionReady)", ea)
        self.assertIn("if(s.executionReady)", indicator)

    def test_15_new_bar_refresh_uses_closed_bar_and_clears_stale_signal(self):
        engine = read("Include/EL/EL_Engine.mqh")
        signal = read("Include/EL/EL_Signal.mqh")
        indicator = read("Indicators/EL_Indicator.mq5")
        self.assertIn("sg.Reset(sig);", engine)
        self.assertIn("double px=r[1].close;", signal)
        self.assertIn("datetime cur=iTime(_Symbol,(ENUM_TIMEFRAMES)_Period,0);", indicator)

    def test_closed_bar_fvg_and_structure_confirmation_are_enforced(self):
        zones = read("Include/EL/EL_Zones.mqh")
        structure = read("Include/EL/EL_Structure.mqh")
        self.assertIn("for(int j=1;j<i;j++)", zones)
        self.assertIn("lo[i].bar>sw.bar+swingLR", structure)
        self.assertIn("hi[i].bar>sw.bar+swingLR", structure)

    def test_consumed_external_liquidity_target_fails_closed(self):
        signal = read("Include/EL/EL_Signal.mqh")
        self.assertIn("EL_TargetUntouchedSinceAvailable", signal)
        self.assertIn("if(count<1) return false;", signal)
        self.assertIn("history[j].high>=pool.price", signal)
        self.assertIn("history[j].low<=pool.price", signal)

    def test_price_rounding_uses_tick_size_and_broker_stop_level(self):
        validation = read("Include/EL/EL_Validation.mqh")
        self.assertIn("SYMBOL_TRADE_TICK_SIZE", validation)
        self.assertIn("SYMBOL_TRADE_STOPS_LEVEL", validation)
        self.assertIn("MathRound(price/tick)*tick", validation)

    def test_actual_broker_xauusd_audit_harness_reads_contract_and_sends_no_orders(self):
        harness = read("tests/EL_XAUUSD_BrokerAudit.mq5")
        self.assertIn('InpBrokerSymbol = "XAUUSD"', harness)
        self.assertIn("SYMBOL_TRADE_TICK_SIZE", harness)
        self.assertIn("SYMBOL_TRADE_TICK_VALUE", harness)
        self.assertIn("SYMBOL_VOLUME_MIN", harness)
        self.assertIn("SYMBOL_TRADE_STOPS_LEVEL", harness)
        self.assertIn("SYMBOL_EXPIRATION_MODE", harness)
        self.assertIn("EL_ValidateLimitPlan", harness)
        self.assertIn("EL_LotsByRisk", harness)
        self.assertNotIn("OrderSend(", harness)
        self.assertIn("NO ORDERS SENT", harness)

    def test_risk_parameters_and_sizing_are_not_changed_to_mask_entry_defects(self):
        inputs = read("Include/EL/EL_Inputs.mqh")
        ea = read("Experts/EL_EA.mq5")
        self.assertIn("InpSLBufATR     = 0.25", inputs)
        self.assertIn("InpRRMin        = 2.0", inputs)
        self.assertIn("InpRiskPct      = 0.5", ea)
        risk = read("Include/EL/EL_Risk.mqh")
        self.assertIn("double dist = MathAbs(entry - sl);", risk)
        self.assertIn("double lossPerLot = (dist / tickSize) * tickVal;", risk)
        self.assertNotIn("MathMin(dist", risk)

    def test_new_strategy_gates_are_explicit_and_documented(self):
        inputs = read("Include/EL/EL_Inputs.mqh")
        report = read("AUDIT_REPORT.md")
        self.assertIn("InpMinDisplacementATR = 0.50", inputs)
        self.assertIn("strategy-impact notes", report)
        self.assertIn("M15 execution, D1/H4/H1 alignment, M5 confirmation", report)

    def test_pending_order_expiry_never_falls_back_to_gtc(self):
        trade = read("Include/EL/EL_Trade.mqh")
        self.assertIn("SYMBOL_EXPIRATION_SPECIFIED", trade)
        self.assertIn("ORDER_TIME_SPECIFIED", trade)
        self.assertNotIn("ORDER_TIME_GTC", trade)


if __name__ == "__main__":
    unittest.main(verbosity=2)

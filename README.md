# Engineered Liquidity (EL) Trading System — MQL5 (XAUUSD)

An institutional-grade algorithmic trading system written in pure, modern **MQL5**, based on **Smart Money Concepts (SMC)** and **Engineered Liquidity**. Optimized specifically for **Gold (XAUUSD)**.

---

## 🏗 System Architecture

The codebase is built on a modular design where a single central orchestration engine (`CELEngine`) powers both the Expert Advisor (`EL_EA.mq5`) and the visual Chart Indicator (`EL_Indicator.mq5`).

```
├── Experts/
│   └── EL_EA.mq5           # Automated Expert Advisor with Risk Management & Order Execution
├── Indicators/
│   └── EL_Indicator.mq5    # Live visual HUD (Pools, OB, FVG, Entry/SL/TP & Signal Arrows)
└── Include/EL/
    ├── EL_Types.mqh        # Core data structures (Swings, Pools, Sweeps, Zones, Signals)
    ├── EL_Config.mqh       # Parameter struct (ELParams)
    ├── EL_Inputs.mqh       # External input definitions
    ├── EL_Swings.mqh       # Fractal swing high/low detection (Anti-repainting)
    ├── EL_Liquidity.mqh    # Liquidity pools (EQH/EQL, SWH/SWL, PDH/PDL, PWH/PWL, Asia Range)
    ├── EL_Sweep.mqh        # True liquidity sweep detection & invalidation filtering
    ├── EL_Structure.mqh    # Market Structure Shift (MSS / CHoCH) confirmation
    ├── EL_Zones.mqh        # Institutional Order Block (OB) and Fair Value Gap (FVG)
    ├── EL_Signal.mqh       # Multi-factor confluence scoring engine (0-100)
    ├── EL_Filters.mqh      # Session Killzones, Spread filter, and News blackout
    ├── EL_Risk.mqh         # Fractional equity risk sizing & free margin validation
    ├── EL_Trade.mqh        # CTrade wrapper, broker expiration fallback & BE management
    └── EL_Engine.mqh       # Central orchestrator synchronizing all modules
```

---

## ⚙️ Core Trading Mechanics

1. **Liquidity Mapping (`EL_Liquidity`):**
   - **Equal Highs / Equal Lows (EQH / EQL)** within ATR tolerance.
   - **Previous Day High / Low (PDH / PDL)** and **Previous Week High / Low (PWH / PWL)**.
   - **Completed Asian Session High / Low (ASH / ASL)**.
   - **Recent Swing Highs / Lows (SWH / SWL)**.

2. **Liquidity Sweep & Confirmation (`EL_Sweep`):**
   - Price wicks beyond a known liquidity pool by at least `InpSweepMinATR` and closes back inside.
   - Invalidation check: Ensures subsequent candles did not accept/close beyond the pool.
   - Tracks the highest high / lowest low across the entire sweep sequence for bulletproof Stop Loss placement.

3. **Market Structure Shift (`EL_Structure`):**
   - Confirms Change of Character (CHoCH) when a candle body closes beyond the opposite swing that preceded the sweep.

4. **Institutional Zones (`EL_Zones`):**
   - **Order Block (OB):** Identifies the origin candle at the sweep extreme before displacement.
   - **Fair Value Gap (FVG):** Detects 3-candle imbalance gaps and verifies mitigation status.

5. **Scoring Engine (`EL_Signal`):**
   - Minimum threshold: `InpMinScore` (default 65 / 100).
   - Sweep + CHoCH: 40 pts.
   - OB + FVG Confluence: +30 pts (or single zone: +20 pts).
   - Premium / Discount Dealing Range (below 50% for Buys, above 50% for Sells): +15 pts.
   - External Opposing Liquidity Target (>= `InpRRMin`): +10 pts.
   - Session Killzone alignment: +10 pts.

---

## 🛡 Engineering Improvements Implemented

1. **Anti-Repainting Swings:**
   - Swings scan strictly starts at `LR + 1` closed bars, completely isolating the open, forming bar 0.
2. **Calendar-Day Asia Range:**
   - Replaced flawed `time % 86400` logic with `MqlDateTime` calendar day checks. Guarantees accurate Asian session range extraction across all broker server time zones (UTC+2, UTC+3, UTC+0).
3. **Broker Expiration Adaptability:**
   - Detects `SYMBOL_EXPIRATION_MODE`. If `ORDER_TIME_SPECIFIED` is not supported by the broker, automatically falls back to `ORDER_TIME_GTC` without throwing error `10015`.
4. **Volume Step & Margin Protection:**
   - Dynamic lot size normalization according to `SYMBOL_VOLUME_STEP` digits.
   - Validates required margin via `OrderCalcMargin()` against 90% of free equity to prevent error `10019`.
5. **Chart Flickering & Memory Optimization:**
   - In `EL_Indicator`, replaced bulk `ObjectsDeleteAll` with `ObjectMove` and targeted updates.
6. **Break-Even Buffer:**
   - Added cost-neutral buffer on Break-Even trailing to protect against spread/commissions on short positions.

---

## 🚀 Recommended Parameters for XAUUSD (Gold)

| Parameter | Recommended Value | Notes |
| :--- | :---: | :--- |
| **Recommended Timeframe** | `M15` | Best balance of noise reduction and clean SMC setups. |
| `InpSweepMinATR` | `0.15 - 0.25` | Prevents tagging normal spread noise as sweeps. |
| `InpSLBufATR` | `0.25 - 0.35` | Protects against secondary retests/wicks on Gold. |
| `InpRRMin` | `2.0 - 3.0` | Minimum 1:2 or 1:3 reward to risk. |
| `InpMinScore` | `65` | Filters out low-confluence setups. |
| `InpRiskPct` | `0.5% - 1.0%` | Prop-firm compliant risk per trade. |
| `InpPartialR` | `1.5` | Recommended over 1.0R to let Gold breathe before securing BE. |
| `InpMaxSpreadPts` | `60` | 60 points = $0.60 on Gold. |

---

## 📦 Installation & Setup

1. Copy the `Include/EL` directory into your MT5 `MQL5/Include/EL/`.
2. Copy `Experts/EL_EA.mq5` into `MQL5/Experts/`.
3. Copy `Indicators/EL_Indicator.mq5` into `MQL5/Indicators/`.
4. Open MetaEditor and compile both `EL_EA.mq5` and `EL_Indicator.mq5`.
5. Attach `EL_Indicator` to the XAUUSD M15 chart.
6. To trade live, set `InpDryRun = false` and `InpAllowReal = true` on `EL_EA`.

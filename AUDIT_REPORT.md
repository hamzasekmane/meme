# Engineered Liquidity (EL) MQL5 — Technical Audit

**Scope:** source audit of the EA, indicator, and shared `Include/EL` engine, plus targeted hardening. The screenshot and displayed XAUUSD values are treated as evidence, not as proof of internal unrounded prices. No MT5 terminal, MetaEditor compiler, broker account, or historical tick dataset is available in this workspace.

## A. Executive result

The alert `SELL 3952.86 / SL 4170.84 / TP 3516.91` on `EL_Indicator (XAUUSD,D1)` was **not evidence of a market SELL**. The old signal builder placed the entry at the midpoint of an OB/FVG zone, and the EA submitted BuyLimit/SellLimit orders. It was an analytical retracement reference that could be treated by users as an immediate trade because the alert said only `SELL` and did not include timeframe, order type, validity, or execution status.

The 185.53 price difference from the screenshot's approximate 3767.33 is not, by itself, proof that a Sell Limit is invalid: the limit is on the retracement side. The defects were that the setup was computed on D1 without an execution hierarchy, its zone/sweep could be old, the last-price check used the forming bar rather than a live executable quote, and the EA could start a fresh pending-order lifetime for an old setup. As displayed, the values imply `(3952.86 - 3516.91) / (4170.84 - 3952.86) ≈ 1.99995R`; if those are the exact prices, a strict 2R rule should reject it. Because the alert rounds to two decimals, the original internal RR cannot be proven from the screenshot alone.

The shared implementation now treats chart-timeframe signals as **analytical plans** and sets `executionReady` only for a valid M15 Sell Limit/Buy Limit after closed-bar structural, MTF, price-grid, broker-stop, RR, and expiry checks. A D1/H4/H1 chart can show a reference but cannot produce an execution-ready signal.

## B. Findings and root causes

### Critical — chart timeframe was mistaken for the execution timeframe

- **Before:** `CELEngine::Init` used the attached `_Period`; `CELEngine::Update` passed that one timeframe's rates, swings, pools, sweeps, structure, zones, and signal through the whole pipeline. There was no D1→H4→H1→M15→M5 architecture or MTF consistency gate.
- **Impact:** a D1 bearish setup was scored and alerted as `SELL`; the EA could also be attached to D1 and treat it as an order candidate. A D1 bias did not imply an immediate M15 setup.
- **Fix:** `EL_MTF.mqh` calculates D1/H4/H1 structural bias independently from confirmed swings; M15 is the only execution timeframe; M5 must independently close through its own latest confirmed opposing swing after the M15 setup timestamp. The engine leaves other timeframe signals analytical-only. A mixed/missing HTF bias or M5 confirmation yields WAIT.
- **Exact areas:** `Include/EL/EL_Engine.mqh`, `CELEngine::Update`; new `Include/EL/EL_MTF.mqh`, `EL_StructuralBias`, `EL_HTFAligned`, `EL_M5Confirms`; `Experts/EL_EA.mq5`, `OnInit`/`OnTick`.

### Critical — high score and `valid` were treated as execution eligibility

- **Before:** `ELSignal` had only a `valid` bit and score. `EL_Indicator::Draw` alerted on `valid && score >= minScore`; `EL_EA::OnTick` used the same condition and attempted a limit order. No separate bias, displacement, entry, risk, or execution states existed.
- **Impact:** historical confluence could retain a high score without demonstrating current executable conditions.
- **Fix:** `ELSignal` now records state and stage flags (`LIQUIDITY_SWEPT`, `STRUCTURE_CONFIRMED`, `DISPLACEMENT_CONFIRMED`, `ZONE_IDENTIFIED`, `ENTRY_VALIDATED`, `RISK_VALIDATED`, `EXECUTION_READY`, `WAIT`, `INVALIDATED`, `EXPIRED`). Score remains a confluence measure. Both EA and indicator require the shared `executionReady` flag before any trade/ready alert.
- **Exact areas:** `Include/EL/EL_Types.mqh`, `ELSignal`; `Include/EL/EL_Signal.mqh`, `CELSig::Build`; `Include/EL/EL_Engine.mqh`, `CELEngine::Update`; EA and indicator output branches.

### High — stale signal/zone and price-reference handling

- **Before:** `CELSig::Build` compared entry to `r[0].close` (forming bar), and its decision was only refreshed once a new bar arrived. It did not compare a plan with current Bid/Ask. `EL_EA` calculated pending expiry from `now`, allowing an old sweep/zone to receive a fresh lifetime. `CELZones` could select the oldest opposing candle between sweep and break, did not reject an invalidated OB, and searched FVGs without constraining all three candles to the sweep/MSS interval; FVG mitigation included bar 0.
- **Impact:** live entry distance could be stale, a historical zone could be re-used, and an already-crossed limit could remain mislabeled as a candidate.
- **Fix:** closed-bar `r[1]` is used for setup and premium/discount checks; OB selection takes the nearest valid opposing candle preceding MSS and rejects closes through its structural boundary; FVG formation is constrained to after sweep and at/before MSS and mitigation scans closed bars only. Signal lifetime is anchored to its sweep and pending expiry to signal time, capped by sweep expiry. The engine clears the previous signal before every update, including data failures.
- **Exact areas:** `Include/EL/EL_Signal.mqh`, `CELSig::Reset/Build`; `Include/EL/EL_Zones.mqh`, `CELZones::Build`; `Include/EL/EL_Engine.mqh`, `CELEngine::Update`; `Experts/EL_EA.mq5`, pending expiry calculation; `Indicators/EL_Indicator.mq5`, `OnCalculate`.

### High — swing confirmation could leak past the sweep; sweep event could be reused

- **Before:** `CELStructure::Detect` selected an opposite swing older than the sweep by bar index, but did not require its right-hand confirmation bars to have completed before the sweep. Sweep invalidation checked later closes beyond the pool but did not retire an older sweep when a later wick re-swept the same level.
- **Impact:** a pivot confirmed using post-sweep bars could be treated as pre-sweep structure, and an old sweep might remain the event after a more recent excursion.
- **Fix:** structure requires the pivot to have completed its `swingLR` confirmation before the sweep. Pools carry an `available` timestamp, and later excursions through a pool supersede the older sweep event. Candidate signals use the newest still-valid sweep within the configured bar-age limit.
- **Exact areas:** `Include/EL/EL_Structure.mqh`, `CELStructure::Detect`; `Include/EL/EL_Sweep.mqh`, `CELSweep::Detect`; `Include/EL/EL_Types.mqh`, `ELPool`; `Include/EL/EL_Liquidity.mqh`, `CELLiquidity::Build/Add`.

### High — entry/order type, broker geometry, normalization, and expiry were conflated

- **Before:** the zone midpoint was simply called `entry`; price rounding in `PlaceLimit` used display digits, and validation covered only whether a limit was too close to Bid/Ask. Stop/target geometry and tick size were not validated there. If the broker did not support specified expiry, the code silently sent GTC.
- **Impact:** an analytical reference could be mistaken for a market price; off-grid prices and invalid SL/TP distances could reach order submission; an unsupported expiry could leave a stale order indefinitely.
- **Fix:** entry kinds explicitly distinguish analytical, market, limit, and stop orders; this system currently creates only Buy Limit/Sell Limit candidates. `EL_ValidateLimitPlan` maps prices to tick size, rounds structural SL outward, validates correct limit side against Ask/Bid, validates SL/TP direction and broker stop distance, and rechecks actual RR. `CELTrade::PlaceLimit` repeats quote/geometry/expiry checks at send time. Unsupported specified expiry rejects the order rather than falling back to GTC.
- **Exact areas:** new `Include/EL/EL_Validation.mqh`, `EL_NormalizeToTick`, `EL_ValidateLimitPlan`; `Include/EL/EL_Types.mqh`, `ENUM_EL_ENTRY_KIND`; `Include/EL/EL_Trade.mqh`, `CELTrade::PlaceLimit`.

### High — stop/target logic

- **Stop loss before:** `CELSig::Build` used the sweep extreme plus/minus `atr * slBufATR`; this is structurally sensible and is preserved. It did not validate the resulting plan against broker minimum stop distances/tick grid. No arbitrary stop-width reduction was found or introduced.
- **Fix:** the structural extreme and ATR buffer remain intact; stop prices round away from entry and plans violating broker minimum distances are rejected, not tightened.
- **Take profit before:** nearest opposite pool qualified mainly by RR; minor swing tags could qualify, targets already crossed relative to the current price could be selected, and a fixed-RR fallback could be labeled a target even when no external liquidity existed.
- **Fix:** only EQH/EQL, PDH/PDL, PWH/PWL, and completed Asia pools qualify; the target must remain beyond current closed price and meet RR. A target crossed since its availability is rejected. No synthetic fixed-RR fallback is used. External tags are preserved when duplicate pools are coalesced.
- **Exact areas:** `Include/EL/EL_Signal.mqh`, `EL_IsExternalLiquidity`, target selection; `Include/EL/EL_Liquidity.mqh`, `CELLiquidity::Add`; `Include/EL/EL_Validation.mqh`.

### Medium — displacement was absent as an independent test

- **Before:** a close beyond a swing was treated as CHoCH/MSS; no distinct displacement test existed.
- **Fix:** added configurable `InpMinDisplacementATR` (default `0.50`). The closed MSS candle body is measured against ATR from that same historical candle. Missing displacement blocks plan generation; this is an explicit conservative rule addition requested by the audit, not a hidden score tweak.
- **Exact areas:** `Include/EL/EL_Inputs.mqh`, `EL_Config.mqh`, `EL_Signal.mqh`, `CELEngine::Update`.

### Confirmed working / retained

- Sweep direction (high→SELL, low→BUY) and close-back-inside pattern were present.
- Sweep invalidation by subsequent acceptance closes was present and remains; later excursions now also supersede stale events.
- SL was already anchored to the sweep extreme with an ATR buffer. It remains so.
- ATR reads used shift 1 for the current setup; this remains for SL/pool normalization. MSS displacement uses ATR at the MSS candle.
- Position sizing used tick-value/tick-size loss estimation, volume-step flooring, and a margin check. This code was not rewritten; broker-specific runtime validation is still required.
- EA DRY-RUN and real-account safety guard remain.
- Indicator and EA use the same `CELEngine` calculation for the same symbol, timeframe, and input values.

## C. Implementation details and strategy-impact notes

- M15 execution, D1/H4/H1 alignment, M5 confirmation, `0.50 ATR` displacement, external-pool-only targets, strict RR, and no-GTC fallback are deliberate conservative eligibility changes. They can materially reduce signal/order frequency; they do not establish profitability.
- HTF bias is currently defined as two most recent confirmed swing highs **and** lows both rising (bullish) or both falling (bearish); mixed/insufficient structure is neutral and blocks execution. This definition is explicit and testable, but must be validated against the user's intended strategy rules.
- M15 owns the liquidity/sweep/OB/FVG setup. D1/H4/H1 supply separate swing-based bias; M5 supplies independent structure confirmation. HTF OB/FVG confluence is not currently calculated, by design, and is listed as a remaining limitation below rather than being implied.
- No arbitrary maximum dollar/ATR distance from current price was added. A valid limit must be on the correct side of live Bid/Ask, retain the same structural zone, and remain within its event/order expiry. Thus a far limit can still be valid if it is a fresh M15 retracement plan; D1 cannot be actionable.
- **Risk parameters were not changed:** `InpSLBufATR` remains `0.25`, `InpRRMin` remains `2.0`, `InpRiskPct` remains `0.5`, and `Include/EL/EL_Risk.mqh` sizing logic was not modified. Price defects are handled by rejecting invalid setups, not by narrowing stops or increasing risk.
- Strategy-policy deltas are explicit in inputs/docs: M15-only execution, HH/HL-or-LH/LL D1/H4/H1 alignment, M5 swing-break confirmation, and the new `InpMinDisplacementATR=0.50` filter. They are conservative eligibility rules from the requested audit, can reduce setup frequency, and require validation against the user's strategy specification; they are not represented as the original strategy's pre-existing rules.

## D. Validation performed

### Automated tests

`python3 -m unittest discover -s tests -v` runs **21 portable regression/contract tests**, including the 15 requested cases (far SELL/BUY, valid limits, invalid side, stale OB, invalidated sweep, no displacement/MSS, timeframe guard, wide structural SL preservation, TP direction, RR, indicator/EA readiness consistency, and new-bar reset). The XAUUSD-style fixture uses 0.01 price/tick increments and tests the screenshot values as exact two-decimal prices; with those exact displayed prices the target misses 2R by 0.01. The source reads actual `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_POINT`, stop level, and symbol quotes at runtime.

**Result:** 21 passed in Python after the latest source edits; this is not an MQL5 compile or MT5 runtime test.

### Static checks

- `git diff --check`: passed after the final source edits.
- MQL source-contract assertions are included in the Python tests.
- No `MetaEditor`/MQL5 compiler is installed in this workspace. **MQL5 compilation was not run and is not claimed.**
- No real broker specification is available from the source repo or screenshot. **Actual XAUUSD tick size, tick value, digits, volume step, stop/freeze levels, expiration mode, and live quote validation remain to be checked in the target MT5 terminal.**

## E. Modified files

- `Experts/EL_EA.mq5`
- `Indicators/EL_Indicator.mq5`
- `Include/EL/EL_Config.mqh`
- `Include/EL/EL_Engine.mqh`
- `Include/EL/EL_Inputs.mqh`
- `Include/EL/EL_Liquidity.mqh`
- `Include/EL/EL_Signal.mqh`
- `Include/EL/EL_Structure.mqh`
- `Include/EL/EL_Sweep.mqh`
- `Include/EL/EL_Trade.mqh`
- `Include/EL/EL_Types.mqh`
- `Include/EL/EL_Zones.mqh`
- New `Include/EL/EL_MTF.mqh`
- New `Include/EL/EL_Validation.mqh`
- New `tests/test_el_audit_contracts.py`
- `README.md`

## F. Remaining limitations / MT5 work required

1. Compile the EA and indicator in the target MetaEditor; resolve any compiler-version-specific diagnostics.
2. Run the Strategy Tester on the broker's exact XAUUSD symbol (including suffixes) and verify D1/H4/H1 history readiness, `CopyRates`/ATR warmup, timestamps, and closed-candle timing.
3. Verify live `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_POINT`, tick values, volume min/max/step, stop/freeze levels, allowed order type and `SYMBOL_EXPIRATION_SPECIFIED`. The new behavior intentionally skips brokers without specified pending expiry.
4. Confirm the user's intended HTF bias and displacement definitions. The chosen rules are conservative implementation defaults, not derived from a provided rulebook.
5. HTF liquidity pools/OB/FVG and formal H1 structure labels are not independently built. Current hierarchy intentionally uses D1/H4/H1 swing trend as bias, M15 as setup, M5 as confirmation; expand only if the strategy requires those additional confluences.
6. Run visual parity checks with indicator and EA on identical inputs, then tester/backtest and forward/demo tests. No profitability or runtime execution claim is made.

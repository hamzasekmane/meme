# Engineered Liquidity (EL) MQL5 — Technical Audit

**Scope:** source audit of the EA, indicator, and shared `Include/EL` engine, plus targeted hardening. The screenshot and displayed XAUUSD values are treated as evidence, not as proof of internal unrounded prices. No MT5 terminal, MetaEditor compiler, broker account, or historical tick dataset is available in this workspace.

## A. Executive result

The alert `SELL 3952.86 / SL 4170.84 / TP 3516.91` on `EL_Indicator (XAUUSD,D1)` was **not evidence of a market SELL**. The old signal builder placed the entry at the midpoint of an OB/FVG zone, and the EA submitted BuyLimit/SellLimit orders. It was an analytical retracement reference that could be treated by users as an immediate trade because the alert said only `SELL` and did not include timeframe, order type, validity, or execution status.

The 185.53 price difference from the screenshot's approximate 3767.33 is not, by itself, proof that a Sell Limit is invalid: the limit is on the retracement side. The defects were that the setup was computed on D1 without an execution hierarchy, its zone/sweep could be old, the last-price check used the forming bar rather than a live executable quote, and the EA could start a fresh pending-order lifetime for an old setup. As displayed, the values imply `(3952.86 - 3516.91) / (4170.84 - 3952.86) ≈ 1.99995R`; if those are the exact prices, a strict 2R rule should reject it. Because the alert rounds to two decimals, the original internal RR cannot be proven from the screenshot alone.

The shared implementation now treats chart-timeframe signals as **analytical plans** and sets `executionReady` only for a valid M15 Sell Limit/Buy Limit after closed-bar structural, MTF, price-grid, broker-stop, RR, and expiry checks. A D1/H4/H1 chart can show a reference but cannot produce an execution-ready signal.

## B. Findings and root causes

**Disposition:** the two Critical and listed High findings below have source-level fixes in the shared engine/EA/indicator; the missing independent displacement check is addressed as a documented Medium-priority eligibility-rule addition. The Medium residual is an expected distinction between a shared calculated plan and the EA's account/runtime order gates. These dispositions are based on source review and portable tests only; no MQL compilation or MT5 execution has been performed.

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

### Defect-to-source trace (exact functions and decision impact)

The ranges below identify the **current fixed code sections**. Each entry names the old defective function/path, the corrected section, the technical cause, and the trading impact.

| Priority / defect | Source file, function, relevant section | Technical explanation | Impact on trading decisions |
|---|---|---|---|
| **Critical — timeframe mixing / D1 promoted to execution** | `Include/EL/EL_Engine.mqh`, `CELEngine::Update`, lines 61–123; `Include/EL/EL_MTF.mqh`, `EL_StructuralBias`/`EL_HTFAligned`/`EL_M5Confirms`, lines 9–54 | Previously the attached chart timeframe powered all stages, with no D1/H4/H1/M15/M5 hierarchy. Now each HTF swing bias is scanned separately, only M15 can pass the execution branch, and M5 uses its own closed rates/swings. | A D1 plan cannot be submitted as a current trade. Missing/mixed context leaves a candidate in WAIT.
| **Critical — score/valid bit treated as executable** | `Include/EL/EL_Types.mqh`, `ELSignal`, lines 14–59; `Include/EL/EL_Signal.mqh`, `CELSig::Build`, lines 31–39 and 124–129; `Include/EL/EL_Engine.mqh`, `CELEngine::Update`, lines 110–124; `Experts/EL_EA.mq5`, `OnTick`, lines 67–78; `Indicators/EL_Indicator.mq5`, `Draw`, lines 113–145 | The old EA/indicator used `valid && score >= minScore` as the practical execution/alert gate. The shared signal now has explicit stage flags and `executionReady`; consumers require it for order submission/READY alerts, after common structural, quote/plan, MTF and freshness gates. `riskValidated` denotes plan geometry/RR validation; EA lot sizing, margin, exposure, session, spread and news checks remain account/runtime-specific downstream checks. | Historical confluence cannot override missing entry or setup validation. WAIT/reference plans are non-executable; a READY calculation still does not guarantee an EA order, which can be suppressed by downstream checks.
| **High — forming-bar / stale entry price** | `Include/EL/EL_Signal.mqh`, `CELSig::Build`, lines 77–94; `Include/EL/EL_Validation.mqh`, `EL_ValidateLimitPlan`, lines 35–73 | The old plan used `r[0].close` as its price check; bar 0 is forming and is not a stable executable quote. The fix uses `r[1].close` for closed-bar analysis, then normalizes and checks actual Bid/Ask for the limit side and stop distances. | Prevents an entry already crossed or wrongly sided from being called a valid retracement; avoids treating an analytical zone midpoint as a market fill.
| **High — OB/FVG can be stale or misidentified** | `Include/EL/EL_Zones.mqh`, `CELZones::Build`, lines 12–56 | The old OB scan could pick an old opposite candle and did not reject structural closes through it. The old FVG scan was not strictly bounded to sweep→MSS and used bar 0 in mitigation. Current code selects a nearer valid OB, checks invalidation, bounds the 3-candle gap, and mitigates using closed bars. | Prevents old/filled zones from supplying a new limit price and avoids repainting on the open candle.
| **High — stale cached signal / renewed pending expiry** | `Include/EL/EL_Engine.mqh`, `CELEngine::Update`, lines 51–82; `Include/EL/EL_Signal.mqh`, `CELSig::Build`, lines 41–51; `Experts/EL_EA.mq5`, `OnTick`, lines 60–78 and 97–105; `Indicators/EL_Indicator.mq5`, `OnCalculate`, lines 158–170; `Include/EL/EL_Trade.mqh`, `CELTrade::PlaceLimit`, lines 45–71 | Previously failed history refresh could leave the indicator's prior objects/signals visible, and pending lifetime was started from placement time instead of the setup timestamp. The fix resets signal state before data fetch, redraws after failed updates, anchors signal/order expiry to sweep/setup time and caps it by sweep expiry. | Prevents stale plans from remaining displayed/actionable or being renewed with a new pending-order TTL.
| **High — post-sweep swing confirmation / stale sweep reuse** | `Include/EL/EL_Structure.mqh`, `CELStructure::Detect`, lines 11–29; `Include/EL/EL_Sweep.mqh`, `CELSweep::Detect`, lines 12–75; `Include/EL/EL_Liquidity.mqh`, `CELLiquidity::Build/Add`, lines 18–95 | Before, an opposite pivot could use right-side confirmation candles occurring after the sweep, and a later excursion could leave the older sweep as the selected event. Current structure requires the pivot be confirmed before the sweep; pools track availability and later excursions supersede older sweep events. | Reduces look-ahead structure labels and prevents entries from relying on a consumed/replayed sweep.
| **High — synthetic/obsolete TP and RR acceptance** | `Include/EL/EL_Signal.mqh`, `EL_IsExternalLiquidity`, `EL_TargetUntouchedSinceAvailable`, `CELSig::Build`, lines 7–24 and 106–120 | The old target loop admitted minor swing pools, did not require the target remain beyond current price, and created fixed-RR TP when no pool qualified. Current selection requires an external pool, unconsumed since availability, correctly sided beyond current closed price, and minimum RR; otherwise there is no plan. | Avoids false external-liquidity targets, targets already taken, and apparently valid plans with an invented TP.
| **High — price grid / broker stop / expiry handling** | `Include/EL/EL_Validation.mqh`, `EL_ValidateLimitPlan`, lines 5–75; `Include/EL/EL_Trade.mqh`, `CELTrade::PlaceLimit`, lines 36–78 | The old order code rounded to digits and mostly checked only entry-vs-market proximity; unsupported expiration silently became GTC. Current code uses tick size, structural SL outward rounding, direction and stop-level checks, send-time revalidation, and rejects brokers lacking specified expiry. | Prevents invalid/off-grid pending orders and orders that can remain live past setup validity.
| **Medium — displacement was not an independent confirmation** | `Include/EL/EL_Engine.mqh`, `CELEngine::Update`, lines 61–73; `Include/EL/EL_Signal.mqh`, `CELSig::Build`, lines 53–62; `Include/EL/EL_Inputs.mqh`, `EL_Config.mqh` | Before, a close through a swing could count as MSS/CHoCH without a separately measured impulse body. The fix measures the closed break candle body against ATR sampled at that break candle and requires `InpMinDisplacementATR` (default 0.50); missing displacement returns without a valid plan. | Filters weak/low-momentum breaks that could otherwise create an entry plan; this is a conservative policy addition and may reduce signal frequency. The 0.50 threshold is not backtest-validated here.
| **Confirmed safe behavior — wide structural SL** | `Include/EL/EL_Signal.mqh`, `CELSig::Build`, lines 77–84; `Include/EL/EL_Validation.mqh`, lines 48–73; `Include/EL/EL_Risk.mqh`, `EL_LotsByRisk`, lines 5–24; `Experts/EL_EA.mq5`, `OnTick`, lines 87–92 | There is no automatic max-stop clamp. SL stays at sweep extreme ± configured ATR buffer, rounds outward, and full entry-to-SL distance drives lot sizing. If volume floors below the broker minimum, sizing returns zero and EA skips. | A wide valid structural stop can mean no trade; it does not silently tighten invalidation or exceed configured risk. A reproducible test covers this behavior; no separate distance cap was added.
| **Medium residual — indicator/EA can differ after shared signal calculation** | `Indicators/EL_Indicator.mq5`, `Draw`, lines 113–145; `Experts/EL_EA.mq5`, `OnTick`, lines 79–105 | Both consume the same `CELEngine` signal fields on identical symbol/timeframe/inputs. EA additionally checks exposure, current killzone, spread, news blackout, risk lot size and dry-run mode; indicator does not own the EA's positions or send-order outcome. | A visual READY plan is a valid calculated plan, not a guarantee an EA order was sent. EA-specific suppressions can still differ; verify logs and terminal order state.

### Confirmed working / retained (source/static/reference-test level only)

These components remain present and internally consistent by source review, static checks, and the named reference/source-contract tests. This is **not** a claim of MQL compilation, broker execution, or MT5 runtime confirmation.

- Sweep direction (high→SELL, low→BUY), wick-through/close-back-inside pattern, and subsequent-close invalidation: `Include/EL/EL_Sweep.mqh`, `CELSweep::Detect`, lines 6–75; invalidation/supersession fixture `test_07_invalidated_liquidity_sweep_is_not_reused`.
- MSS/CHoCH is a closed close beyond pre-sweep confirmed structure: `Include/EL/EL_Structure.mqh`, `CELStructure::Detect`, lines 11–29; missing-MSS fixture `test_09_missing_mss_blocks_signal_plan`.
- Structural SL stays anchored to sweep extreme ± ATR buffer: `Include/EL/EL_Signal.mqh`, `CELSig::Build`, lines 77–84; tick mapping preserves outward distance in `Include/EL/EL_Validation.mqh`, `EL_ValidateLimitPlan`, lines 48–52. Wide-stop/minimum-volume behavior is exercised by `test_11_wide_structural_stop_is_not_arbitrarily_clipped` and `test_excessive_sl_distance_is_preserved_and_minimum_lot_is_skipped`.
- ATR setup value uses the closed bar, and displacement uses ATR associated with the MSS candle: `Include/EL/EL_Engine.mqh`, `CELEngine::Update`, lines 55–73.
- Risk sizing uses tick-value/tick-size loss estimation, volume-step flooring, and a margin check: `Include/EL/EL_Risk.mqh`, `EL_LotsByRisk`, lines 5–24. The sizing implementation/parameters were not changed; broker-specific behavior remains unverified.
- EA DRY-RUN and real-account safety guard remain: `Experts/EL_EA.mq5`, `OnInit` and `OnTick`, lines 29–47 and 54–117.
- Indicator and EA consume the shared `CELEngine` calculation: `Include/EL/EL_Engine.mqh`, `CELEngine::Update`; execution-result divergence from EA-only downstream gates is disclosed above.

## C. Implementation details and strategy-impact notes

- M15 execution, D1/H4/H1 alignment, M5 confirmation, `0.50 ATR` displacement, external-pool-only targets, strict RR, and no-GTC fallback are deliberate conservative eligibility changes. They can materially reduce signal/order frequency; they do not establish profitability.
- HTF bias is currently defined as two most recent confirmed swing highs **and** lows both rising (bullish) or both falling (bearish); mixed/insufficient structure is neutral and blocks execution. This definition is explicit and testable, but must be validated against the user's intended strategy rules.
- M15 owns the liquidity/sweep/OB/FVG setup. D1/H4/H1 supply separate swing-based bias; M5 supplies independent structure confirmation. HTF OB/FVG confluence is not currently calculated, by design, and is listed as a remaining limitation below rather than being implied.
- No arbitrary maximum dollar/ATR distance from current price was added. A valid limit must be on the correct side of live Bid/Ask, retain the same structural zone, and remain within its event/order expiry. Thus a far limit can still be valid if it is a fresh M15 retracement plan; D1 cannot be actionable.
- **Risk parameters were not changed:** `InpSLBufATR` remains `0.25`, `InpRRMin` remains `2.0`, `InpRiskPct` remains `0.5`, and `Include/EL/EL_Risk.mqh` sizing logic was not modified. Price defects are handled by rejecting invalid setups, not by narrowing stops or increasing risk.
- Strategy-policy deltas are explicit in inputs/docs: M15-only execution, HH/HL-or-LH/LL D1/H4/H1 alignment, M5 swing-break confirmation, and the new `InpMinDisplacementATR=0.50` filter. They are conservative eligibility rules from the requested audit, can reduce setup frequency, and require validation against the user's strategy specification; they are not represented as the original strategy's pre-existing rules.

### Execution-related changes and their rationale

| Change and exact implementation area | Behavior/rationale | Trading-decision effect |
|---|---|---|
| **Analytical vs executable plan type:** `Include/EL/EL_Types.mqh`, `ELSignal`/`ENUM_EL_ENTRY_KIND`; `Include/EL/EL_Signal.mqh`, `CELSig::Build` lines 77–94; `Indicators/EL_Indicator.mq5`, `Draw` lines 113–145 | OB/FVG midpoint is represented as a retracement Buy Limit/Sell Limit, not a market execution price. Indicator distinguishes `ANALYTICAL REFERENCE - WAIT / NOT EXECUTABLE` from `BUY/SELL LIMIT (READY)`, and READY alerts include prices and expiry. | Prevents a reference on D1 or an unvalidated zone from being read as an immediate market order; no arbitrary maximum entry distance is added.
| **Execution timeframe and independent confirmations:** `Include/EL/EL_Engine.mqh`, `CELEngine::Update` lines 83–108; `Include/EL/EL_MTF.mqh`, `EL_StructuralBias`, `EL_HTFAligned`, `EL_M5Confirms` | Only M15 may enter the execution path; D1/H4/H1 swing biases must align, M5 must confirm after the setup timestamp, and minimum score is still required. | Blocks D1/H4/H1/M5 chart references and mixed or missing context from authorizing orders; expected to reduce frequency.
| **Closed-bar, MSS, displacement and zone gates:** `Include/EL/EL_Structure.mqh`, `CELStructure::Detect` lines 11–29; `Include/EL/EL_Signal.mqh`, `CELSig::Build` lines 41–65; `Include/EL/EL_Zones.mqh`, `CELZones::Build` lines 12–58 | MSS is a closed close through pre-sweep confirmed structure; displacement is separately measured on that closed candle; OB/FVG must belong to the sweep-to-MSS sequence and be valid/unmitigated. Open bar is excluded from the decision. | Weak breaks, absent MSS/displacement, stale/invalidated OBs, and filled or incorrectly sequenced FVGs cannot produce a plan.
| **Sweep/target freshness and expiry:** `Include/EL/EL_Liquidity.mqh`, `CELLiquidity::Build/Add`; `Include/EL/EL_Sweep.mqh`, `CELSweep::Detect`; `Include/EL/EL_Signal.mqh`, `EL_TargetUntouchedSinceAvailable`/`CELSig::Build`; `Experts/EL_EA.mq5`, `OnTick`; `Include/EL/EL_Trade.mqh`, `CELTrade::PlaceLimit` | Pools have availability timestamps; later excursions consume/supersede sweeps; target history is checked for prior consumption; setup and pending-order expiry derive from setup/sweep timestamps, and send rejects elapsed expiry. | Stops old events/targets being replayed and prevents a new order lifetime from reviving an expired setup.
| **Entry/SL/TP broker geometry:** `Include/EL/EL_Validation.mqh`, `EL_NormalizeToTick`, `EL_FloorToTick`, `EL_CeilToTick`, `EL_ValidateLimitPlan`; `Include/EL/EL_Trade.mqh`, `CELTrade::PlaceLimit` | Uses broker tick-size grid, correct pending side vs live Ask/Bid, outward structural-SL rounding, stop-distance and direction checks, and plan RR checks; order path revalidates at send time. | Invalid market-side entries, off-grid prices, wrong-side SL/TP, insufficient RR, or broker-invalid stop distances fail closed rather than being sent.
| **No GTC fallback:** `Include/EL/EL_Trade.mqh`, `CELTrade::PlaceLimit`, lines 60–71 | Specified expiry is required; unsupported broker expiration returns an error instead of silently submitting a GTC order. | Reduces risk of unattended stale pending orders; brokers without the required mode will have no order until policy/support is changed deliberately.
| **Risk sizing and wide stops:** `Include/EL/EL_Risk.mqh`, `EL_LotsByRisk`; `Experts/EL_EA.mq5`, `OnTick`, lines 87–92 | Risk percent/SL buffer and lot-sizing algorithm were not changed. Full structural stop distance sizes the position; zero/under-minimum size, insufficient margin, or other risk failure skips entry. | Wide stops may result in no trade; stop is not tightened to manufacture eligibility or conceal a sizing defect.
| **EA-only live-operational gates and DRY-RUN:** `Experts/EL_EA.mq5`, `OnTick`, lines 54–117; `Include/EL/EL_Trade.mqh`, `CELTrade::HasExposure/Manage/PlaceLimit` | EA still checks expiry, one exposure/one sweep, killzone, spread, news, lot size, and DRY-RUN before sending; position management remains disabled in DRY-RUN. | An indicator READY plan is a calculation result, not proof an order was placed. EA may correctly suppress it because account/session/market conditions differ.

## D. Validation performed

### Automated tests

`python3 -m unittest discover -s tests -v` runs **30 portable regression/calculation tests**: 22 scenario/regression contracts (including dedicated synthetic cases for the 10 requested scenarios and a contract check for the broker harness) plus 8 signal/entry/SL/TP reference-model calculation cases. The scenario cases combine deterministic fixture behavior with source-contract checks for far SELL/BUY entries, valid retracement limits, invalid market-side prices, stale OB, invalidated sweep, missing displacement/MSS and wrong timeframe. Other coverage includes wide/excessive structural SL behavior, minimum-volume skip, TP direction, RR after tick mapping, shared indicator/EA plan fields, and new-bar refresh. XAUUSD-style price fixtures use 0.01 increments and test the screenshot prices as exact two-decimal values; at those exact values the target is short of 2R by 0.01. The excessive-stop sizing fixture is illustrative only (0.01 tick size, hypothetical $1 tick value, 0.01 step/minimum lot), not an asserted broker specification. These deterministic Python reference cases are paired with source-contract checks but do not execute MQL bytecode. Runtime code reads the live symbol's `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_POINT`, stop level and quotes.

**Final executed-test results:** Python unit/regression/signal-calculation/entry-SL-TP tests: **30 passed, 0 failed** (22 scenario/regression contracts and 8 calculation tests); static source analysis: **passed**; whitespace/diff check: **passed**. No executed test failed. MQL5 compilation was **not run** because MetaEditor/Wine is absent; that is unavailable, not a failure or pass. The actual-broker MQL harness and all MT5 runtime checks are also **not run**, not failed.

### Static checks

- `python3 tests/static_mql_analysis.py`: passed for 18 MQL source files (internal include resolution, include guards, balanced delimiters, ELParams initialization, and key execution contracts).
- `git diff --check`: passed.
- No `MetaEditor`/MQL5 compiler or Wine is installed in this workspace. **MQL5 compilation could not be run and is not claimed.**
- No live broker specification is available from the source repo or screenshot. `tests/EL_XAUUSD_BrokerAudit.mq5` is a no-order Script harness that, when run in the target MT5 terminal, prints the exact selected symbol's digits, point, tick size/value, volume limits, stop/freeze levels, order/expiration modes and live quote, then exercises production price/lot helpers. It defaults to `XAUUSD` and supports broker suffixes through its input. **The harness was not run here; actual ICMarkets demo contract values and quote validation remain unverified.**

## E. Final change inventory

### Files changed for this completion on active branch `arena/1d5c578e-meme`

- `AUDIT_REPORT.md` — severity/source trace, confirmed components, execution-change rationale, test results, limitations, and final inventory.
- `tests/EL_XAUUSD_BrokerAudit.mq5` — no-order broker-specific MT5 harness; source-contract checked, not compiled or run in MT5.
- `tests/static_mql_analysis.py` — static analyzer now includes MQL scripts under `tests/`.
- `tests/test_el_audit_contracts.py` — adds regression contract coverage for the broker harness; includes reproducible setup/entry scenario tests.
- `tests/test_el_signal_calculations.py` — calculation and entry/SL/TP consistency reference cases, including wide structural SL/minimum-volume handling.

### Cumulative implementation files covered by this audit

The following implementation files were changed in the earlier audit hardening already present in the branch base; they are listed to make the final report inventory complete, not as edits made in this completion turn:

- `.gitignore`, `README.md`
- `Experts/EL_EA.mq5`, `Indicators/EL_Indicator.mq5`
- `Include/EL/EL_Config.mqh`, `Include/EL/EL_Engine.mqh`, `Include/EL/EL_Inputs.mqh`, `Include/EL/EL_Liquidity.mqh`, `Include/EL/EL_Signal.mqh`, `Include/EL/EL_Structure.mqh`, `Include/EL/EL_Sweep.mqh`, `Include/EL/EL_Trade.mqh`, `Include/EL/EL_Types.mqh`, `Include/EL/EL_Zones.mqh`
- New `Include/EL/EL_MTF.mqh`, `Include/EL/EL_Validation.mqh`
- New `tests/test_el_audit_contracts.py`, `tests/test_el_signal_calculations.py`, `tests/static_mql_analysis.py`

## F. Remaining limitations / MT5 work required

1. Compile the EA, indicator, and `tests/EL_XAUUSD_BrokerAudit.mq5` in the target MetaEditor; resolve compiler-version-specific diagnostics. This workspace has no MetaEditor/Wine.
2. Copy the broker-audit Script into `MQL5/Scripts/` while installing `Include/EL`; run it in the target terminal with the exact ICMarkets symbol name (including suffix if present). It sends no orders, prints live contract specs, and returns per-check PASS/FAIL. Attach its Journal output to complete broker-specific validation; it has not been run here.
3. Run the Strategy Tester on that exact XAUUSD symbol and verify D1/H4/H1 history readiness, `CopyRates`/ATR warmup, timestamps, and closed-candle timing.
4. Verify live `SYMBOL_TRADE_TICK_SIZE`, `SYMBOL_POINT`, tick values, volume min/max/step, stop/freeze levels, allowed order type and `SYMBOL_EXPIRATION_SPECIFIED`. The new behavior intentionally skips brokers without specified pending expiry.
5. Confirm the user's intended HTF bias and displacement definitions. The chosen rules are conservative implementation defaults, not derived from a provided rulebook.
6. HTF liquidity pools/OB/FVG and formal H1 structure labels are not independently built. Current hierarchy intentionally uses D1/H4/H1 swing trend as bias, M15 as setup, M5 as confirmation; expand only if the strategy requires those additional confluences.
7. Run visual parity checks with indicator and EA on identical inputs, then tester/backtest and forward/demo tests. No profitability or runtime execution claim is made.

## G. Final report

- **Bugs fixed at source level:** chart-period/D1 execution ambiguity; score/`valid` being treated as sufficient for an order; stale/forming-bar price checks and cached signals; renewing pending expiry for old setups; post-sweep swing look-ahead and stale sweep reuse; stale/invalidated OB/FVG acceptance; missing independent displacement gate; weak/synthetic/consumed TP and unverified RR; display-digit-only rounding and incomplete broker-side entry/SL/TP checks; and silent GTC fallback. Fix locations and trading-decision impacts are in the trace table above. Risk parameters and structural-stop logic were preserved.
- **Execution-policy changes explained:** M15-only execution with D1/H4/H1 alignment and M5 confirmation; `0.50 ATR` displacement; external-liquidity targets with strict RR; tick-grid and broker-stop validation; setup-anchored expiry with no GTC fallback; plus existing EA session/spread/news/exposure/risk/DRY-RUN gates. These conservative eligibility rules can reduce trade frequency and have not been proven profitable.
- **Tests:** 30 Python unit/regression/reference-calculation tests passed; static analysis passed for 18 MQL sources; `git diff --check` passed. **Failures: 0 among tests actually run.** MQL compiler and runtime tests were not run and are not counted as passing or failing.
- **Modified files:** current completion-turn paths are listed under E (five files); the cumulative audit implementation paths already in the branch base are listed separately there.
- **Outstanding:** MQL compilation, live broker-spec harness output, Strategy Tester, EA/indicator visual parity, and forward/demo validation remain required as detailed in F. No runtime, live trading, or profitability validation is claimed.

#ifndef EL_CONFIG_MQH
#define EL_CONFIG_MQH
// All tunables used by the shared engine (filled from inputs by EL_Inputs.mqh).
struct ELParams
{
   int    swingLR;       // bars each side for a swing point
   int    lookback;      // bars scanned
   int    atrPeriod;
   double eqTolATR;      // equal highs/lows tolerance (x ATR)
   int    asiaStart;     // server hour
   int    asiaEnd;
   double sweepMinATR;   // min wick beyond the pool (x ATR)
   int    sweepMaxAge;   // max bars since sweep
   double slBufATR;      // SL buffer beyond sweep extreme (x ATR)
   double rrMin;         // min reward:risk
   int    minScore;      // 0..100
   bool   useKillzone;
   int    kz1Start, kz1End, kz2Start, kz2End; // server hours
   int    maxSpreadPts;
   string newsList;      // "2026.11.19 15:30;2026.11.20 16:00"
   int    newsMin;       // blackout +/- minutes
};
#endif

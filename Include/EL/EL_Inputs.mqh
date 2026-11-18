#ifndef EL_INPUTS_MQH
#define EL_INPUTS_MQH
#include <EL/EL_Config.mqh>

input group "=== Swings & Liquidity ==="
input int    InpSwingLR      = 3;     // Bars on each side for swing fractal
input int    InpLookback     = 300;   // Bars scanned
input int    InpATRPeriod    = 14;    // ATR period for normalization
input double InpEqTolATR     = 0.15;  // Equal highs/lows tolerance (x ATR)
input int    InpAsiaStart    = 0;     // Asia session start (server hour)
input int    InpAsiaEnd      = 7;     // Asia session end (server hour)

input group "=== Sweep / Structure ==="
input double InpSweepMinATR  = 0.15;  // Min wick beyond pool (x ATR, recommended 0.15-0.30 for Gold)
input double InpMinDisplacementATR = 0.50; // Explicit new eligibility rule; changes signal frequency, not risk sizing
input int    InpSweepMaxAge  = 25;    // Max bars since sweep

input group "=== Entry / Score ==="
input double InpSLBufATR     = 0.25;  // SL buffer beyond sweep extreme (x ATR, recommended >=0.25 for Gold)
input double InpRRMin        = 2.0;   // Minimum Reward:Risk ratio
input int    InpMinScore     = 65;    // Minimum score to qualify trade (0..100)

input group "=== Filters (server time) ==="
input bool   InpUseKillzone  = true;  // Filter trades by session Killzones
input int    InpKZ1Start     = 7;     // London start (server hour)
input int    InpKZ1End       = 11;    // London end (server hour)
input int    InpKZ2Start     = 12;    // New York start (server hour)
input int    InpKZ2End       = 17;    // New York end (server hour)
input int    InpMaxSpreadPts = 60;    // Max allowed spread in points (60 pts = $0.60 on Gold)
input string InpNews         = "";    // News blackout list: "YYYY.MM.DD HH:MM;..."
input int    InpNewsMin      = 30;    // Blackout +/- minutes around news

ELParams EL_BuildParams()
{
   ELParams p;
   p.swingLR      = InpSwingLR;
   p.lookback     = InpLookback;
   p.atrPeriod    = InpATRPeriod;
   p.eqTolATR     = InpEqTolATR;
   p.asiaStart    = InpAsiaStart;
   p.asiaEnd      = InpAsiaEnd;
   p.sweepMinATR  = InpSweepMinATR;
   p.minDisplacementATR = InpMinDisplacementATR;
   p.sweepMaxAge  = InpSweepMaxAge;
   p.slBufATR     = InpSLBufATR;
   p.rrMin        = InpRRMin;
   p.minScore     = InpMinScore;
   p.useKillzone  = InpUseKillzone;
   p.kz1Start     = InpKZ1Start;
   p.kz1End       = InpKZ1End;
   p.kz2Start     = InpKZ2Start;
   p.kz2End       = InpKZ2End;
   p.maxSpreadPts = InpMaxSpreadPts;
   p.newsList     = InpNews;
   p.newsMin      = InpNewsMin;
   return p;
}
#endif

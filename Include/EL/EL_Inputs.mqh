#ifndef EL_INPUTS_MQH
#define EL_INPUTS_MQH
#include <EL/EL_Config.mqh>

input group "=== Swings & Liquidity ==="
input int    InpSwingLR      = 3;
input int    InpLookback     = 300;
input int    InpATRPeriod    = 14;
input double InpEqTolATR     = 0.15;
input int    InpAsiaStart    = 0;     // server hour
input int    InpAsiaEnd      = 7;

input group "=== Sweep / Structure ==="
input double InpSweepMinATR  = 0.10;
input int    InpSweepMaxAge  = 25;

input group "=== Entry / Score ==="
input double InpSLBufATR     = 0.20;
input double InpRRMin        = 2.0;
input int    InpMinScore     = 65;

input group "=== Filters (server time) ==="
input bool   InpUseKillzone  = true;
input int    InpKZ1Start     = 7;     // London
input int    InpKZ1End       = 11;
input int    InpKZ2Start     = 12;    // New York
input int    InpKZ2End       = 17;
input int    InpMaxSpreadPts = 60;
input string InpNews         = "";    // "2026.11.19 15:30;2026.11.20 16:00"
input int    InpNewsMin      = 30;

ELParams EL_BuildParams()
{
   ELParams p;
   p.swingLR=InpSwingLR; p.lookback=InpLookback; p.atrPeriod=InpATRPeriod; p.eqTolATR=InpEqTolATR;
   p.asiaStart=InpAsiaStart; p.asiaEnd=InpAsiaEnd;
   p.sweepMinATR=InpSweepMinATR; p.sweepMaxAge=InpSweepMaxAge;
   p.slBufATR=InpSLBufATR; p.rrMin=InpRRMin; p.minScore=InpMinScore;
   p.useKillzone=InpUseKillzone; p.kz1Start=InpKZ1Start; p.kz1End=InpKZ1End; p.kz2Start=InpKZ2Start; p.kz2End=InpKZ2End;
   p.maxSpreadPts=InpMaxSpreadPts; p.newsList=InpNews; p.newsMin=InpNewsMin;
   return p;
}
#endif

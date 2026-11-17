//+------------------------------------------------------------------+
//| EL_EA.mq5 - Engineered Liquidity EA (XAUUSD) - personal use      |
//| Starts in DRY-RUN mode (prints signals, no orders).              |
//+------------------------------------------------------------------+
#property copyright "Personal use"
#property version   "1.00"

#include <EL/EL_Inputs.mqh>
#include <EL/EL_Engine.mqh>
#include <EL/EL_Risk.mqh>
#include <EL/EL_Trade.mqh>

input group "=== Execution ==="
input bool   InpDryRun       = true;     // true = log only
input bool   InpAllowReal    = false;    // must be true to run on a real account
input long   InpMagic        = 20261117;
input double InpRiskPct      = 0.5;      // % of equity per trade
input int    InpDeviation    = 30;
input int    InpExpiryBars   = 12;       // pending order lifetime (bars)

input group "=== Trade management ==="
input double InpPartialR     = 1.0;      // partial close at N x R
input double InpPartialPct   = 50.0;     // % closed

CELEngine eng;
CELTrade  trd;
datetime  lastBar=0, lastSweep=0;

int OnInit()
{
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL && !InpAllowReal)
   { Print("EL: real account blocked (set InpAllowReal=true to allow)."); return INIT_FAILED; }
   if(StringFind(_Symbol,"XAU")<0 && StringFind(_Symbol,"GOLD")<0)
      Print("EL: warning - symbol is not gold, defaults are tuned for XAUUSD.");
   if(!eng.Init(_Symbol,(ENUM_TIMEFRAMES)_Period,EL_BuildParams())) return INIT_FAILED;
   trd.Init(InpMagic,InpDeviation);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason){ eng.Deinit(); }

void OnTick()
{
   if(!InpDryRun) trd.Manage(_Symbol,InpPartialR,InpPartialPct);

   datetime bt=iTime(_Symbol,_Period,0);
   if(bt==lastBar) return;
   lastBar=bt;

   if(!eng.Update()) return;
   ELSignal s=eng.sig;
   if(!s.valid || s.score<eng.p.minScore) return;
   if(s.sweepTime==lastSweep) return;                       // one trade per sweep
   if(trd.HasExposure(_Symbol)) return;

   datetime now=TimeCurrent();
   if(!EL_InKillzone(now,eng.p))                 return;
   if(!EL_SpreadOk(_Symbol,eng.p.maxSpreadPts))  return;
   if(EL_NewsBlocked(now,eng.p))                 return;

   double lots=EL_LotsByRisk(_Symbol,InpRiskPct,s.entry,s.sl);
   if(lots<=0){ Print("EL: lot size is 0 (risk too small / SL too wide)."); return; }

   PrintFormat("EL: %s score=%d entry=%.2f sl=%.2f tp=%.2f lots=%.2f [%s]",
               s.dir==EL_BUY?"BUY":"SELL",s.score,s.entry,s.sl,s.tp,lots,s.reason);

   if(!InpDryRun)
      trd.PlaceLimit(_Symbol,s,lots,now+PeriodSeconds()*InpExpiryBars);
   lastSweep=s.sweepTime;
}

#ifndef EL_SIGNAL_MQH
#define EL_SIGNAL_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>
#include <EL/EL_Filters.mqh>

bool EL_IsExternalLiquidity(const string tag)
{
   return tag=="EQH" || tag=="EQL" || tag=="PDH" || tag=="PDL" ||
          tag=="PWH" || tag=="PWL" || tag=="ASH" || tag=="ASL";
}

bool EL_TargetUntouchedSinceAvailable(string sym,ENUM_TIMEFRAMES tf,const ELPool &pool)
{
   MqlRates history[]; ArraySetAsSeries(history,true);
   int count=CopyRates(sym,tf,pool.available,TimeCurrent(),history);
   if(count<1) return false; // fail closed when the target history cannot be verified
   for(int j=1;j<count;j++) // ignore the forming bar; only closed candles can consume a target
   {
      if(history[j].time<pool.available) continue;
      if(pool.isHigh && history[j].high>=pool.price) return false;
      if(!pool.isHigh && history[j].low<=pool.price) return false;
   }
   return true;
}

// A valid plan is still analytical until all execution gates in CELEngine pass.
class CELSig
{
public:
   void Reset(ELSignal &s)
   {
      s.valid=false; s.dir=EL_NONE; s.entry=0; s.sl=0; s.tp=0; s.score=0;
      s.t=0; s.sweepTime=0; s.expiresAt=0; s.entryKind=EL_ENTRY_ANALYTICAL;
      s.state=EL_STATE_WAIT; s.biasConfirmed=false; s.liquiditySwept=false;
      s.structureConfirmed=false; s.displacementConfirmed=false; s.zoneIdentified=false;
      s.entryValidated=false; s.riskValidated=false; s.executionReady=false;
      s.invalidated=false; s.expired=false; s.reason="WAIT";
   }

   void Build(string sym,ENUM_TIMEFRAMES tf,const MqlRates &r[],const ELSweep &sw,const ELBreak &bk,const ELZone &ob,const ELZone &fvg,
              const ELPool &pools[],double atr,double breakAtr,const ELParams &p,int tfSeconds,ELSignal &s)
   {
      Reset(s);
      if(ArraySize(r)<3 || !sw.found) return;
      s.liquiditySwept=true;
      s.state=EL_LIQUIDITY_SWEPT;
      s.dir=sw.dir;
      s.sweepTime=r[sw.bar].time;
      s.t=r[1].time;
      s.expiresAt=s.sweepTime+(datetime)(tfSeconds*p.sweepMaxAge);

      if(!bk.found) return;
      s.structureConfirmed=true;
      s.state=EL_STRUCTURE_CONFIRMED;

      // A structural close alone is not displacement. Require a completed MSS candle
      // with a body at least InpMinDisplacementATR * the prior closed-bar ATR.
      double body=MathAbs(r[bk.bar].close-r[bk.bar].open);
      if(breakAtr<=0 || p.minDisplacementATR<0 || body<breakAtr*p.minDisplacementATR) return;
      s.displacementConfirmed=true;
      s.state=EL_DISPLACEMENT_CONFIRMED;

      if(!ob.valid && !fvg.valid) return;
      s.zoneIdentified=true;
      s.state=EL_ZONE_IDENTIFIED;

      int dir=sw.dir;
      double zt=0,zb=0;
      int sc=40; // sweep + confirmed structure
      string why="Sweep+MSS+Displacement";
      if(ob.valid && fvg.valid && MathMin(ob.top,fvg.top)>MathMax(ob.bottom,fvg.bottom))
      { zt=MathMin(ob.top,fvg.top); zb=MathMax(ob.bottom,fvg.bottom); sc+=30; why+="+OB&FVG"; }
      else if(fvg.valid){ zt=fvg.top; zb=fvg.bottom; sc+=20; why+="+FVG"; }
      else { zt=ob.top; zb=ob.bottom; sc+=20; why+="+OB"; }

      // This is a retracement limit reference, never a market execution price.
      double entry=(zt+zb)*0.5;
      double buf=atr*p.slBufATR;
      double sl=(dir==EL_BUY)? sw.extreme-buf : sw.extreme+buf;
      double risk=(dir==EL_BUY)? entry-sl : sl-entry;
      if(risk<=0) return;
      if(dir==EL_BUY && entry<=sl) return;
      if(dir==EL_SELL && entry>=sl) return;

      // Only closed market data participates in validation and dealing-range calculations.
      double px=r[1].close;
      if(dir==EL_BUY && (px<=entry || px<=sl))
      { s.invalidated=true; s.state=EL_INVALIDATED; s.reason="INVALIDATED: BUY retracement entry was reached/passed"; return; }
      if(dir==EL_SELL && (px>=entry || px>=sl))
      { s.invalidated=true; s.state=EL_INVALIDATED; s.reason="INVALIDATED: SELL retracement entry was reached/passed"; return; }
      s.entryValidated=true;
      s.entryKind=(dir==EL_BUY)?EL_ENTRY_BUY_LIMIT:EL_ENTRY_SELL_LIMIT;
      s.state=EL_ENTRY_VALIDATED;

      double ext=sw.extreme,opp=sw.extreme;
      for(int j=1;j<=sw.bar && j<ArraySize(r);j++)
      {
         if(dir==EL_BUY) opp=MathMax(opp,r[j].high);
         else            opp=MathMin(opp,r[j].low);
      }
      double eq=(ext+opp)*0.5;
      if((dir==EL_BUY && entry<=eq) || (dir==EL_SELL && entry>=eq))
      { sc+=15; why+="+P/D"; }

      // Target only a qualifying external pool beyond both the entry RR threshold and
      // the current closed price. No fixed-R fallback masquerades as external liquidity.
      double tp=0;
      for(int i=0;i<ArraySize(pools);i++)
      {
         if(!EL_IsExternalLiquidity(pools[i].tag) || !EL_TargetUntouchedSinceAvailable(sym,tf,pools[i])) continue;
         if(dir==EL_BUY && pools[i].isHigh && pools[i].price>entry+risk*p.rrMin && pools[i].price>px)
         { if(tp==0 || pools[i].price<tp) tp=pools[i].price; }
         if(dir==EL_SELL && !pools[i].isHigh && pools[i].price<entry-risk*p.rrMin && pools[i].price<px)
         { if(tp==0 || pools[i].price>tp) tp=pools[i].price; }
      }
      if(tp<=0) return;
      double rr=(dir==EL_BUY)?(tp-entry)/risk:(entry-tp)/risk;
      if(rr+1e-8<p.rrMin) return;
      sc+=10; why+="+ExternalLiqTarget";

      if(EL_InKillzone(s.t,p)){ sc+=10; why+="+KZ"; }

      s.valid=true;
      s.entry=entry; s.sl=sl; s.tp=tp;
      s.score=MathMin(sc,100);
      s.reason=why;
      s.riskValidated=true;
      s.state=EL_RISK_VALIDATED;
   }
};
#endif

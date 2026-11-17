#ifndef EL_SIGNAL_MQH
#define EL_SIGNAL_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>
#include <EL/EL_Filters.mqh>

// Combines sweep + CHoCH + zone into a scored trade plan (limit entry at zone midpoint).
class CELSig
{
public:
   void Build(const MqlRates &r[],const ELSweep &sw,const ELBreak &bk,const ELZone &ob,const ELZone &fvg,
              const ELPool &pools[],double atr,const ELParams &p,ELSignal &s)
   {
      s.valid=false; s.score=0; s.reason=""; s.dir=EL_NONE; s.entry=0; s.sl=0; s.tp=0;
      if(!sw.found || !bk.found) return;
      if(!ob.valid && !fvg.valid) return;
      int dir=sw.dir;

      double zt=0, zb=0; int sc=40; // sweep 20 + CHoCH 20
      string why="Sweep+CHoCH";
      if(ob.valid && fvg.valid && MathMin(ob.top,fvg.top)>MathMax(ob.bottom,fvg.bottom))
      { zt=MathMin(ob.top,fvg.top); zb=MathMax(ob.bottom,fvg.bottom); sc+=30; why+="+OB&FVG"; }
      else if(fvg.valid){ zt=fvg.top; zb=fvg.bottom; sc+=20; why+="+FVG"; }
      else { zt=ob.top; zb=ob.bottom; sc+=20; why+="+OB"; }

      double entry=(zt+zb)/2.0;
      double buf=atr*p.slBufATR;
      double sl=(dir==EL_BUY)? sw.extreme-buf : sw.extreme+buf;
      double risk=MathAbs(entry-sl);
      if(risk<=0) return;
      if(dir==EL_BUY && entry<=sl) return;
      if(dir==EL_SELL && entry>=sl) return;

      // Price must still be on the "approach" side of the entry and not past the stop
      double px=r[0].close;
      if(dir==EL_BUY  && (px<=entry || px<=sl)) return;
      if(dir==EL_SELL && (px>=entry || px>=sl)) return;

      // Premium / Discount of the dealing range (sweep extreme -> opposite extreme since sweep)
      double ext=sw.extreme, opp=sw.extreme;
      for(int j=0;j<=sw.bar;j++)
      {
         if(dir==EL_BUY)  opp=MathMax(opp,r[j].high);
         else             opp=MathMin(opp,r[j].low);
      }
      double eq=(ext+opp)/2.0;
      if((dir==EL_BUY && entry<=eq) || (dir==EL_SELL && entry>=eq)){ sc+=15; why+="+P/D"; }

      // Target: nearest opposite pool giving at least rrMin, else fixed RR
      double tp=0; bool poolTp=false;
      for(int i=0;i<ArraySize(pools);i++)
      {
         if(dir==EL_BUY && pools[i].isHigh && pools[i].price>entry+risk*p.rrMin)
         { if(tp==0 || pools[i].price<tp) tp=pools[i].price; }
         if(dir==EL_SELL && !pools[i].isHigh && pools[i].price<entry-risk*p.rrMin)
         { if(tp==0 || pools[i].price>tp) tp=pools[i].price; }
      }
      if(tp==0) tp=(dir==EL_BUY)? entry+risk*p.rrMin : entry-risk*p.rrMin;
      else { poolTp=true; sc+=10; why+="+LiqTarget"; }

      if(EL_InKillzone(r[0].time,p)){ sc+=10; why+="+KZ"; }

      s.valid=true; s.dir=dir; s.entry=entry; s.sl=sl; s.tp=tp;
      s.score=MathMin(sc,100); s.t=r[0].time; s.sweepTime=r[sw.bar].time; s.reason=why;
   }
};
#endif

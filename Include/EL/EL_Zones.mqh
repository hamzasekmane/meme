#ifndef EL_ZONES_MQH
#define EL_ZONES_MQH
#include <EL/EL_Types.mqh>

// OB/FVG candidates must belong to the sweep-to-MSS sequence and remain unmitigated.
class CELZones
{
public:
   ELZone ob;
   ELZone fvg;

   void Build(const MqlRates &r[],int total,const ELSweep &sw,const ELBreak &bk)
   {
      ob.valid=false;
      fvg.valid=false;
      if(!sw.found || !bk.found || total<4 || bk.bar<1 || sw.bar<=bk.bar) return;

      // The OB is the nearest opposing candle immediately preceding the MSS impulse,
      // not the oldest opposite candle found near the sweep.
      for(int i=bk.bar+1;i<=sw.bar && i<total;i++)
      {
         bool bull=r[i].close>r[i].open;
         bool bear=r[i].close<r[i].open;
         if(!((sw.dir==EL_SELL && bull)||(sw.dir==EL_BUY && bear))) continue;

         bool invalidated=false;
         for(int j=1;j<i;j++) // closed candles strictly newer than the candidate OB
         {
            if(sw.dir==EL_SELL && r[j].close>r[i].high) { invalidated=true; break; }
            if(sw.dir==EL_BUY  && r[j].close<r[i].low)  { invalidated=true; break; }
         }
         if(invalidated) continue;
         ob.valid=true; ob.top=r[i].high; ob.bottom=r[i].low;
         ob.t=r[i].time; ob.bar=i; ob.kind=0;
         break;
      }

      // Require all three FVG candles to be after the sweep and at/before the MSS.
      // Search newest first. Mitigation checks use closed bars only (never bar 0).
      for(int i=MathMax(1,bk.bar);i+2<sw.bar && i+2<total;i++)
      {
         if(sw.dir==EL_SELL && r[i+2].low>r[i].high)
         {
            double top=r[i+2].low,bot=r[i].high;
            bool filled=false;
            for(int j=1;j<i;j++) if(r[j].high>=top) { filled=true; break; }
            if(!filled && top>bot)
            { fvg.valid=true; fvg.top=top; fvg.bottom=bot; fvg.t=r[i+1].time; fvg.bar=i+1; fvg.kind=1; break; }
         }
         if(sw.dir==EL_BUY && r[i].low>r[i+2].high)
         {
            double top=r[i].low,bot=r[i+2].high;
            bool filled=false;
            for(int j=1;j<i;j++) if(r[j].low<=bot) { filled=true; break; }
            if(!filled && top>bot)
            { fvg.valid=true; fvg.top=top; fvg.bottom=bot; fvg.t=r[i+1].time; fvg.bar=i+1; fvg.kind=1; break; }
         }
      }
   }
};
#endif

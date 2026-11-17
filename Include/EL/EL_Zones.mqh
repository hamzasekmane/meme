#ifndef EL_ZONES_MQH
#define EL_ZONES_MQH
#include <EL/EL_Types.mqh>

// Entry zones: Order Block and unfilled Fair Value Gap formed between sweep and now.
class CELZones
{
public:
   ELZone ob;
   ELZone fvg;

   void Build(const MqlRates &r[],int total,const ELSweep &sw,const ELBreak &bk)
   {
      ob.valid=false; fvg.valid=false;
      if(!sw.found || !bk.found) return;
      int dir=sw.dir;

      // Order block: last opposite candle between the break and the sweep
      for(int i=bk.bar+1;i<=sw.bar && i<total;i++)
      {
         bool bull=r[i].close>r[i].open, bear=r[i].close<r[i].open;
         if((dir==EL_SELL && bull) || (dir==EL_BUY && bear))
         { ob.valid=true; ob.top=r[i].high; ob.bottom=r[i].low; ob.t=r[i].time; ob.bar=i; ob.kind=0; break; }
      }

      // FVG: most recent unfilled 3-candle gap
      for(int i=1;i<=sw.bar && i+2<total;i++)
      {
         if(dir==EL_SELL && r[i+2].low>r[i].high)
         {
            double top=r[i+2].low, bot=r[i].high; bool filled=false;
            for(int j=0;j<i;j++) if(r[j].high>=top){ filled=true; break; }
            if(!filled){ fvg.valid=true; fvg.top=top; fvg.bottom=bot; fvg.t=r[i+1].time; fvg.bar=i+1; fvg.kind=1; break; }
         }
         if(dir==EL_BUY && r[i+2].high<r[i].low)
         {
            double top=r[i].low, bot=r[i+2].high; bool filled=false;
            for(int j=0;j<i;j++) if(r[j].low<=bot){ filled=true; break; }
            if(!filled){ fvg.valid=true; fvg.top=top; fvg.bottom=bot; fvg.t=r[i+1].time; fvg.bar=i+1; fvg.kind=1; break; }
         }
      }
   }
};
#endif

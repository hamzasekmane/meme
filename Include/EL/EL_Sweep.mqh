#ifndef EL_SWEEP_MQH
#define EL_SWEEP_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>

// Liquidity sweep: wick beyond a pool, close back inside. Sweep of highs => SELL setup, of lows => BUY setup.
class CELSweep
{
public:
   ELSweep res;

   void Detect(const MqlRates &r[],const ELPool &pools[],double atr,const ELParams &p)
   {
      res.found=false; res.dir=EL_NONE; res.bar=-1; res.extreme=0;
      double minW=atr*p.sweepMinATR;
      for(int s=1;s<=p.sweepMaxAge;s++)
      {
         for(int pi=0;pi<ArraySize(pools);pi++)
         {
            if(pools[pi].t>=r[s].time) continue;
            if(pools[pi].isHigh)
            {
               if(r[s].high>pools[pi].price+minW && r[s].close<pools[pi].price)
               { res.found=true; res.dir=EL_SELL; res.pool=pools[pi]; res.bar=s; res.extreme=r[s].high; return; }
            }
            else
            {
               if(r[s].low<pools[pi].price-minW && r[s].close>pools[pi].price)
               { res.found=true; res.dir=EL_BUY; res.pool=pools[pi]; res.bar=s; res.extreme=r[s].low; return; }
            }
         }
      }
   }
};
#endif

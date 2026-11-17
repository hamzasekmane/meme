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
      res.found = false; res.dir = EL_NONE; res.bar = -1; res.extreme = 0;
      double minW = atr * p.sweepMinATR;

      for(int s = 1; s <= p.sweepMaxAge; s++)
      {
         for(int pi = 0; pi < ArraySize(pools); pi++)
         {
            if(pools[pi].t >= r[s].time) continue;

            if(pools[pi].isHigh)
            {
               // Sweep of high: wick extends beyond pool + minW, but candle closes back below pool price
               if(r[s].high > pools[pi].price + minW && r[s].close < pools[pi].price)
               {
                  // Verify that subsequent closed bars did not accept and close above the pool
                  bool invalidated = false;
                  double highest = r[s].high;
                  for(int k = s - 1; k >= 1; k--)
                  {
                     if(r[k].close > pools[pi].price) { invalidated = true; break; }
                     if(r[k].high > highest) highest = r[k].high;
                  }
                  if(!invalidated)
                  {
                     res.found   = true;
                     res.dir     = EL_SELL;
                     res.pool    = pools[pi];
                     res.bar     = s;
                     res.extreme = highest;
                     return;
                  }
               }
            }
            else
            {
               // Sweep of low: wick extends below pool - minW, but candle closes back above pool price
               if(r[s].low < pools[pi].price - minW && r[s].close > pools[pi].price)
               {
                  // Verify that subsequent closed bars did not accept and close below the pool
                  bool invalidated = false;
                  double lowest = r[s].low;
                  for(int k = s - 1; k >= 1; k--)
                  {
                     if(r[k].close < pools[pi].price) { invalidated = true; break; }
                     if(r[k].low < lowest) lowest = r[k].low;
                  }
                  if(!invalidated)
                  {
                     res.found   = true;
                     res.dir     = EL_BUY;
                     res.pool    = pools[pi];
                     res.bar     = s;
                     res.extreme = lowest;
                     return;
                  }
               }
            }
         }
      }
   }
};
#endif

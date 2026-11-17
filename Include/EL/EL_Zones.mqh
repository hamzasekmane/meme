#ifndef EL_ZONES_MQH
#define EL_ZONES_MQH
#include <EL/EL_Types.mqh>

// Entry zones: Order Block (at origin of move near sweep) and Fair Value Gap.
class CELZones
{
public:
   ELZone ob;
   ELZone fvg;

   void Build(const MqlRates &r[],int total,const ELSweep &sw,const ELBreak &bk)
   {
      ob.valid = false;
      fvg.valid = false;
      if(!sw.found || !bk.found) return;
      int dir = sw.dir;

      // Order block: origin candle near sweep extreme before the displacement break
      int startI = MathMin(sw.bar, total - 1);
      for(int i = startI; i >= bk.bar && i >= 1; i--)
      {
         bool bull = r[i].close > r[i].open;
         bool bear = r[i].close < r[i].open;
         if((dir == EL_SELL && bull) || (dir == EL_BUY && bear))
         {
            ob.valid  = true;
            ob.top    = r[i].high;
            ob.bottom = r[i].low;
            ob.t      = r[i].time;
            ob.bar    = i;
            ob.kind   = 0;
            break;
         }
      }

      // FVG: most recent 3-candle imbalance gap formed between sweep and now
      for(int i = 1; i <= sw.bar && i + 2 < total; i++)
      {
         if(dir == EL_SELL && r[i+2].low > r[i].high)
         {
            double top = r[i+2].low;
            double bot = r[i].high;
            bool filled = false;
            // Check if subsequent bars completely filled the gap
            for(int j = 0; j < i; j++)
            {
               if(r[j].high >= top) { filled = true; break; }
            }
            if(!filled && top > bot)
            {
               fvg.valid  = true;
               fvg.top    = top;
               fvg.bottom = bot;
               fvg.t      = r[i+1].time;
               fvg.bar    = i + 1;
               fvg.kind   = 1;
               break;
            }
         }
         if(dir == EL_BUY && r[i].low > r[i+2].high)
         {
            double top = r[i].low;
            double bot = r[i+2].high;
            bool filled = false;
            for(int j = 0; j < i; j++)
            {
               if(r[j].low <= bot) { filled = true; break; }
            }
            if(!filled && top > bot)
            {
               fvg.valid  = true;
               fvg.top    = top;
               fvg.bottom = bot;
               fvg.t      = r[i+1].time;
               fvg.bar    = i + 1;
               fvg.kind   = 1;
               break;
            }
         }
      }
   }
};
#endif

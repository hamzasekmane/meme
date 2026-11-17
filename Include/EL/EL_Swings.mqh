#ifndef EL_SWINGS_MQH
#define EL_SWINGS_MQH
#include <EL/EL_Types.mqh>

// Fractal swing detection. Arrays are sorted newest first (bar ascending).
class CELSwings
{
public:
   ELSwing highs[];
   ELSwing lows[];

   void Scan(const MqlRates &r[], int total, int LR, int lookback)
   {
      ArrayResize(highs,0); ArrayResize(lows,0);
      int maxI=MathMin(lookback,total-LR-1);
      for(int i=LR;i<=maxI;i++)
      {
         bool h=true,l=true;
         for(int k=1;k<=LR;k++)
         {
            if(r[i].high<r[i-k].high || r[i].high<r[i+k].high) h=false;
            if(r[i].low >r[i-k].low  || r[i].low >r[i+k].low ) l=false;
         }
         if(h){ int n=ArraySize(highs); ArrayResize(highs,n+1); highs[n].bar=i; highs[n].t=r[i].time; highs[n].p=r[i].high; highs[n].isHigh=true; }
         if(l){ int n=ArraySize(lows);  ArrayResize(lows,n+1);  lows[n].bar=i;  lows[n].t=r[i].time;  lows[n].p=r[i].low;  lows[n].isHigh=false; }
      }
   }
};
#endif

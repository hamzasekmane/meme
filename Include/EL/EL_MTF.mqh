#ifndef EL_MTF_MQH
#define EL_MTF_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>
#include <EL/EL_Swings.mqh>

// Structural trend bias from two independently confirmed swing highs and lows.
// Returns EL_NONE when the timeframe is mixed, immature, or not loaded.
int EL_StructuralBias(string sym,ENUM_TIMEFRAMES tf,const ELParams &p)
{
   MqlRates rates[]; ArraySetAsSeries(rates,true);
   int count=CopyRates(sym,tf,0,p.lookback+2*p.swingLR+10,rates);
   if(count<=2*p.swingLR+5) return EL_NONE;
   CELSwings sw; sw.Scan(rates,count,p.swingLR,p.lookback);
   if(ArraySize(sw.highs)<2 || ArraySize(sw.lows)<2) return EL_NONE;

   bool higherHigh=sw.highs[0].p>sw.highs[1].p;
   bool higherLow =sw.lows[0].p >sw.lows[1].p;
   bool lowerHigh =sw.highs[0].p<sw.highs[1].p;
   bool lowerLow  =sw.lows[0].p <sw.lows[1].p;
   if(higherHigh && higherLow) return EL_BUY;
   if(lowerHigh && lowerLow) return EL_SELL;
   return EL_NONE;
}

bool EL_HTFAligned(string sym,int dir,const ELParams &p)
{
   if(dir==EL_NONE) return false;
   // Each timeframe is copied and swing-scanned independently using closed candles.
   return EL_StructuralBias(sym,PERIOD_D1,p)==dir &&
          EL_StructuralBias(sym,PERIOD_H4,p)==dir &&
          EL_StructuralBias(sym,PERIOD_H1,p)==dir;
}

// M5 confirmation: a closed M5 candle after the M15 setup closes through its
// own latest confirmed opposing swing. No M15 prices/swings are reused here.
bool EL_M5Confirms(string sym,int dir,datetime setupTime,const ELParams &p)
{
   MqlRates rates[]; ArraySetAsSeries(rates,true);
   int count=CopyRates(sym,PERIOD_M5,0,p.lookback+2*p.swingLR+10,rates);
   if(count<=2*p.swingLR+5 || rates[1].time<=setupTime) return false;
   CELSwings sw; sw.Scan(rates,count,p.swingLR,p.lookback);

   if(dir==EL_SELL)
   {
      for(int i=0;i<ArraySize(sw.lows);i++)
         if(sw.lows[i].bar>1) return rates[1].close<sw.lows[i].p;
   }
   else if(dir==EL_BUY)
   {
      for(int i=0;i<ArraySize(sw.highs);i++)
         if(sw.highs[i].bar>1) return rates[1].close>sw.highs[i].p;
   }
   return false;
}
#endif

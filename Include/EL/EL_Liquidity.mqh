#ifndef EL_LIQUIDITY_MQH
#define EL_LIQUIDITY_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>

// Liquidity pools: EQH/EQL, recent swing highs/lows, PDH/PDL, PWH/PWL, Asia range.
class CELLiquidity
{
public:
   ELPool pools[];

   bool IsExternalTag(const string tag)
   {
      return tag=="EQH" || tag=="EQL" || tag=="PDH" || tag=="PDL" ||
             tag=="PWH" || tag=="PWL" || tag=="ASH" || tag=="ASL";
   }

   void Add(double price,datetime t,datetime available,bool hi,string tag,double tol)
   {
      if(price<=0 || available<=0) return;
      for(int i=0;i<ArraySize(pools);i++)
      {
         if(pools[i].isHigh==hi && MathAbs(pools[i].price-price)<=tol*0.5)
         {
            // Do not let a nearby minor swing hide a qualified external pool target.
            if(IsExternalTag(tag) && !IsExternalTag(pools[i].tag))
            { pools[i].price=price; pools[i].t=t; pools[i].available=available; pools[i].tag=tag; }
            return;
         }
      }
      int n=ArraySize(pools);
      ArrayResize(pools,n+1);
      pools[n].price=price;
      pools[n].t=t;
      pools[n].available=available;
      pools[n].isHigh=hi;
      pools[n].tag=tag;
   }

   void Build(string sym,const MqlRates &r[],int total,const ELSwing &hi[],const ELSwing &lo[],double atr,const ELParams &p)
   {
      ArrayResize(pools,0);
      double tol = atr * p.eqTolATR;
      int nh = MathMin(ArraySize(hi), 10), nl = MathMin(ArraySize(lo), 10);

      // Equal highs / lows
      for(int a = 0; a < nh; a++)
         for(int b = a + 1; b < nh; b++)
            if(MathAbs(hi[a].p - hi[b].p) <= tol)
            {
               int confirmBar=(int)MathMin(hi[a].bar,hi[b].bar)-p.swingLR;
               datetime available=(confirmBar>=1)?r[confirmBar].time+PeriodSeconds():0;
               Add(MathMax(hi[a].p,hi[b].p),hi[a].t,available,true,"EQH",tol);
               break;
            }
      for(int a = 0; a < nl; a++)
         for(int b = a + 1; b < nl; b++)
            if(MathAbs(lo[a].p - lo[b].p) <= tol)
            {
               int confirmBar=(int)MathMin(lo[a].bar,lo[b].bar)-p.swingLR;
               datetime available=(confirmBar>=1)?r[confirmBar].time+PeriodSeconds():0;
               Add(MathMin(lo[a].p,lo[b].p),lo[a].t,available,false,"EQL",tol);
               break;
            }

      // Recent single swings (minor liquidity)
      for(int a=0;a<MathMin(nh,3);a++)
      {
         int confirmBar=hi[a].bar-p.swingLR;
         datetime available=(confirmBar>=1)?r[confirmBar].time+PeriodSeconds():0;
         Add(hi[a].p,hi[a].t,available,true,"SWH",tol);
      }
      for(int a=0;a<MathMin(nl,3);a++)
      {
         int confirmBar=lo[a].bar-p.swingLR;
         datetime available=(confirmBar>=1)?r[confirmBar].time+PeriodSeconds():0;
         Add(lo[a].p,lo[a].t,available,false,"SWL",tol);
      }

      // Previous day / week (checking history validity)
      datetime dtD1=iTime(sym,PERIOD_D1,1);
      datetime availD1=iTime(sym,PERIOD_D1,0); // completed prior-day levels are usable from today's open
      if(dtD1>0 && availD1>0)
      {
         double pdh=iHigh(sym,PERIOD_D1,1),pdl=iLow(sym,PERIOD_D1,1);
         if(pdh>0) Add(pdh,dtD1,availD1,true,"PDH",tol);
         if(pdl>0) Add(pdl,dtD1,availD1,false,"PDL",tol);
      }
      datetime dtW1=iTime(sym,PERIOD_W1,1);
      datetime availW1=iTime(sym,PERIOD_W1,0);
      if(dtW1>0 && availW1>0)
      {
         double pwh=iHigh(sym,PERIOD_W1,1),pwl=iLow(sym,PERIOD_W1,1);
         if(pwh>0) Add(pwh,dtW1,availW1,true,"PWH",tol);
         if(pwl>0) Add(pwl,dtW1,availW1,false,"PWL",tol);
      }

      // Asia range: find latest COMPLETED session using calendar day to avoid timezone wrap bugs
      if(total > 1)
      {
         MqlDateTime mNow;
         TimeToStruct(r[0].time, mNow);
         int curDayKey = mNow.year * 1000 + mNow.day_of_year;
         int targetDayKey = -1;
         bool sessionFound = false;
         double ah = 0, al = 0;
         datetime endT = 0;

         for(int i = 1; i < total; i++)
         {
            MqlDateTime m;
            TimeToStruct(r[i].time, m);
            int barDayKey = m.year * 1000 + m.day_of_year;
            bool isAsiaHour = (m.hour >= p.asiaStart && m.hour < p.asiaEnd);

            if(targetDayKey == -1)
            {
               // Session is completed if today has passed asiaEnd or bar is from a prior day
               if(isAsiaHour && (barDayKey < curDayKey || mNow.hour >= p.asiaEnd))
               {
                  targetDayKey = barDayKey;
                  sessionFound = true;
                  ah   = r[i].high;
                  al   = r[i].low;
                  endT = r[i].time;
               }
            }
            else
            {
               if(barDayKey == targetDayKey)
               {
                  if(isAsiaHour)
                  {
                     ah = MathMax(ah, r[i].high);
                     al = MathMin(al, r[i].low);
                     if(r[i].time > endT) endT = r[i].time;
                  }
               }
               else if(barDayKey < targetDayKey)
               {
                  break;
               }
            }
         }
         if(sessionFound && ah > 0 && al > 0)
         {
            datetime available=endT+PeriodSeconds();
            Add(ah,endT,available,true,"ASH",tol);
            Add(al,endT,available,false,"ASL",tol);
         }
      }
   }
};
#endif

#ifndef EL_LIQUIDITY_MQH
#define EL_LIQUIDITY_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>

// Liquidity pools: EQH/EQL, recent swing highs/lows, PDH/PDL, PWH/PWL, Asia range.
class CELLiquidity
{
public:
   ELPool pools[];

   void Add(double price,datetime t,bool hi,string tag,double tol)
   {
      if(price<=0) return;
      for(int i=0;i<ArraySize(pools);i++)
         if(pools[i].isHigh==hi && MathAbs(pools[i].price-price)<=tol*0.5) return;
      int n=ArraySize(pools); ArrayResize(pools,n+1);
      pools[n].price=price; pools[n].t=t; pools[n].isHigh=hi; pools[n].tag=tag;
   }

   void Build(string sym,const MqlRates &r[],int total,const ELSwing &hi[],const ELSwing &lo[],double atr,const ELParams &p)
   {
      ArrayResize(pools,0);
      double tol=atr*p.eqTolATR;
      int nh=MathMin(ArraySize(hi),10), nl=MathMin(ArraySize(lo),10);

      // Equal highs / lows
      for(int a=0;a<nh;a++)
         for(int b=a+1;b<nh;b++)
            if(MathAbs(hi[a].p-hi[b].p)<=tol){ Add(MathMax(hi[a].p,hi[b].p),hi[a].t,true,"EQH",tol); break; }
      for(int a=0;a<nl;a++)
         for(int b=a+1;b<nl;b++)
            if(MathAbs(lo[a].p-lo[b].p)<=tol){ Add(MathMin(lo[a].p,lo[b].p),lo[a].t,false,"EQL",tol); break; }

      // Recent single swings (minor liquidity)
      for(int a=0;a<MathMin(nh,3);a++) Add(hi[a].p,hi[a].t,true,"SWH",tol);
      for(int a=0;a<MathMin(nl,3);a++) Add(lo[a].p,lo[a].t,false,"SWL",tol);

      // Previous day / week
      datetime d0=iTime(sym,PERIOD_D1,0), w0=iTime(sym,PERIOD_W1,0);
      Add(iHigh(sym,PERIOD_D1,1),d0,true,"PDH",tol);  Add(iLow(sym,PERIOD_D1,1),d0,false,"PDL",tol);
      Add(iHigh(sym,PERIOD_W1,1),w0,true,"PWH",tol);  Add(iLow(sym,PERIOD_W1,1),w0,false,"PWL",tol);

      // Asia range (latest session found in history)
      bool got=false; datetime day=0, endT=0; double ah=0, al=0;
      for(int i=1;i<total;i++)
      {
         MqlDateTime m; TimeToStruct(r[i].time,m);
         bool in=(m.hour>=p.asiaStart && m.hour<p.asiaEnd);
         datetime d=r[i].time-(r[i].time%86400);
         if(!got){ if(in){ got=true; day=d; endT=r[i].time; ah=r[i].high; al=r[i].low; } }
         else
         {
            if(in && d==day){ ah=MathMax(ah,r[i].high); al=MathMin(al,r[i].low); }
            else if(d<day) break;
         }
      }
      if(got){ Add(ah,endT,true,"ASH",tol); Add(al,endT,false,"ASL",tol); }
   }
};
#endif

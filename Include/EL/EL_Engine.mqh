#ifndef EL_ENGINE_MQH
#define EL_ENGINE_MQH
#include <EL/EL_Types.mqh>
#include <EL/EL_Config.mqh>
#include <EL/EL_Swings.mqh>
#include <EL/EL_Liquidity.mqh>
#include <EL/EL_Sweep.mqh>
#include <EL/EL_Structure.mqh>
#include <EL/EL_Zones.mqh>
#include <EL/EL_Filters.mqh>
#include <EL/EL_Signal.mqh>

// Orchestrates all modules. Used identically by the indicator and the EA.
class CELEngine
{
public:
   string          sym;
   ENUM_TIMEFRAMES tf;
   ELParams        p;
   int             hATR;
   MqlRates        r[];
   int             total;
   double          atr;
   CELSwings       swings;
   CELLiquidity    liq;
   CELSweep        swp;
   CELStructure    st;
   CELZones        zn;
   CELSig          sg;
   ELSignal        sig;

   CELEngine(){ hATR=INVALID_HANDLE; total=0; atr=0; sig.valid=false; }

   bool Init(string s,ENUM_TIMEFRAMES t,const ELParams &pp)
   {
      sym=s; tf=t; p=pp;
      hATR=iATR(sym,tf,p.atrPeriod);
      return hATR!=INVALID_HANDLE;
   }

   void Deinit(){ if(hATR!=INVALID_HANDLE){ IndicatorRelease(hATR); hATR=INVALID_HANDLE; } }

   // Call once per new bar. Returns false if data is not ready.
   bool Update()
   {
      ArraySetAsSeries(r,true);
      total=CopyRates(sym,tf,0,p.lookback+20,r);
      if(total<p.lookback/2) return false;
      double a[]; ArraySetAsSeries(a,true);
      if(CopyBuffer(hATR,0,1,1,a)<1 || a[0]<=0) return false;
      atr=a[0];

      swings.Scan(r,total,p.swingLR,p.lookback);
      liq.Build(sym,r,total,swings.highs,swings.lows,atr,p);
      swp.Detect(r,liq.pools,atr,p);
      st.Detect(r,swings.highs,swings.lows,swp.res);
      zn.Build(r,total,swp.res,st.brk);
      sg.Build(r,swp.res,st.brk,zn.ob,zn.fvg,liq.pools,atr,p,sig);
      return true;
   }
};
#endif

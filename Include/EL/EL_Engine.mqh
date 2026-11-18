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
#include <EL/EL_Validation.mqh>
#include <EL/EL_MTF.mqh>

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
      if(s=="" || pp.swingLR<1 || pp.lookback<30 || pp.atrPeriod<2 ||
         pp.sweepMaxAge<1 || pp.rrMin<=0 || pp.slBufATR<0 ||
         pp.minDisplacementATR<0 || pp.minScore<0 || pp.minScore>100)
         return false;
      sym=s; tf=t; p=pp;
      hATR=iATR(sym,tf,p.atrPeriod);
      return hATR!=INVALID_HANDLE;
   }

   void Deinit(){ if(hATR!=INVALID_HANDLE){ IndicatorRelease(hATR); hATR=INVALID_HANDLE; } }

   // Call once per new bar. All decision inputs are closed-bar data; failed updates
   // clear the published signal so an old result cannot remain actionable or visible.
   bool Update()
   {
      sg.Reset(sig);
      ArraySetAsSeries(r,true);
      total=CopyRates(sym,tf,0,p.lookback+20,r);
      if(total<MathMax(p.lookback/2,3)) return false;
      double a[]; ArraySetAsSeries(a,true);
      if(CopyBuffer(hATR,0,1,1,a)<1 || a[0]<=0) return false;
      atr=a[0];

      swings.Scan(r,total,p.swingLR,p.lookback);
      liq.Build(sym,r,total,swings.highs,swings.lows,atr,p);
      swp.Detect(r,liq.pools,atr,p);
      st.Detect(r,swings.highs,swings.lows,swp.res,p.swingLR);
      zn.Build(r,total,swp.res,st.brk);
      double breakAtr=atr;
      if(st.brk.found)
      {
         double ab[]; ArraySetAsSeries(ab,true);
         if(CopyBuffer(hATR,0,st.brk.bar,1,ab)<1 || ab[0]<=0) return false;
         breakAtr=ab[0];
      }
      sg.Build(sym,tf,r,swp.res,st.brk,zn.ob,zn.fvg,liq.pools,atr,breakAtr,p,PeriodSeconds(tf),sig);

      if(!sig.valid) return true;
      if(sig.expiresAt<=TimeCurrent())
      {
         sig.expired=true;
         sig.state=EL_EXPIRED;
         sig.reason+=" | EXPIRED: sweep validity window elapsed";
         return true;
      }
      if(tf!=PERIOD_M15)
      {
         sig.reason+=" | ANALYTICAL ONLY: execution timeframe is M15";
         return true;
      }

      sig.biasConfirmed=EL_HTFAligned(sym,sig.dir,p);
      if(!sig.biasConfirmed)
      {
         sig.state=EL_STATE_WAIT;
         sig.reason+=" | WAIT: D1/H4/H1 swing bias not aligned";
         return true;
      }
      sig.state=EL_BIAS_CONFIRMED;
      if(!EL_M5Confirms(sym,sig.dir,sig.t,p))
      {
         sig.state=EL_STATE_WAIT;
         sig.reason+=" | WAIT: M5 closed-bar structure confirmation missing";
         return true;
      }
      if(sig.score<p.minScore)
      {
         sig.state=EL_STATE_WAIT;
         sig.reason+=" | WAIT: score below execution threshold";
         return true;
      }

      string invalidReason="";
      if(!EL_ValidateLimitPlan(sym,sig.dir,sig.entry,sig.sl,sig.tp,p.rrMin,invalidReason))
      {
         sig.entryValidated=false;
         sig.riskValidated=false;
         sig.invalidated=true;
         sig.state=EL_INVALIDATED;
         sig.reason+=" | INVALID: "+invalidReason;
         return true;
      }
      sig.entryValidated=true;
      sig.riskValidated=true;
      sig.executionReady=true;
      sig.state=EL_EXECUTION_READY;
      return true;
   }
};
#endif

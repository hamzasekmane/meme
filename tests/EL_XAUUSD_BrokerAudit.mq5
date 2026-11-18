// Run this Script inside the target broker's MT5 terminal. It places NO orders.
// It reads the selected symbol's live contract/quote properties and checks the
// production EL_ValidateLimitPlan and EL_LotsByRisk helpers against those values.
#property strict
#property script_show_inputs

#include <EL/EL_Validation.mqh>
#include <EL/EL_Risk.mqh>

input string InpBrokerSymbol = "XAUUSD"; // Set the broker's exact symbol, including any suffix.
input double InpRiskPercent  = 0.5;       // Existing EA risk input; not changed by this test.
input double InpMinimumRR   = 2.0;       // Existing EL RR input; not changed by this test.

int g_failed=0;
int g_passed=0;

void Check(const string name,bool passed,const string detail="")
{
   if(passed) g_passed++; else g_failed++;
   PrintFormat("EL broker audit %s: %s%s",passed?"PASS":"FAIL",name,detail==""?"":" | "+detail);
}

bool CheckPlan(const string name,string sym,int dir,double entry,double sl,double tp,double rrMin,bool expected)
{
   string why="";
   bool actual=EL_ValidateLimitPlan(sym,dir,entry,sl,tp,rrMin,why);
   bool passed=(actual==expected);
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   Check(name,passed,StringFormat("actual=%s expected=%s entry=%s sl=%s tp=%s %s",
        actual?"valid":"rejected",expected?"valid":"rejected",
        DoubleToString(entry,digits),DoubleToString(sl,digits),DoubleToString(tp,digits),why));
   return passed;
}

void OnStart()
{
   if(!SymbolSelect(InpBrokerSymbol,true))
   {
      Check("symbol available",false,"SymbolSelect failed for "+InpBrokerSymbol);
      return;
   }

   double point=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_POINT);
   double tick=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_SIZE);
   double tickValue=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE);
   double tickValueLoss=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_LOSS);
   double volMin=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MIN);
   double volMax=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MAX);
   double volStep=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_STEP);
   int digits=(int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_DIGITS);
   int stops=(int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_TRADE_STOPS_LEVEL);
   int freeze=(int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_TRADE_FREEZE_LEVEL);
   long expiration=SymbolInfoInteger(InpBrokerSymbol,SYMBOL_EXPIRATION_MODE);
   long orderMode=SymbolInfoInteger(InpBrokerSymbol,SYMBOL_ORDER_MODE);
   MqlTick q;

   PrintFormat("EL actual broker symbol specs: symbol=%s digits=%d point=%.10f tickSize=%.10f tickValue=%.10f tickValueLoss=%.10f volumeMin=%.4f volumeMax=%.4f volumeStep=%.4f stopsLevel=%d freezeLevel=%d expirationMode=%I64d orderMode=%I64d",
               InpBrokerSymbol,digits,point,tick,tickValue,tickValueLoss,volMin,volMax,volStep,stops,freeze,expiration,orderMode);

   bool specsOk=(point>0 && tick>0 && volMin>0 && volStep>0 && SymbolInfoTick(InpBrokerSymbol,q) && q.bid>0 && q.ask>=q.bid);
   Check("usable broker contract and live quote",specsOk);
   if(!specsOk) return;
   Check("broker allows pending limit orders",(orderMode & SYMBOL_ORDER_LIMIT)!=0);
   Check("broker supports specified expiry",(expiration & SYMBOL_EXPIRATION_SPECIFIED)!=0);

   double stopDistance=MathMax((double)stops*point,tick);
   double minRisk=MathMax(stopDistance*20.0,tick*20.0);

   // Tradable tick-grid normalization on the exact broker symbol.
   double gridPrice=EL_NormalizeToTick(InpBrokerSymbol,q.bid+tick*1.37);
   double gridUnits=gridPrice/tick;
   Check("normalized price lies on broker tick grid",MathAbs(gridUnits-MathRound(gridUnits))<1e-6,
         StringFormat("price=%s tick=%.10f",DoubleToString(gridPrice,digits),tick));

   // Valid Sell Limit: above Bid, structural SL above entry, external TP >= RR threshold below.
   double sellEntry=EL_CeilToTick(InpBrokerSymbol,q.bid+stopDistance*5.0);
   double sellSL=EL_CeilToTick(InpBrokerSymbol,sellEntry+minRisk);
   double sellTP=EL_FloorToTick(InpBrokerSymbol,sellEntry-minRisk*(InpMinimumRR+0.5));
   CheckPlan("valid Sell Limit retracement",InpBrokerSymbol,EL_SELL,sellEntry,sellSL,sellTP,InpMinimumRR,true);

   // Valid Buy Limit: below Ask, structural SL below entry, external TP above RR threshold.
   double buyEntry=EL_FloorToTick(InpBrokerSymbol,q.ask-stopDistance*5.0);
   double buySL=EL_FloorToTick(InpBrokerSymbol,buyEntry-minRisk);
   double buyTP=EL_CeilToTick(InpBrokerSymbol,buyEntry+minRisk*(InpMinimumRR+0.5));
   CheckPlan("valid Buy Limit retracement",InpBrokerSymbol,EL_BUY,buyEntry,buySL,buyTP,InpMinimumRR,true);

   // Invalid market-side / wrong-side limit prices are rejected, never converted to market orders.
   double badSell=EL_FloorToTick(InpBrokerSymbol,q.bid-stopDistance*2.0);
   CheckPlan("invalid Sell Limit below Bid",InpBrokerSymbol,EL_SELL,badSell,badSell+minRisk,badSell-minRisk*3.0,InpMinimumRR,false);
   double badBuy=EL_CeilToTick(InpBrokerSymbol,q.ask+stopDistance*2.0);
   CheckPlan("invalid Buy Limit above Ask",InpBrokerSymbol,EL_BUY,badBuy,badBuy-minRisk,badBuy+minRisk*3.0,InpMinimumRR,false);

   // Fail RR after normal price mapping: a favorable direction alone is insufficient.
   double shortTarget=EL_FloorToTick(InpBrokerSymbol,sellEntry-minRisk*1.5);
   CheckPlan("below-minimum RR plan rejected",InpBrokerSymbol,EL_SELL,sellEntry,sellSL,shortTarget,InpMinimumRR,false);

   // Excessive structural SL is preserved; lot sizing may go to zero or decrease, never widen risk.
   double nearSL=EL_CeilToTick(InpBrokerSymbol,sellEntry+tick*20.0);
   double wideSL=EL_CeilToTick(InpBrokerSymbol,sellEntry+tick*20000.0);
   double nearLots=EL_LotsByRisk(InpBrokerSymbol,InpRiskPercent,sellEntry,nearSL);
   double wideLots=EL_LotsByRisk(InpBrokerSymbol,InpRiskPercent,sellEntry,wideSL);
   Check("wide structural SL reduces or skips size",wideSL>nearSL && wideLots<=nearLots,
         StringFormat("nearSL=%s wideSL=%s nearLots=%.4f wideLots=%.4f",
                      DoubleToString(nearSL,digits),DoubleToString(wideSL,digits),nearLots,wideLots));

   PrintFormat("EL broker audit complete: passed=%d failed=%d symbol=%s (NO ORDERS SENT)",g_passed,g_failed,InpBrokerSymbol);
}

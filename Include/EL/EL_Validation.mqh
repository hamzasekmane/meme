#ifndef EL_VALIDATION_MQH
#define EL_VALIDATION_MQH
#include <EL/EL_Types.mqh>

// Round to the symbol's tradable tick grid, not merely its displayed decimal digits.
double EL_NormalizeToTick(string sym,double price)
{
   double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   if(tick<=0) tick=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(tick<=0 || price<=0) return 0;
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   return NormalizeDouble(MathRound(price/tick)*tick,digits);
}

double EL_FloorToTick(string sym,double price)
{
   double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   if(tick<=0) tick=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(tick<=0 || price<=0) return 0;
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   return NormalizeDouble(MathFloor(price/tick+1e-10)*tick,digits);
}

double EL_CeilToTick(string sym,double price)
{
   double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   if(tick<=0) tick=SymbolInfoDouble(sym,SYMBOL_POINT);
   if(tick<=0 || price<=0) return 0;
   int digits=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
   return NormalizeDouble(MathCeil(price/tick-1e-10)*tick,digits);
}

// Validate a retracement LIMIT plan against executable quotes and broker geometry.
// No distance cap is imposed: time/sweep freshness and the actual zone determine validity.
bool EL_ValidateLimitPlan(string sym,int dir,double &entry,double &sl,double &tp,double rrMin,string &why)
{
   why="";
   MqlTick q;
   if(!SymbolInfoTick(sym,q) || q.ask<=0 || q.bid<=0 || q.ask<q.bid)
   { why="no valid bid/ask"; return false; }

   double point=SymbolInfoDouble(sym,SYMBOL_POINT);
   double tick=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   if(point<=0) { why="invalid point size"; return false; }
   if(tick<=0) tick=point;
   double minDist=MathMax((double)SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL)*point,tick);

   // Preserve pending-limit side when mapping analytical prices to the broker tick grid.
   entry=(dir==EL_BUY)?EL_FloorToTick(sym,entry):EL_CeilToTick(sym,entry);
   // Round the structural stop away from entry: never trim the invalidation buffer.
   sl=(dir==EL_BUY)?EL_FloorToTick(sym,sl):EL_CeilToTick(sym,sl);
   tp=EL_NormalizeToTick(sym,tp);
   if(entry<=0 || sl<=0 || tp<=0) { why="invalid normalized price"; return false; }

   double risk=0,reward=0;
   if(dir==EL_BUY)
   {
      if(entry>=q.ask-minDist) { why="BUY LIMIT is not below executable Ask by broker minimum"; return false; }
      if(sl>=entry-minDist) { why="BUY SL is not below entry by broker minimum"; return false; }
      if(tp<=entry+minDist) { why="BUY TP is not above entry by broker minimum"; return false; }
      risk=entry-sl; reward=tp-entry;
   }
   else if(dir==EL_SELL)
   {
      if(entry<=q.bid+minDist) { why="SELL LIMIT is not above executable Bid by broker minimum"; return false; }
      if(sl<=entry+minDist) { why="SELL SL is not above entry by broker minimum"; return false; }
      if(tp>=entry-minDist) { why="SELL TP is not below entry by broker minimum"; return false; }
      risk=sl-entry; reward=entry-tp;
   }
   else { why="unknown direction"; return false; }

   if(risk<=0 || reward<=0) { why="non-positive risk or reward"; return false; }
   if(rrMin>0 && reward/risk+1e-8<rrMin) { why="normalized plan is below minimum RR"; return false; }
   return true;
}
#endif

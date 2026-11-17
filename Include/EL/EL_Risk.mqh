#ifndef EL_RISK_MQH
#define EL_RISK_MQH

// Position size so that a stop-out loses riskPct % of equity.
double EL_LotsByRisk(string sym,double riskPct,double entry,double sl)
{
   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   double tickVal=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   double tickSize=SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   double dist=MathAbs(entry-sl);
   if(eq<=0 || tickVal<=0 || tickSize<=0 || dist<=0) return 0;
   double lossPerLot=dist/tickSize*tickVal;
   double lots=(eq*riskPct/100.0)/lossPerLot;
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   if(step<=0) step=0.01;
   lots=MathFloor(lots/step)*step;
   if(lots<vmin) return 0;           // risk too small for min lot: skip instead of over-risking
   lots=MathMin(lots,vmax);
   return NormalizeDouble(lots,2);
}
#endif

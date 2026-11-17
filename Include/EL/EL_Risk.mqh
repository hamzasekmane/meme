#ifndef EL_RISK_MQH
#define EL_RISK_MQH

// Position size so that a stop-out loses riskPct % of equity, with margin safety check.
double EL_LotsByRisk(string sym,double riskPct,double entry,double sl)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double tickVal = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickVal <= 0) tickVal = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double dist = MathAbs(entry - sl);

   if(eq <= 0 || tickVal <= 0 || tickSize <= 0 || dist <= 0) return 0;

   double lossPerLot = (dist / tickSize) * tickVal;
   double lots = (eq * (riskPct / 100.0)) / lossPerLot;

   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;

   lots = MathFloor(lots / step) * step;
   if(lots < vmin) return 0; // risk too small for min lot: skip instead of over-risking
   lots = MathMin(lots, vmax);

   // Determine exact decimal digits supported by the symbol's volume step
   int stepDigits = 0;
   if(step < 1.0 && step > 0)
      stepDigits = (int)MathCeil(-MathLog10(step));
   lots = NormalizeDouble(lots, stepDigits);

   // Margin verification to avoid 10019 (TRADE_RETCODE_NO_MONEY)
   ENUM_ORDER_TYPE orderType = (entry > sl) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
   double marginReq = 0;
   if(OrderCalcMargin(orderType, sym, lots, entry, marginReq))
   {
      double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      if(freeMargin > 0 && marginReq > freeMargin * 0.90)
      {
         double maxAllowedMargin = freeMargin * 0.90;
         double marginScale = maxAllowedMargin / marginReq;
         lots = MathFloor((lots * marginScale) / step) * step;
         lots = NormalizeDouble(lots, stepDigits);
         if(lots < vmin) return 0;
      }
   }

   return lots;
}
#endif

#ifndef EL_TRADE_MQH
#define EL_TRADE_MQH
#include <Trade/Trade.mqh>
#include <EL/EL_Types.mqh>

class CELTrade
{
   CTrade t;
   long   magic;
   int    dev;
public:
   void Init(long m,int deviation)
   {
      magic = m;
      dev   = deviation;
      t.SetExpertMagicNumber((ulong)m);
      t.SetDeviationInPoints(deviation);
   }

   bool HasExposure(string sym)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(PositionGetTicket(i) == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) == sym && PositionGetInteger(POSITION_MAGIC) == magic) return true;
      }
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         if(OrderGetTicket(i) == 0) continue;
         if(OrderGetString(ORDER_SYMBOL) == sym && OrderGetInteger(ORDER_MAGIC) == magic) return true;
      }
      return false;
   }

   bool PlaceLimit(string sym,const ELSignal &s,double lots,datetime expiry)
   {
      t.SetTypeFillingBySymbol(sym);
      int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double pt = SymbolInfoDouble(sym, SYMBOL_POINT);
      int stopsLevel = (int)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
      double minDist = stopsLevel * pt;

      double e  = NormalizeDouble(s.entry, dg);
      double sl = NormalizeDouble(s.sl, dg);
      double tp = NormalizeDouble(s.tp, dg);

      // Validate against current market price and broker stops level
      double curAsk = SymbolInfoDouble(sym, SYMBOL_ASK);
      double curBid = SymbolInfoDouble(sym, SYMBOL_BID);

      if(s.dir == EL_BUY && (curAsk - e) < minDist)
      {
         PrintFormat("EL: BuyLimit price %.2f too close to Ask %.2f (stopsLevel=%d)", e, curAsk, stopsLevel);
         return false;
      }
      if(s.dir == EL_SELL && (e - curBid) < minDist)
      {
         PrintFormat("EL: SellLimit price %.2f too close to Bid %.2f (stopsLevel=%d)", e, curBid, stopsLevel);
         return false;
      }

      // Check broker expiration policy: fallback to GTC if SPECIFIED is not supported
      uint expMode = (uint)SymbolInfoInteger(sym, SYMBOL_EXPIRATION_MODE);
      ENUM_ORDER_TYPE_TIME timeType = ORDER_TIME_GTC;
      datetime expTime = 0;

      if((expMode & SYMBOL_EXPIRATION_SPECIFIED) != 0 && expiry > TimeCurrent())
      {
         timeType = ORDER_TIME_SPECIFIED;
         expTime  = expiry;
      }

      bool ok = (s.dir == EL_BUY)
              ? t.BuyLimit(lots, e, sym, sl, tp, timeType, expTime, "EL")
              : t.SellLimit(lots, e, sym, sl, tp, timeType, expTime, "EL");

      if(!ok)
         PrintFormat("EL: Limit order failed! Retcode=%d (%s)", t.ResultRetcode(), t.ResultRetcodeDescription());
      else
         PrintFormat("EL: %s Limit order placed at %.2f (SL: %.2f, TP: %.2f, Lots: %.2f)",
                     s.dir == EL_BUY ? "BUY" : "SELL", e, sl, tp, lots);

      return ok;
   }

   // At partialR x initial risk: close partialPct % and move SL to break-even (+ buffer)
   void Manage(string sym,double partialR,double partialPct)
   {
      int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double pt = SymbolInfoDouble(sym, SYMBOL_POINT);
      int stopsLevel = (int)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
      double minDist = stopsLevel * pt;

      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong tk = PositionGetTicket(i);
         if(tk == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) != sym || PositionGetInteger(POSITION_MAGIC) != magic) continue;

         bool buy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
         double op  = PositionGetDouble(POSITION_PRICE_OPEN);
         double sl  = PositionGetDouble(POSITION_SL);
         double tp  = PositionGetDouble(POSITION_TP);
         double vol = PositionGetDouble(POSITION_VOLUME);

         if(sl == 0) continue;
         double R = buy ? (op - sl) : (sl - op);
         if(R <= 0) continue; // Already at or past break-even

         double px = buy ? SymbolInfoDouble(sym, SYMBOL_BID) : SymbolInfoDouble(sym, SYMBOL_ASK);
         double prof = buy ? (px - op) : (op - px);
         if(prof < R * partialR) continue;

         // Small buffer (2 points) past open price to cover minimal slippage/costs
         double beBuffer = 2.0 * pt;
         double beSL = buy ? (op + beBuffer) : (op - beBuffer);
         beSL = NormalizeDouble(beSL, dg);

         // Ensure distance to current price respects broker stops level
         if(buy && (px - beSL) < minDist) continue;
         if(!buy && (beSL - px) < minDist) continue;

         // Partial close if requested
         if(partialPct > 0 && partialPct < 100)
         {
            double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
            double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
            double part = MathFloor((vol * partialPct / 100.0) / step) * step;
            if(part >= vmin && (vol - part) >= vmin)
            {
               t.PositionClosePartial(tk, part);
            }
         }

         // Move SL to break-even
         t.PositionModify(tk, beSL, tp);
      }
   }
};
#endif

#ifndef EL_TRADE_MQH
#define EL_TRADE_MQH
#include <Trade/Trade.mqh>
#include <EL/EL_Types.mqh>

class CELTrade
{
   CTrade t;
   long   magic;
public:
   void Init(long m,int deviation)
   {
      magic=m; t.SetExpertMagicNumber((ulong)m); t.SetDeviationInPoints(deviation);
      t.SetTypeFillingBySymbol(_Symbol);
   }

   bool HasExposure(string sym)
   {
      for(int i=PositionsTotal()-1;i>=0;i--)
      {
         if(PositionGetTicket(i)==0) continue;
         if(PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==magic) return true;
      }
      for(int i=OrdersTotal()-1;i>=0;i--)
      {
         if(OrderGetTicket(i)==0) continue;
         if(OrderGetString(ORDER_SYMBOL)==sym && OrderGetInteger(ORDER_MAGIC)==magic) return true;
      }
      return false;
   }

   bool PlaceLimit(string sym,const ELSignal &s,double lots,datetime expiry)
   {
      int dg=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      double e=NormalizeDouble(s.entry,dg), sl=NormalizeDouble(s.sl,dg), tp=NormalizeDouble(s.tp,dg);
      bool ok=(s.dir==EL_BUY)
              ? t.BuyLimit(lots,e,sym,sl,tp,ORDER_TIME_SPECIFIED,expiry,"EL")
              : t.SellLimit(lots,e,sym,sl,tp,ORDER_TIME_SPECIFIED,expiry,"EL");
      if(!ok) PrintFormat("EL: order failed %d %s",t.ResultRetcode(),t.ResultRetcodeDescription());
      return ok;
   }

   // At partialR x initial risk: close partialPct % and move SL to break-even.
   void Manage(string sym,double partialR,double partialPct)
   {
      int dg=(int)SymbolInfoInteger(sym,SYMBOL_DIGITS);
      for(int i=PositionsTotal()-1;i>=0;i--)
      {
         ulong tk=PositionGetTicket(i);
         if(tk==0) continue;
         if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=magic) continue;
         bool buy=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY);
         double op=PositionGetDouble(POSITION_PRICE_OPEN), sl=PositionGetDouble(POSITION_SL), tp=PositionGetDouble(POSITION_TP);
         double vol=PositionGetDouble(POSITION_VOLUME);
         if(sl==0) continue;
         double R=buy? op-sl : sl-op;
         if(R<=0) continue;                       // already at/after break-even
         double px=buy? SymbolInfoDouble(sym,SYMBOL_BID) : SymbolInfoDouble(sym,SYMBOL_ASK);
         double prof=buy? px-op : op-px;
         if(prof<R*partialR) continue;

         double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP), vmin=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
         double part=MathFloor(vol*partialPct/100.0/step)*step;
         if(part>=vmin && vol-part>=vmin) t.PositionClosePartial(tk,part);
         t.PositionModify(tk,NormalizeDouble(op,dg),tp);
      }
   }
};
#endif

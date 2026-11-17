//+------------------------------------------------------------------+
//| EL_Indicator.mq5 - Engineered Liquidity (XAUUSD) - personal use  |
//+------------------------------------------------------------------+
#property copyright "Personal use"
#property version   "1.01"
#property indicator_chart_window
#property indicator_plots 0

#include <EL/EL_Inputs.mqh>
#include <EL/EL_Engine.mqh>

input group "=== Display ==="
input bool InpShowPools   = true;
input bool InpShowZones   = true;
input bool InpAlerts      = true;

CELEngine eng;
datetime  lastBar = 0, lastAlert = 0;

int OnInit()
{
   if(!eng.Init(_Symbol, (ENUM_TIMEFRAMES)_Period, EL_BuildParams()))
      return INIT_FAILED;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   eng.Deinit();
   ObjectsDeleteAll(0, "EL_");
   ObjectsDeleteAll(0, "ELS_");
}

void Line(string n, datetime t1, double p1, datetime t2, double p2, color c, ENUM_LINE_STYLE st, bool ray, string txt)
{
   if(ObjectFind(0, n) < 0)
      ObjectCreate(0, n, OBJ_TREND, 0, t1, p1, t2, p2);
   else
   {
      ObjectMove(0, n, 0, t1, p1);
      ObjectMove(0, n, 1, t2, p2);
   }
   ObjectSetInteger(0, n, OBJPROP_COLOR, c);
   ObjectSetInteger(0, n, OBJPROP_STYLE, st);
   ObjectSetInteger(0, n, OBJPROP_RAY_RIGHT, ray);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
   ObjectSetString(0,  n, OBJPROP_TEXT, txt);
}

void Box(string n, datetime t1, double top, datetime t2, double bot, color c)
{
   if(ObjectFind(0, n) < 0)
      ObjectCreate(0, n, OBJ_RECTANGLE, 0, t1, top, t2, bot);
   else
   {
      ObjectMove(0, n, 0, t1, top);
      ObjectMove(0, n, 1, t2, bot);
   }
   ObjectSetInteger(0, n, OBJPROP_COLOR, c);
   ObjectSetInteger(0, n, OBJPROP_FILL, true);
   ObjectSetInteger(0, n, OBJPROP_BACK, true);
   ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
}

void Draw()
{
   int ps = PeriodSeconds();
   if(ArraySize(eng.r) <= 0) return;
   datetime tNow = eng.r[0].time;

   // 1. Draw Liquidity Pools
   if(InpShowPools)
   {
      int poolCount = ArraySize(eng.liq.pools);
      for(int i = 0; i < poolCount; i++)
      {
         ELPool pl = eng.liq.pools[i];
         Line("EL_P_" + IntegerToString(i), pl.t, pl.price, tNow + ps * 10, pl.price,
              pl.isHigh ? clrTomato : clrDeepSkyBlue, STYLE_DOT, true, pl.tag);
      }
      // Delete any leftover pool lines from previous higher count
      for(int i = poolCount; i < poolCount + 20; i++)
      {
         string oldName = "EL_P_" + IntegerToString(i);
         if(ObjectFind(0, oldName) >= 0) ObjectDelete(0, oldName);
         else break;
      }
   }
   else
   {
      ObjectsDeleteAll(0, "EL_P_");
   }

   // 2. Draw Order Block & FVG Zones
   if(InpShowZones && eng.sig.valid)
   {
      if(eng.zn.ob.valid)
         Box("EL_OB", eng.zn.ob.t, eng.zn.ob.top, tNow + ps * 20, eng.zn.ob.bottom, clrDarkSlateGray);
      else
         ObjectDelete(0, "EL_OB");

      if(eng.zn.fvg.valid)
         Box("EL_FVG", eng.zn.fvg.t, eng.zn.fvg.top, tNow + ps * 20, eng.zn.fvg.bottom, clrDarkOliveGreen);
      else
         ObjectDelete(0, "EL_FVG");
   }
   else
   {
      ObjectDelete(0, "EL_OB");
      ObjectDelete(0, "EL_FVG");
   }

   // 3. Draw Active Trade Plan & Arrows
   if(eng.sig.valid && eng.sig.score >= eng.p.minScore)
   {
      ELSignal s = eng.sig;
      Line("EL_ENTRY", tNow, s.entry, tNow + ps * 15, s.entry, clrGold, STYLE_SOLID, false, "Entry");
      Line("EL_SL",    tNow, s.sl,    tNow + ps * 15, s.sl,    clrRed,  STYLE_SOLID, false, "SL");
      Line("EL_TP",    tNow, s.tp,    tNow + ps * 15, s.tp,    clrLime, STYLE_SOLID, false, "TP");

      string n = "ELS_" + TimeToString(s.sweepTime, TIME_DATE | TIME_MINUTES);
      if(ObjectFind(0, n) < 0)
      {
         ObjectCreate(0, n, OBJ_ARROW, 0, s.t, s.entry);
         ObjectSetInteger(0, n, OBJPROP_ARROWCODE, s.dir == EL_BUY ? 233 : 234);
         ObjectSetInteger(0, n, OBJPROP_COLOR, s.dir == EL_BUY ? clrLime : clrRed);
         ObjectSetInteger(0, n, OBJPROP_WIDTH, 3);
         ObjectSetString(0,  n, OBJPROP_TEXT, s.reason + " | " + IntegerToString(s.score));
      }
      if(InpAlerts && s.sweepTime != lastAlert)
      {
         lastAlert = s.sweepTime;
         Alert(_Symbol, " ", (s.dir == EL_BUY ? "BUY" : "SELL"),
               " score ", s.score,
               " entry ", DoubleToString(s.entry, _Digits),
               " SL ", DoubleToString(s.sl, _Digits),
               " TP ", DoubleToString(s.tp, _Digits));
      }
   }
   else
   {
      ObjectDelete(0, "EL_ENTRY");
      ObjectDelete(0, "EL_SL");
      ObjectDelete(0, "EL_TP");
   }

   ChartRedraw(0);
}

int OnCalculate(const int rates_total,const int prev_calculated,const datetime &time[],
                const double &open[],const double &high[],const double &low[],const double &close[],
                const long &tick_volume[],const long &volume[],const int &spread[])
{
   if(rates_total < 100) return 0;
   datetime cur = time[rates_total - 1];
   if(cur == lastBar) return rates_total;
   lastBar = cur;

   if(eng.Update()) Draw();
   return rates_total;
}

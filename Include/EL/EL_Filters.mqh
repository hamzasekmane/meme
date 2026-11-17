#ifndef EL_FILTERS_MQH
#define EL_FILTERS_MQH
#include <EL/EL_Config.mqh>

bool EL_InKillzone(datetime t,const ELParams &p)
{
   if(!p.useKillzone) return true;
   MqlDateTime m; TimeToStruct(t,m);
   int h=m.hour;
   return (h>=p.kz1Start && h<p.kz1End) || (h>=p.kz2Start && h<p.kz2End);
}

bool EL_SpreadOk(string sym,int maxPts)
{
   return (int)SymbolInfoInteger(sym,SYMBOL_SPREAD)<=maxPts;
}

// Manual news blackout list: "YYYY.MM.DD HH:MM;YYYY.MM.DD HH:MM" in server time.
bool EL_NewsBlocked(datetime t,const ELParams &p)
{
   if(p.newsList=="") return false;
   string parts[];
   int n=StringSplit(p.newsList,';',parts);
   for(int i=0;i<n;i++)
   {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]);
      datetime nt=StringToTime(parts[i]);
      if(nt==0) continue;
      if(MathAbs((long)(t-nt))<=(long)p.newsMin*60) return true;
   }
   return false;
}
#endif

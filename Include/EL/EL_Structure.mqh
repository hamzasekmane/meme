#ifndef EL_STRUCTURE_MQH
#define EL_STRUCTURE_MQH
#include <EL/EL_Types.mqh>

// CHoCH / MSS after the sweep: close beyond the last opposite swing that existed before the sweep.
class CELStructure
{
public:
   ELBreak brk;

   void Detect(const MqlRates &r[],const ELSwing &hi[],const ELSwing &lo[],const ELSweep &sw)
   {
      brk.found=false; brk.bar=-1; brk.level=0;
      if(!sw.found) return;
      double lvl=0; bool ok=false;
      if(sw.dir==EL_SELL)
      {
         for(int i=0;i<ArraySize(lo);i++) if(lo[i].bar>sw.bar){ lvl=lo[i].p; ok=true; break; }
         if(!ok) return;
         for(int b=sw.bar-1;b>=1;b--) if(r[b].close<lvl){ brk.found=true; brk.bar=b; brk.level=lvl; return; }
      }
      else
      {
         for(int i=0;i<ArraySize(hi);i++) if(hi[i].bar>sw.bar){ lvl=hi[i].p; ok=true; break; }
         if(!ok) return;
         for(int b=sw.bar-1;b>=1;b--) if(r[b].close>lvl){ brk.found=true; brk.bar=b; brk.level=lvl; return; }
      }
   }
};
#endif

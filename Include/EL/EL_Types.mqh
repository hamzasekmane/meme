#ifndef EL_TYPES_MQH
#define EL_TYPES_MQH
// Shared data structures. Series indexing everywhere: 0 = forming bar, 1 = last closed bar.
enum ENUM_EL_DIR { EL_NONE=0, EL_BUY=1, EL_SELL=-1 };
enum ENUM_EL_ENTRY_KIND
{
   EL_ENTRY_ANALYTICAL=0,
   EL_ENTRY_MARKET,
   EL_ENTRY_BUY_LIMIT,
   EL_ENTRY_SELL_LIMIT,
   EL_ENTRY_BUY_STOP,
   EL_ENTRY_SELL_STOP
};
enum ENUM_EL_STATE
{
   EL_STATE_WAIT=0,
   EL_BIAS_CONFIRMED,
   EL_LIQUIDITY_SWEPT,
   EL_STRUCTURE_CONFIRMED,
   EL_DISPLACEMENT_CONFIRMED,
   EL_ZONE_IDENTIFIED,
   EL_ENTRY_VALIDATED,
   EL_RISK_VALIDATED,
   EL_EXECUTION_READY,
   EL_INVALIDATED,
   EL_EXPIRED
};

struct ELSwing  { int bar; datetime t; double p; bool isHigh; };
struct ELPool   { double price; datetime t; datetime available; bool isHigh; string tag; };
struct ELSweep  { bool found; int dir; ELPool pool; int bar; double extreme; };
struct ELBreak  { bool found; int bar; double level; };
struct ELZone   { bool valid; double top; double bottom; datetime t; int bar; int kind; }; // kind 0=OB 1=FVG
struct ELSignal
{
   // valid means a structurally-derived analytical plan exists; it does NOT mean executable.
   bool valid;
   int dir;
   double entry;
   double sl;
   double tp;
   int score;
   datetime t;                 // last closed setup candle time
   datetime sweepTime;
   datetime expiresAt;
   ENUM_EL_ENTRY_KIND entryKind;
   int state;
   bool biasConfirmed;
   bool liquiditySwept;
   bool structureConfirmed;
   bool displacementConfirmed;
   bool zoneIdentified;
   bool entryValidated;
   bool riskValidated;
   bool executionReady;
   bool invalidated;
   bool expired;
   string reason;
};
#endif

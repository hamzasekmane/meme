#ifndef EL_TYPES_MQH
#define EL_TYPES_MQH
// Shared data structures. Series indexing everywhere: 0 = forming bar, 1 = last closed bar.
enum ENUM_EL_DIR { EL_NONE=0, EL_BUY=1, EL_SELL=-1 };

struct ELSwing  { int bar; datetime t; double p; bool isHigh; };
struct ELPool   { double price; datetime t; bool isHigh; string tag; };
struct ELSweep  { bool found; int dir; ELPool pool; int bar; double extreme; };
struct ELBreak  { bool found; int bar; double level; };
struct ELZone   { bool valid; double top; double bottom; datetime t; int bar; int kind; }; // kind 0=OB 1=FVG
struct ELSignal { bool valid; int dir; double entry; double sl; double tp; int score; datetime t; datetime sweepTime; string reason; };
#endif

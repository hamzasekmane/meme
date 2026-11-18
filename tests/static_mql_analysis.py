#!/usr/bin/env python3
"""Lightweight static checks for this MQL5 repository (not a MetaEditor compiler)."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = list((ROOT / "Include/EL").glob("*.mqh"))
SOURCES += list((ROOT / "Experts").glob("*.mq5"))
SOURCES += list((ROOT / "Indicators").glob("*.mq5"))
errors = []


def check(condition, message):
    if not condition:
        errors.append(message)


def strip_comments_and_strings(text):
    # Remove block/line comments and string contents while preserving delimiters.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


for path in SOURCES:
    text = path.read_text()
    if path.suffix == ".mqh":
        guard = re.search(r"^#ifndef\s+(\w+)\s*\n#define\s+\1\b", text, re.M)
        check(guard is not None and text.rstrip().endswith("#endif"),
              f"{path.relative_to(ROOT)}: missing/invalid include guard")

    for include in re.findall(r"^\s*#include\s*<EL/([^>]+)>", text, re.M):
        check((ROOT / "Include/EL" / include).exists(),
              f"{path.relative_to(ROOT)}: unresolved internal include EL/{include}")

    clean = strip_comments_and_strings(text)
    for opening, closing in (("(", ")"), ("{", "}"), ("[", "]")):
        depth = 0
        for char in clean:
            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
            if depth < 0:
                errors.append(f"{path.relative_to(ROOT)}: unmatched {closing}")
                break
        check(depth == 0, f"{path.relative_to(ROOT)}: unbalanced {opening}{closing}")

signal = (ROOT / "Include/EL/EL_Signal.mqh").read_text()
engine = (ROOT / "Include/EL/EL_Engine.mqh").read_text()
trade = (ROOT / "Include/EL/EL_Trade.mqh").read_text()
ea = (ROOT / "Experts/EL_EA.mq5").read_text()
indicator = (ROOT / "Indicators/EL_Indicator.mq5").read_text()

check("r[0].close" not in signal, "signal calculations reference forming-bar close")
check("EL_ValidateLimitPlan" in engine and "EL_ValidateLimitPlan" in trade,
      "plan validation is not shared/repeated at send time")
check("if(!s.executionReady)" in ea, "EA lacks executionReady gate")
check("if(s.executionReady)" in indicator, "indicator alerts lack executionReady gate")
check("if(tf!=PERIOD_M15)" in engine, "non-M15 execution guard is missing")
check("ORDER_TIME_GTC" not in trade, "trade code may leave stale GTC pending orders")
check("if(tp<=0) return;" in signal, "signal can proceed without an external target")
check("EL_TargetUntouchedSinceAvailable" in signal, "consumed target check is missing")

# Every ELParams field must be initialized by the shared input builder.
config = (ROOT / "Include/EL/EL_Config.mqh").read_text()
inputs = (ROOT / "Include/EL/EL_Inputs.mqh").read_text()
body = re.search(r"struct\s+ELParams\s*\{(.*?)\};", config, re.S).group(1)
body = re.sub(r"//[^\n]*", "", body)
fields = []
for declaration in re.findall(r"(?:int|double|bool|string)\s+([^;]+);", body):
    fields.extend(re.findall(r"\b(\w+)\b", declaration))
for field in fields:
    check(re.search(rf"\bp\.{re.escape(field)}\s*=", inputs) is not None,
          f"ELParams.{field} is not initialized in EL_BuildParams")

if errors:
    print("MQL static analysis: FAIL")
    print("\n".join(f"- {error}" for error in errors))
    sys.exit(1)

print(f"MQL static analysis: PASS ({len(SOURCES)} source files; include, guard, delimiter, and execution-contract checks)")
print("Note: this is static source analysis, not MQL5 compilation or MT5 runtime validation.")

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "Vietnam_Banking_Liquidity_Master.xlsx"
OUT = ROOT / "data" / "casa_actual.csv"

if not MASTER.exists():
    raise SystemExit(0)

try:
    df = pd.read_excel(MASTER, sheet_name="CASA_INPUT", header=2)
except Exception as exc:
    print("CASA_INPUT unavailable:", exc)
    raise SystemExit(0)

rename = {}
for c in df.columns:
    k = str(c).strip().lower()
    if k == "ticker": rename[c] = "Ticker"
    elif k == "period": rename[c] = "Period"
    elif k in {"as of date","asofdate","date"}: rename[c] = "AsOfDate"
    elif k == "casa": rename[c] = "CASA"
    elif "source url" in k: rename[c] = "SourceURL"
    elif "source name" in k: rename[c] = "SourceName"
    elif "data type" in k: rename[c] = "DataType"

df = df.rename(columns=rename)
required = ["Ticker","CASA","SourceURL","SourceName","DataType"]
if not all(c in df.columns for c in required):
    print("CASA_INPUT missing required columns.")
    raise SystemExit(0)

for c in ["Period","AsOfDate"]:
    if c not in df.columns:
        df[c] = None

x = df[["Ticker","Period","AsOfDate","CASA","SourceURL","SourceName","DataType"]].copy()
x["Ticker"] = x["Ticker"].astype(str).str.upper().str.strip()
x["CASA"] = pd.to_numeric(x["CASA"], errors="coerce")
x.loc[(x["CASA"] > 1.5) & (x["CASA"] <= 100), "CASA"] = x.loc[(x["CASA"] > 1.5) & (x["CASA"] <= 100), "CASA"] / 100.0
x = x[(x["CASA"] >= 0) & (x["CASA"] <= 1)]
x = x[x["DataType"].astype(str).str.upper().isin(["ACTUAL","ACTUAL_PUBLIC_SOURCE"])]
x = x[x["SourceURL"].astype(str).str.startswith("http")]
x = x[x["Ticker"].str.len().between(3,4)]

if x.empty:
    print("CASA_INPUT has no validated ACTUAL rows; existing casa_actual.csv preserved.")
    raise SystemExit(0)

OUT.parent.mkdir(exist_ok=True)
x.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"Exported {len(x)} ACTUAL CASA rows to {OUT}")

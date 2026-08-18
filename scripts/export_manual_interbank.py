from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "Vietnam_Banking_Liquidity_Master.xlsx"
OUT = ROOT / "data" / "interbank_manual.csv"

if not MASTER.exists():
    raise SystemExit(0)
try:
    df = pd.read_excel(MASTER, sheet_name="INTERBANK_INPUT", header=2)
except Exception:
    raise SystemExit(0)

mapping = {}
for c in df.columns:
    k = str(c).strip().lower()
    if k.startswith("date"): mapping[c] = "date"
    elif "overnight" in k: mapping[c] = "overnight_rate"
    elif "source url" in k: mapping[c] = "source_url"
    elif "source name" in k: mapping[c] = "source_name"
    elif "data type" in k: mapping[c] = "data_type"
df = df.rename(columns=mapping)
required = ["date","overnight_rate","source_url","source_name","data_type"]
if not all(c in df.columns for c in required):
    raise SystemExit(0)
x = df[required].copy()
x["date"] = pd.to_datetime(x.date, errors="coerce")
x["overnight_rate"] = pd.to_numeric(x.overnight_rate, errors="coerce")
x = x.dropna(subset=["date","overnight_rate"])
x = x[x.data_type.astype(str).str.upper().eq("ACTUAL")]
x = x[x.source_url.astype(str).str.startswith("http")]
if len(x) < 10:
    print(f"Manual interbank: {len(x)} valid rows; existing file is not overwritten.")
    raise SystemExit(0)
OUT.parent.mkdir(exist_ok=True)
x["date"] = x.date.dt.strftime("%Y-%m-%d")
x.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"Exported {len(x)} manual ACTUAL interbank observations.")

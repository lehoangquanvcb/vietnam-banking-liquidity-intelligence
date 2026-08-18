
from pathlib import Path
from datetime import datetime
import pandas as pd, numpy as np, json, re, time, sys

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; RAW=DATA/"raw_bank"
DATA.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

try:
    from vnstock_data import Fundamental, Macro
except Exception as e:
    print("ERROR: vnstock_data unavailable in this Python:",repr(e)); sys.exit(2)

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")
def norm(x): return re.sub(r"[^a-z0-9]+"," ",str(x).lower()).strip()

def latest_numeric_from_tidy(df, id_terms=(), name_terms=()):
    if df is None or len(df)==0: return None
    x=df.copy()
    x.columns=[str(c) for c in x.columns]
    # Semantic-ID first (stable Vnstock v3.2.8+), then name aliases.
    masks=[]
    if "id" in x.columns:
        ids=x["id"].astype(str).str.upper()
        for t in id_terms:
            masks.append(ids.str.contains(str(t).upper(),regex=False,na=False))
    if "name" in x.columns:
        names=x["name"].astype(str).map(norm)
        for t in name_terms:
            masks.append(names.str.contains(norm(t),regex=False,na=False))
    for m in masks:
        if not m.any(): continue
        # Long/tidy data may contain period columns or a value column. Prefer rightmost numeric.
        for c in reversed(x.columns):
            if c in ["id","name","unit","order","level"]: continue
            v=pd.to_numeric(x.loc[m,c],errors="coerce").dropna()
            if len(v): return float(v.iloc[0])
    return None

def latest_from_wide(df, terms=()):
    if df is None or len(df)==0: return None
    x=df.copy()
    x.columns=[" | ".join(map(str,c)) if isinstance(c,tuple) else str(c) for c in x.columns]
    for c in x.columns:
        nc=norm(c)
        if any(norm(t) in nc for t in terms):
            v=pd.to_numeric(x[c],errors="coerce").dropna()
            if len(v): return float(v.iloc[-1])
    # financial_health may have metrics as rows/first column
    for _,r in x.iterrows():
        lead=" | ".join(norm(v) for v in r.values[:min(4,len(r))])
        if any(norm(t) in lead for t in terms):
            for v0 in reversed(r.values):
                v=pd.to_numeric(pd.Series([v0]),errors="coerce").dropna()
                if len(v): return float(v.iloc[0])
    return None

def scale_ratio(v):
    if v is None or pd.isna(v): return np.nan
    v=float(v)
    return v/100 if abs(v)>2 else v

def fetch_bank(ticker):
    fun=Fundamental()
    eq=fun.equity(ticker)

    # Current documented v3.2.8+ interfaces. Force Bank taxonomy.
    try: bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)
    except Exception: bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
    try: ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)
    except Exception: ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
    try: health=eq.financial_health(scorecard="bank",lang="en",limit=4)
    except Exception: health=pd.DataFrame()

    # Save raw schemas for audit/debug. These are ACTUAL source tables.
    for name,df in [("balance_sheet",bs),("ratio",ratio),("financial_health",health)]:
        if df is not None and len(df):
            df.to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")

    # Prefer financial-health/ratio direct metrics; use Semantic ID / names, then compute.
    ldr=latest_from_wide(health,["ldr","loan to deposit"])
    if ldr is None: ldr=latest_numeric_from_tidy(ratio,["LDR"],["ldr","loan to deposit"])
    casa=latest_from_wide(health,["casa","current account saving"])
    if casa is None: casa=latest_numeric_from_tidy(ratio,["CASA"],["casa","current account saving"])
    nim=latest_from_wide(health,["nim","net interest margin"])
    if nim is None: nim=latest_numeric_from_tidy(ratio,["NIM"],["nim","net interest margin"])

    loans=latest_numeric_from_tidy(
        bs,
        ["CUSTOMER_LOANS","LOANS_TO_CUSTOMERS"],
        ["loans to customers","customer loans","cho vay khách hàng"]
    )
    deposits=latest_numeric_from_tidy(
        bs,
        ["CUSTOMER_DEPOSITS","DEPOSITS_FROM_CUSTOMERS"],
        ["customer deposits","deposits from customers","tiền gửi khách hàng"]
    )
    assets=latest_numeric_from_tidy(bs,["TOTAL_ASSETS"],["total assets","tổng tài sản"])
    interbank=latest_numeric_from_tidy(
        bs,
        ["CREDIT_INSTITUTIONS","INTERBANK"],
        ["credit institutions","interbank","tổ chức tín dụng"]
    )

    if (ldr is None or pd.isna(ldr)) and loans is not None and deposits not in (None,0):
        ldr=loans/deposits
    ibdep=interbank/assets if interbank is not None and assets not in (None,0) else np.nan
    gap=(loans-deposits)/deposits if loans is not None and deposits not in (None,0) else np.nan

    vals=[scale_ratio(ldr),scale_ratio(casa),scale_ratio(ibdep),scale_ratio(gap),scale_ratio(nim)]
    coverage=float(pd.Series(vals).notna().mean())
    return [ticker, vals[0],vals[1],vals[2],vals[3],vals[4],coverage,
            "ACTUAL","BRONZE","OK" if coverage>=.60 else "PARTIAL",now()]

status=[]; rows=[]
for t in BANKS:
    try:
        rows.append(fetch_bank(t)); status.append(["bank:"+t,"OK","",now()])
    except Exception as e:
        status.append(["bank:"+t,"ERROR",str(e)[:350],now()])
    time.sleep(.25)

cols=["Ticker","LDR","CASA","InterbankDep","CreditDepositGap","NIM","MetricCoverage","Data Type","Source Mode","ParseStatus","Retrieved At"]
pd.DataFrame(rows,columns=cols).to_csv(DATA/"bank_actuals_bronze.csv",index=False,encoding="utf-8-sig")

m=Macro()
def save(df,name):
    if df is None or len(df)==0: return False
    x=df.copy(); x["Data Type"]="ACTUAL"; x["Source Mode"]="BRONZE"; x["Retrieved At"]=now()
    x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig"); return True

jobs={
    "omo":lambda:m.currency().omo(start="2018-01-01"),
    "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
    # This is a banking-rate proxy, NOT labelled interbank.
    "funding_rate_proxy":lambda:m.currency().interest_rate(period="day",length=3650),
    "m2":lambda:m.economy().money_supply(period="month",length=180),
    "credit":lambda:m.economy().credit(period="month",length=180),
    "cpi":lambda:m.economy().cpi(period="month",length=180),
    "budget":lambda:m.economy().state_budget(period="month",length=180),
}
for name,fn in jobs.items():
    try:
        status.append([name,"OK" if save(fn(),name) else "EMPTY","",now()])
    except Exception as e:
        status.append([name,"ERROR",str(e)[:350],now()])
    time.sleep(.25)

# True interbank only. Never substitute retail deposit/lending rates.
ib_errors=[]; ib_ok=False
for label,call in [
    ("interbank_rate length",lambda:m.currency().interbank_rate(period="day",length=3650)),
    ("interbank_rate start",lambda:m.currency().interbank_rate(start="2018-01-01",period="day")),
]:
    try:
        if save(call(),"interbank"):
            status.append(["interbank","OK",label,now()]); ib_ok=True; break
    except Exception as e:
        ib_errors.append(f"{label}: {str(e)[:180]}")
if not ib_ok:
    old=DATA/"interbank_bronze.csv"
    manual=DATA/"interbank_manual.csv"
    if old.exists() and old.stat().st_size>100:
        status.append(["interbank","DEGRADED","Live failed; retained prior ACTUAL file. "+" | ".join(ib_errors),now()])
    elif manual.exists() and manual.stat().st_size>50:
        status.append(["interbank","MANUAL_ACTUAL","Using data/interbank_manual.csv. "+" | ".join(ib_errors),now()])
    else:
        status.append(["interbank","ERROR","No true interbank source. "+" | ".join(ib_errors),now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(DATA/"refresh_status.csv",index=False,encoding="utf-8-sig")
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

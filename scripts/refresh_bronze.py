
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import json,re,time,sys

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

try:
    from vnstock_data import Fundamental, Macro
except Exception as e:
    print("ERROR: Không import được vnstock_data trong Python Bronze.")
    print("Hãy dùng đúng interpreter/venv đã cài Vnstock Sponsor.")
    print(repr(e))
    sys.exit(2)

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df,keys):
    if df is None or len(df)==0:
        return None
    x=df.copy()
    # Flatten MultiIndex / tuple columns often returned by financial endpoints.
    x.columns=[" | ".join(map(str,c)) if isinstance(c,tuple) else str(c) for c in x.columns]

    # 1. Long-schema label columns.
    candidate_label_cols=[c for c in x.columns if norm(c) in {"id","name","item","indicator","metric","code"}]
    candidate_label_cols += [c for c in x.columns[:min(4,len(x.columns))] if c not in candidate_label_cols]
    for lc in candidate_label_cols:
        labels=x[lc].astype(str).map(norm)
        for k in keys:
            nk=norm(k)
            mask=labels.str.contains(nk,regex=False,na=False)
            if mask.any():
                # Search all other columns and prefer the rightmost/latest numeric value.
                for c in reversed(x.columns):
                    if c==lc:
                        continue
                    vals=pd.to_numeric(x.loc[mask,c],errors="coerce").dropna()
                    if len(vals):
                        return float(vals.iloc[0])

    # 2. Wide-schema metric names in column headers.
    for c in x.columns:
        nc=norm(c)
        if any(norm(k) in nc for k in keys):
            vals=pd.to_numeric(x[c],errors="coerce").dropna()
            if len(vals):
                return float(vals.iloc[0])

    # 3. Search text across cells for semi-structured tables.
    for idx,row in x.iterrows():
        row_text=" | ".join(norm(v) for v in row.values[:min(5,len(row))])
        if any(norm(k) in row_text for k in keys):
            for v in reversed(row.values):
                n=pd.to_numeric(pd.Series([v]),errors="coerce").dropna()
                if len(n):
                    return float(n.iloc[0])
    return None

def period_of(*dfs):
    for df in dfs:
        if df is None or len(df)==0:
            continue
        for c in ["period","report_period","report_time","year","quarter","time"]:
            if c in df.columns and len(df[c].dropna()):
                return str(df[c].dropna().iloc[0])
    return ""

def fetch_bank(symbol):
    f=Fundamental()
    eq=f.equity(symbol)
    try:
        bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try: bs=eq.balance_sheet(period="Q")
        except Exception: bs=eq.balance_sheet()
    try:
        ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try: ratio=eq.financial_ratio()
        except Exception:
            try: ratio=eq.ratio(period="Q")
            except Exception: ratio=pd.DataFrame()

    loans=find_metric(bs,["customer loans","loans to customers","cho vay khách hàng"])
    dep=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
    assets=find_metric(bs,["total assets","tổng tài sản"])
    ib=find_metric(bs,["interbank borrowing","borrowings from other credit institutions","tiền gửi và vay các tổ chức tín dụng"])
    ldr=find_metric(ratio,["ldr","loan to deposit"])
    casa=find_metric(ratio,["casa","current account saving account"])
    nim=find_metric(ratio,["nim","net interest margin"])
    if ldr is None and loans is not None and dep not in (None,0):
        ldr=loans/dep
    ibdep=ib/assets if ib is not None and assets not in (None,0) else np.nan
    gap=(loans-dep)/dep if loans is not None and dep not in (None,0) else np.nan
    return [symbol,period_of(bs,ratio),ldr,casa,ibdep,gap,nim,"ACTUAL","BRONZE",now()]

def save_actual(df,name):
    if df is None or len(df)==0:
        return False
    x=df.copy()
    x["Data Type"]="ACTUAL"
    x["Source Mode"]="BRONZE"
    x["Retrieved At"]=now()
    x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig")
    return True

status=[]
rows=[]
for s in BANKS:
    try:
        rows.append(fetch_bank(s))
        status.append(["bank:"+s,"OK","",now()])
    except Exception as e:
        status.append(["bank:"+s,"ERROR",str(e)[:300],now()])
    time.sleep(.25)

bank_cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode","Retrieved At"]
pd.DataFrame(rows,columns=bank_cols).to_csv(DATA/"bank_actuals_bronze.csv",index=False,encoding="utf-8-sig")

m=Macro()

# Daily / event series
jobs_daily = {
    "omo": lambda: m.currency().omo(start="2018-01-01"),
    "fx": lambda: m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate": lambda: m.currency().policy_rate(start="2018-01-01"),
}

# Monthly: use length to avoid date-parser mismatch seen in live Bronze runtime.
jobs_monthly = {
    "m2": lambda: m.economy().money_supply(period="month",length=180),
    "credit": lambda: m.economy().credit(period="month",length=180),
    "cpi": lambda: m.economy().cpi(period="month",length=180),
    "budget": lambda: m.economy().state_budget(period="month",length=180),
}

for name,fn in {**jobs_daily,**jobs_monthly}.items():
    try:
        ok=save_actual(fn(),name)
        status.append([name,"OK" if ok else "EMPTY","",now()])
    except Exception as e:
        status.append([name,"ERROR",str(e)[:300],now()])
    time.sleep(.25)

# Interbank: robust fallback chain based on current Vnstock Macro API.
# 1) dedicated interbank_rate
# 2) currency.interest_rate (official broader rate endpoint)
# 3) legacy Macro.interest_rate for backward compatibility
interbank_ok=False
interbank_errors=[]
interbank_calls=[
    ("currency.interbank_rate(length)", lambda: m.currency().interbank_rate(period="day",length=3650)),
    ("currency.interbank_rate(start)", lambda: m.currency().interbank_rate(start="2018-01-01",period="day")),
    ("currency.interest_rate(length)", lambda: m.currency().interest_rate(length=3650)),
    ("currency.interest_rate(start)", lambda: m.currency().interest_rate(start="2018-01-01",period="day")),
    ("legacy interest_rate", lambda: m.interest_rate(length=3650)),
]
for label,call in interbank_calls:
    try:
        df=call()
        if save_actual(df,"interbank"):
            interbank_ok=True
            status.append(["interbank","OK",f"Source fallback used: {label}",now()])
            break
    except Exception as e:
        interbank_errors.append(f"{label}: {str(e)[:180]}")

if not interbank_ok:
    old=DATA/"interbank_bronze.csv"
    if old.exists() and old.stat().st_size>100:
        status.append(["interbank","DEGRADED","Live refresh failed; retained prior ACTUAL file. "+" | ".join(interbank_errors),now()])
    else:
        status.append(["interbank","ERROR"," | ".join(interbank_errors),now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(
    DATA/"refresh_status.csv",index=False,encoding="utf-8-sig")
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

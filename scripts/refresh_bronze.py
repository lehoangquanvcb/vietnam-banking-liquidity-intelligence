
from pathlib import Path
from datetime import datetime
import pandas as pd, numpy as np, json, re, time, sys

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; RAW=DATA/"raw_bank"
DATA.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
BANKS=json.loads((ROOT/"config/banks.json").read_text(encoding="utf-8"))

try:
    from vnstock_data import Fundamental, Macro
except Exception as e:
    print("ERROR: vnstock_data unavailable:",repr(e)); sys.exit(2)

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")
def norm(x): return re.sub(r"[^a-z0-9]+"," ",str(x).lower()).strip()
def scale(v):
    if v is None or pd.isna(v): return np.nan
    v=float(v)
    return v/100 if abs(v)>2 else v

def flatten(df):
    x=df.copy()
    x.columns=[" | ".join(map(str,c)) if isinstance(c,tuple) else str(c) for c in x.columns]
    return x

def find_metric(df, terms=()):
    if df is None or len(df)==0:return None
    x=flatten(df)
    # label columns first
    label_cols=[c for c in x.columns if norm(c) in {"id","code","metric","indicator","name","item","label"}]
    label_cols += [c for c in x.columns[:min(4,len(x.columns))] if c not in label_cols]
    for lc in label_cols:
        labels=x[lc].astype(str).map(norm)
        for term in terms:
            m=labels.str.contains(norm(term),regex=False,na=False)
            if m.any():
                for c in reversed(x.columns):
                    if c==lc: continue
                    v=pd.to_numeric(x.loc[m,c],errors="coerce").dropna()
                    if len(v): return float(v.iloc[0])
    # wide columns
    for c in x.columns:
        if any(norm(term) in norm(c) for term in terms):
            v=pd.to_numeric(x[c],errors="coerce").dropna()
            if len(v): return float(v.iloc[-1])
    # row scan
    for _,row in x.iterrows():
        lead=" | ".join(norm(v) for v in row.values[:min(6,len(row))])
        if any(norm(term) in lead for term in terms):
            for v0 in reversed(row.values):
                v=pd.to_numeric(pd.Series([v0]),errors="coerce").dropna()
                if len(v): return float(v.iloc[0])
    return None

def fetch_bank(ticker):
    fun=Fundamental()
    try:eq=fun.equity(ticker)
    except Exception:eq=fun.equity(symbol=ticker)

    calls=[]
    try:calls.append(("balance_sheet",eq.balance_sheet(period="quarter",lang="en",scorecard="banking",dropna=False)))
    except Exception:
        try:calls.append(("balance_sheet",eq.balance_sheet(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)))
        except Exception:calls.append(("balance_sheet",eq.balance_sheet(period="quarter")))
    try:calls.append(("ratio",eq.ratio(period="quarter",lang="en",scorecard="banking",dropna=False)))
    except Exception:
        try:calls.append(("ratio",eq.ratio(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)))
        except Exception:
            try:calls.append(("ratio",eq.ratio(period="quarter")))
            except Exception:calls.append(("ratio",pd.DataFrame()))
    try:calls.append(("financial_health",eq.financial_health(scorecard="banking",lang="en",limit=8)))
    except Exception:calls.append(("financial_health",pd.DataFrame()))

    tables={k:v for k,v in calls}
    for name,df in calls:
        if df is not None and len(df):
            df.to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")

    bs=tables["balance_sheet"]; ratio=tables["ratio"]; health=tables["financial_health"]
    ldr=find_metric(health,["ldr","loan to deposit","loans/deposits","customer loan/customer deposit"]) or find_metric(ratio,["ldr","loan to deposit","loans/deposits"])
    casa=find_metric(health,["casa","current account saving","current account savings account","demand deposit"]) or find_metric(ratio,["casa","current account saving","demand deposit"])
    nim=find_metric(health,["nim","net interest margin","interest margin"]) or find_metric(ratio,["nim","net interest margin","interest margin"])

    loans=find_metric(bs,["customer loans","loans to customers","customer loan","cho vay khách hàng","loans and advances to customers"])
    deposits=find_metric(bs,["customer deposits","deposits from customers","customer deposit","tiền gửi khách hàng","deposits of customers"])
    assets=find_metric(bs,["total assets","tổng tài sản"])
    ib=find_metric(bs,["interbank","due from credit institutions","deposits at credit institutions","credit institutions","tổ chức tín dụng"])

    if (ldr is None or pd.isna(ldr)) and loans is not None and deposits not in (None,0):ldr=loans/deposits
    ibdep=ib/assets if ib is not None and assets not in (None,0) else np.nan
    gap=(loans-deposits)/deposits if loans is not None and deposits not in (None,0) else np.nan

    vals=[scale(ldr),scale(casa),scale(ibdep),scale(gap),scale(nim)]
    coverage=float(pd.Series(vals).notna().mean())
    return [ticker,*vals,coverage,"ACTUAL","BRONZE","OK" if coverage>=.60 else "PARTIAL",now()]

status=[];rows=[]
for t in BANKS:
    try:
        rows.append(fetch_bank(t));status.append(["bank:"+t,"OK","",now()])
    except Exception as e:
        status.append(["bank:"+t,"ERROR",str(e)[:400],now()])
    time.sleep(.25)

pd.DataFrame(rows,columns=[
    "Ticker","LDR","CASA","InterbankDep","CreditDepositGap","NIM",
    "MetricCoverage","Data Type","Source Mode","ParseStatus","Retrieved At"
]).to_csv(DATA/"bank_actuals_bronze.csv",index=False,encoding="utf-8-sig")

m=Macro()
def save(df,name):
    if df is None or len(df)==0:return False
    x=df.copy();x["Data Type"]="ACTUAL";x["Source Mode"]="BRONZE";x["Retrieved At"]=now()
    x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig")
    return True

jobs={
    "omo":lambda:m.currency().omo(start="2018-01-01"),
    "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
    "funding_rate_proxy":lambda:m.currency().interest_rate(period="day",length=3650),
    "m2":lambda:m.economy().money_supply(period="month",length=180),
    "credit":lambda:m.economy().credit(period="month",length=180),
    "cpi":lambda:m.economy().cpi(period="month",length=180),
    "budget":lambda:m.economy().state_budget(period="month",length=180),
}
for name,fn in jobs.items():
    try:status.append([name,"OK" if save(fn(),name) else "EMPTY","",now()])
    except Exception as e:status.append([name,"ERROR",str(e)[:400],now()])
    time.sleep(.25)

# True interbank only.
errs=[];ib_ok=False
# Probe only signatures documented by the current Unified UI first.
# Vnstock docs define start/end/period for interbank_rate; length is retained only as a compatibility probe.
for label,call in [
    ("currency.interbank_rate()",lambda:m.currency().interbank_rate()),
    ("currency.interbank_rate(period=day)",lambda:m.currency().interbank_rate(period="day")),
    ("currency.interbank_rate(start,end,day)",lambda:m.currency().interbank_rate(start="2024-01-01",end=pd.Timestamp.today().strftime("%Y-%m-%d"),period="day")),
    ("currency.interbank_rate(start,month)",lambda:m.currency().interbank_rate(start="2018-01",period="month")),
    ("currency.interbank_rate(length) compatibility",lambda:m.currency().interbank_rate(period="day",length=3650)),
]:
    try:
        if save(call(),"interbank"):
            status.append(["interbank","OK",label,now()]);ib_ok=True;break
    except Exception as e:errs.append(f"{label}: {str(e)[:180]}")
if not ib_ok:
    manual=DATA/"interbank_manual.csv";old=DATA/"interbank_bronze.csv"
    if old.exists() and old.stat().st_size>100:
        status.append(["interbank","DEGRADED","Live failed; retained prior Bronze ACTUAL. "+" | ".join(errs),now()])
    elif manual.exists() and manual.stat().st_size>50:
        status.append(["interbank","MANUAL_ACTUAL","Using manual/public ACTUAL. "+" | ".join(errs),now()])
    else:
        status.append(["interbank","ERROR","No true interbank series. "+" | ".join(errs),now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(DATA/"refresh_status.csv",index=False,encoding="utf-8-sig")
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))


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

def find_metric(df, id_terms=(), name_terms=()):
    if df is None or len(df)==0: return None
    x=df.copy()
    x.columns=[" | ".join(map(str,c)) if isinstance(c,tuple) else str(c) for c in x.columns]
    # Stable semantic identifiers first when available.
    for label_col in [c for c in x.columns if norm(c) in {"id","code","metric","indicator","name","item"}]:
        labels=x[label_col].astype(str)
        for term in list(id_terms)+list(name_terms):
            mask=labels.str.contains(str(term),case=False,regex=False,na=False)
            if mask.any():
                for c in reversed(x.columns):
                    if c==label_col: continue
                    vals=pd.to_numeric(x.loc[mask,c],errors="coerce").dropna()
                    if len(vals): return float(vals.iloc[0])
    # Wide schema.
    for c in x.columns:
        if any(norm(term) in norm(c) for term in list(id_terms)+list(name_terms)):
            vals=pd.to_numeric(x[c],errors="coerce").dropna()
            if len(vals): return float(vals.iloc[-1])
    # Semi-structured row labels.
    for _,row in x.iterrows():
        lead=" | ".join(str(v) for v in row.values[:min(5,len(row))])
        if any(norm(term) in norm(lead) for term in list(id_terms)+list(name_terms)):
            for v0 in reversed(row.values):
                vals=pd.to_numeric(pd.Series([v0]),errors="coerce").dropna()
                if len(vals): return float(vals.iloc[0])
    return None

def get_equity(fun,ticker):
    try:return fun.equity(ticker)
    except Exception:return fun.equity(symbol=ticker)

def fetch_bank(ticker):
    fun=Fundamental()
    eq=get_equity(fun,ticker)

    # Current documented calls prefer scorecard='banking'; preserve fallbacks for installed Sponsor versions.
    try: bs=eq.balance_sheet(period="quarter",lang="en",scorecard="banking",dropna=False)
    except Exception:
        try: bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)
        except Exception: bs=eq.balance_sheet(period="quarter")
    try: ratio=eq.ratio(period="quarter",lang="en",scorecard="banking",dropna=False)
    except Exception:
        try: ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)
        except Exception: ratio=eq.ratio(period="quarter")
    try:
        health=eq.financial_health(scorecard="bank",lang="en",limit=4)
    except Exception:
        health=pd.DataFrame()

    for name,df in [("balance_sheet",bs),("ratio",ratio),("financial_health",health)]:
        if df is not None and len(df):
            df.to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")

    ldr=find_metric(health,["LDR"],["loan to deposit","ldr"])
    if ldr is None: ldr=find_metric(ratio,["LDR"],["loan to deposit","ldr"])
    casa=find_metric(health,["CASA"],["casa","current account saving"])
    if casa is None: casa=find_metric(ratio,["CASA"],["casa","current account saving"])
    nim=find_metric(health,["NIM"],["net interest margin","nim"])
    if nim is None: nim=find_metric(ratio,["NIM"],["net interest margin","nim"])

    loans=find_metric(bs,["CUSTOMER_LOANS","LOANS_TO_CUSTOMERS"],["customer loans","loans to customers","cho vay khách hàng"])
    deposits=find_metric(bs,["CUSTOMER_DEPOSITS","DEPOSITS_FROM_CUSTOMERS"],["customer deposits","deposits from customers","tiền gửi khách hàng"])
    assets=find_metric(bs,["TOTAL_ASSETS"],["total assets","tổng tài sản"])
    interbank=find_metric(bs,["INTERBANK","CREDIT_INSTITUTIONS"],["credit institutions","interbank","tổ chức tín dụng"])

    if (ldr is None or pd.isna(ldr)) and loans is not None and deposits not in (None,0):
        ldr=loans/deposits
    ibdep=interbank/assets if interbank is not None and assets not in (None,0) else np.nan
    gap=(loans-deposits)/deposits if loans is not None and deposits not in (None,0) else np.nan

    vals=[scale(ldr),scale(casa),scale(ibdep),scale(gap),scale(nim)]
    coverage=float(pd.Series(vals).notna().mean())
    return [ticker,*vals,coverage,"ACTUAL","BRONZE","OK" if coverage>=.60 else "PARTIAL",now()]

status=[]; rows=[]
for t in BANKS:
    try:
        rows.append(fetch_bank(t)); status.append(["bank:"+t,"OK","",now()])
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
    # Documented as deposit/lending-rate series, hence stored only as a proxy.
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

# True interbank only: never substitute deposit/lending-rate proxy.
ib_ok=False;errs=[]
for label,call in [
    ("currency.interbank_rate(length)",lambda:m.currency().interbank_rate(period="day",length=3650)),
    ("currency.interbank_rate(start)",lambda:m.currency().interbank_rate(start="2018-01-01",period="day")),
]:
    try:
        if save(call(),"interbank"):
            status.append(["interbank","OK",label,now()]);ib_ok=True;break
    except Exception as e:errs.append(f"{label}: {str(e)[:180]}")
if not ib_ok:
    manual=DATA/"interbank_manual.csv"; old=DATA/"interbank_bronze.csv"
    if old.exists() and old.stat().st_size>100:
        status.append(["interbank","DEGRADED","Live failed; retained prior Bronze ACTUAL. "+" | ".join(errs),now()])
    elif manual.exists() and manual.stat().st_size>50:
        status.append(["interbank","MANUAL_ACTUAL","Using data/interbank_manual.csv. "+" | ".join(errs),now()])
    else:
        status.append(["interbank","ERROR","No true interbank series. "+" | ".join(errs),now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(DATA/"refresh_status.csv",index=False,encoding="utf-8-sig")
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

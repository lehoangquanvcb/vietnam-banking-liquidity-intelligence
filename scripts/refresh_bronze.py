
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
    print("ERROR: Không import được vnstock_data trên máy local/self-hosted runner.")
    print("Hãy cài Sponsor bằng Vnstock Installer chính thức trên máy này trước.")
    print(repr(e))
    sys.exit(2)

def norm(s):return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df,keys):
    if df is None or len(df)==0:return None
    for lc in [c for c in ["id","name"] if c in df.columns]:
        labels=df[lc].astype(str).map(norm)
        for k in keys:
            mask=labels.str.contains(norm(k),regex=False)
            if mask.any():
                for c in reversed(df.columns):
                    if c in ["id","name","unit","period","report_period","order","level"]:continue
                    v=pd.to_numeric(df.loc[mask,c],errors="coerce").dropna()
                    if len(v):return float(v.iloc[0])
    for c in df.columns:
        if any(norm(k) in norm(c) for k in keys):
            v=pd.to_numeric(df[c],errors="coerce").dropna()
            if len(v):return float(v.iloc[0])
    return None

def period_of(*dfs):
    for df in dfs:
        if df is None or len(df)==0:continue
        for c in ["period","report_period","report_time","year","quarter","time"]:
            if c in df.columns and len(df[c].dropna()):
                return str(df[c].dropna().iloc[0])
    return ""

def fetch_bank(symbol):
    f=Fundamental()
    eq=f.equity(symbol)
    try:bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try:bs=eq.balance_sheet(period="Q")
        except Exception:bs=eq.balance_sheet()
    try:ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try:ratio=eq.financial_ratio()
        except Exception:
            try:ratio=eq.ratio(period="Q")
            except Exception:ratio=pd.DataFrame()

    loans=find_metric(bs,["customer loans","loans to customers","cho vay khách hàng"])
    dep=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
    assets=find_metric(bs,["total assets","tổng tài sản"])
    ib=find_metric(bs,["interbank borrowing","borrowings from other credit institutions","tiền gửi và vay các tổ chức tín dụng"])
    ldr=find_metric(ratio,["ldr","loan to deposit"])
    casa=find_metric(ratio,["casa","current account saving account"])
    nim=find_metric(ratio,["nim","net interest margin"])
    if ldr is None and loans is not None and dep not in (None,0):ldr=loans/dep
    ibdep=ib/assets if ib is not None and assets not in (None,0) else np.nan
    gap=(loans-dep)/dep if loans is not None and dep not in (None,0) else np.nan
    return [symbol,period_of(bs,ratio),ldr,casa,ibdep,gap,nim,"ACTUAL","BRONZE",datetime.now().astimezone().isoformat(timespec="seconds")]

rows=[];status=[]
for s in BANKS:
    try:
        rows.append(fetch_bank(s));status.append(["bank:"+s,"OK","",datetime.now().astimezone().isoformat(timespec="seconds")])
    except Exception as e:
        status.append(["bank:"+s,"ERROR",str(e)[:300],datetime.now().astimezone().isoformat(timespec="seconds")])
    time.sleep(.25)

cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode","Retrieved At"]
pd.DataFrame(rows,columns=cols).to_csv(DATA/"bank_actuals_bronze.csv",index=False,encoding="utf-8-sig")

# Macro datasets saved separately for future expansion.
m=Macro()
jobs={
    "omo":lambda:m.currency().omo(start="2018-01-01"),
    "interbank":lambda:m.currency().interbank_rate(start="2018-01-01",period="day"),
    "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
    "m2":lambda:m.economy().money_supply(start="2012-01",period="month"),
    "credit":lambda:m.economy().credit(start="2012-01",period="month"),
    "cpi":lambda:m.economy().cpi(start="2012-01",period="month"),
    "budget":lambda:m.economy().state_budget(start="2012-01",period="month"),
}
for name,fn in jobs.items():
    try:
        df=fn()
        if df is not None and len(df):
            x=df.copy()
            x["Data Type"]="ACTUAL"
            x["Source Mode"]="BRONZE"
            x["Retrieved At"]=datetime.now().astimezone().isoformat(timespec="seconds")
            x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig")
        status.append([name,"OK","",datetime.now().astimezone().isoformat(timespec="seconds")])
    except Exception as e:
        status.append([name,"ERROR",str(e)[:300],datetime.now().astimezone().isoformat(timespec="seconds")])
    time.sleep(.25)

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(DATA/"refresh_status.csv",index=False,encoding="utf-8-sig")
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

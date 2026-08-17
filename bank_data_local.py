
from pathlib import Path
from datetime import datetime
import json,re,time
import pandas as pd

ROOT=Path(__file__).parent
DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

def norm(s): return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df,keys):
    if df is None or len(df)==0:return None
    for c in df.columns:
        n=norm(c)
        if any(k in n for k in keys):
            v=pd.to_numeric(df[c],errors="coerce").dropna()
            if len(v):return float(v.iloc[0])
    for lc in df.columns[:min(3,len(df.columns))]:
        labels=df[lc].astype(str).map(norm)
        mask=pd.Series(False,index=df.index)
        for k in keys: mask|=labels.str.contains(k,regex=False)
        if mask.any():
            for vc in reversed(df.columns):
                if vc==lc:continue
                v=pd.to_numeric(df.loc[mask,vc],errors="coerce").dropna()
                if len(v):return float(v.iloc[0])
    return None

def latest_period(*dfs):
    for df in dfs:
        if df is None or len(df)==0:continue
        for c in ["report_time","year","quarter","period","time"]:
            if c in df.columns:
                v=df[c].dropna()
                if len(v):return str(v.iloc[0])
    return ""

def fetch(symbol):
    from vnstock_data import Fundamental
    f=Fundamental()
    eq=f.equity(symbol)
    bs=eq.balance_sheet(period="Q")
    inc=eq.income_statement(period="Q")
    try: ratio=eq.financial_ratio()
    except Exception:
        try: ratio=eq.ratio(period="Q")
        except Exception: ratio=pd.DataFrame()
    assets=find_metric(bs,["total assets","tổng tài sản"])
    loans=find_metric(bs,["customer loans","loans to customers","cho vay khách hàng"])
    deposits=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
    ib=find_metric(bs,["borrowings from other credit institutions","interbank borrowing","vay các tổ chức tín dụng","tiền gửi và vay các tổ chức tín dụng"])
    current=find_metric(bs,["current account","demand deposit","tiền gửi không kỳ hạn"])
    totaldep=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
    nii=find_metric(inc,["net interest income","thu nhập lãi thuần"])
    nim=find_metric(ratio,["nim","net interest margin"])
    ldr=find_metric(ratio,["ldr","loan to deposit"])
    casa=find_metric(ratio,["casa"])
    if ldr is None and loans is not None and deposits not in (None,0):ldr=loans/deposits
    if casa is None and current is not None and totaldep not in (None,0):casa=current/totaldep
    return {
      "Ticker":symbol,"Period":latest_period(bs,inc,ratio),"Total Assets":assets,
      "Customer Loans":loans,"Customer Deposits":deposits,"Interbank Borrowing":ib,
      "Current Accounts":current,"Total Deposits":totaldep,"Net Interest Income":nii,
      "Average Earning Assets":None,"NIM":nim,"LDR Proxy":ldr,"CASA Proxy":casa,
      "Data Type":"ACTUAL","Retrieved At":datetime.now().astimezone().isoformat(timespec="seconds")
    }

def main():
    rows=[];status=[]
    for s in BANKS:
        try:
            rows.append(fetch(s));status.append([s,"OK",""])
        except Exception as e:
            status.append([s,"ERROR",repr(e)])
        time.sleep(.15)
    pd.DataFrame(rows).to_csv(DATA/"bank_actuals.csv",index=False,encoding="utf-8-sig")
    pd.DataFrame(status,columns=["Ticker","Status","Message"]).to_csv(DATA/"bank_refresh_status.csv",index=False,encoding="utf-8-sig")
    print(pd.DataFrame(status,columns=["Ticker","Status","Message"]))

if __name__=="__main__":main()

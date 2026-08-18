
from pathlib import Path
from datetime import datetime
import pandas as pd, numpy as np, json, time, sys

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; RAW=DATA/"raw_bank"
DATA.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
BANKS=json.loads((ROOT/"config/banks.json").read_text(encoding="utf-8"))

try:
    from vnstock_data import Fundamental, Macro
except Exception as e:
    print("ERROR: vnstock_data unavailable:",repr(e)); sys.exit(2)

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")

def latest_id(df, ids):
    if df is None or len(df)==0 or "id" not in df.columns:
        return np.nan
    x=df.copy()
    x["id"]=x["id"].astype(str)
    ids_upper=[str(i).upper() for i in ids]
    m=x["id"].str.upper().isin(ids_upper)
    if not m.any():
        return np.nan
    x=x[m].copy()
    if "period" in x.columns:
        # Periods are YYYY-Qn strings; lexical order works.
        x=x.sort_values("period")
    if "value" in x.columns:
        v=pd.to_numeric(x["value"],errors="coerce").dropna()
        return float(v.iloc[-1]) if len(v) else np.nan
    # financial_health wide schema
    period_cols=[c for c in x.columns if str(c)[:4].isdigit() and ("Q" in str(c) or "-" in str(c))]
    if period_cols:
        period_cols=sorted(period_cols)
        v=pd.to_numeric(x.iloc[0][period_cols],errors="coerce").dropna()
        return float(v.iloc[-1]) if len(v) else np.nan
    return np.nan

def latest_name(df, terms):
    if df is None or len(df)==0:
        return np.nan
    label_col="name" if "name" in df.columns else "item" if "item" in df.columns else None
    if not label_col:
        return np.nan
    s=df[label_col].astype(str).str.lower()
    mask=pd.Series(False,index=df.index)
    for t in terms:
        mask=mask | s.str.contains(str(t).lower(),regex=False,na=False)
    if not mask.any():
        return np.nan
    x=df[mask].copy()
    if "period" in x.columns:
        x=x.sort_values("period")
    if "value" in x.columns:
        v=pd.to_numeric(x["value"],errors="coerce").dropna()
        return float(v.iloc[-1]) if len(v) else np.nan
    period_cols=[c for c in x.columns if str(c)[:4].isdigit() and ("Q" in str(c) or "-" in str(c))]
    if period_cols:
        period_cols=sorted(period_cols)
        v=pd.to_numeric(x.iloc[0][period_cols],errors="coerce").dropna()
        return float(v.iloc[-1]) if len(v) else np.nan
    return np.nan

def fetch_bank(ticker):
    eq=Fundamental().equity(ticker)
    bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)
    ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)
    try:
        health=eq.financial_health(com_type="bank",reports=4,lang="en")
    except Exception:
        try: health=eq.financial_health(scorecard="bank",lang="en",limit=4)
        except Exception: health=pd.DataFrame()

    for name,df in [("balance_sheet",bs),("ratio",ratio),("financial_health",health)]:
        if df is not None and len(df):
            df.to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")

    # Schema locked from R5 diagnostic.
    ldr=latest_id(ratio,["RT_BANK_LDR"])
    casa=latest_id(ratio,["RT_BANK_CASA"])
    nim=latest_id(ratio,["RT_BANK_NIM"])
    if pd.isna(nim): nim=latest_name(ratio,["net interest margin","nim"])

    loans=latest_id(bs,[
        "BS_CUSTOMER_LOANS","BS_LOANS_TO_CUSTOMERS","BS_LOANS_AND_ADVANCES_TO_CUSTOMERS"
    ])
    if pd.isna(loans): loans=latest_name(bs,["customer loans","loans to customers"])

    deposits=latest_id(bs,["BS_CUSTOMER_DEPOSITS"])
    if pd.isna(deposits): deposits=latest_name(bs,["customer deposits"])

    assets=latest_id(bs,["BS_TOTAL_ASSETS"])
    interbank_liab=latest_id(bs,[
        "BS_PLACEMENTS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
        "BS_BORROWINGS_FROM_CREDIT_INSTITUTIONS"
    ])
    if pd.isna(interbank_liab):
        interbank_liab=latest_name(bs,["placements and borrowings from credit institutions","borrowings from credit institutions"])

    if pd.isna(ldr) and pd.notna(loans) and pd.notna(deposits) and deposits!=0:
        ldr=loans/deposits
    ibdep=interbank_liab/assets if pd.notna(interbank_liab) and pd.notna(assets) and assets!=0 else np.nan
    gap=(loans-deposits)/deposits if pd.notna(loans) and pd.notna(deposits) and deposits!=0 else np.nan

    vals=[ldr,casa,ibdep,gap,nim]
    coverage=float(pd.Series(vals).notna().mean())
    return [ticker,*vals,coverage,"ACTUAL","BRONZE","OK" if coverage>=.60 else "PARTIAL",now()]

status=[];rows=[]
for t in BANKS:
    try:
        rows.append(fetch_bank(t));status.append(["bank:"+t,"OK","",now()])
    except Exception as e:
        status.append(["bank:"+t,"ERROR",str(e)[:500],now()])
    time.sleep(.25)

pd.DataFrame(rows,columns=[
    "Ticker","LDR","CASA","InterbankDep","CreditDepositGap","NIM",
    "MetricCoverage","Data Type","Source Mode","ParseStatus","Retrieved At"
]).to_csv(DATA/"bank_actuals_bronze.csv",index=False,encoding="utf-8-sig")

m=Macro()

def save_raw(df,name):
    if df is None or len(df)==0:return False
    x=df.copy()
    x["Data Type"]="ACTUAL";x["Source Mode"]="BRONZE";x["Retrieved At"]=now()
    x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig")
    return True

for name,fn in {
    "omo":lambda:m.currency().omo(start="2018-01-01"),
    "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
    "m2":lambda:m.economy().money_supply(period="month",length=180),
    "credit":lambda:m.economy().credit(period="month",length=180),
    "cpi":lambda:m.economy().cpi(period="month",length=180),
    "budget":lambda:m.economy().state_budget(period="month",length=180),
}.items():
    try: status.append([name,"OK" if save_raw(fn(),name) else "EMPTY","",now()])
    except Exception as e: status.append([name,"ERROR",str(e)[:500],now()])
    time.sleep(.25)

# R6: use the runtime-proven interest_rate() response, filter TRUE interbank group and Overnight.
try:
    rates=m.currency().interest_rate(length=3650)
    rates.to_csv(DATA/"interest_rate_raw_bronze.csv",index=True,encoding="utf-8-sig")

    x=rates.reset_index().copy()
    # R5 showed columns: report_time(index), time, group_name, name, value, unit, source.
    group=x["group_name"].astype(str).str.lower() if "group_name" in x.columns else pd.Series("",index=x.index)
    tenor=x["name"].astype(str).str.lower() if "name" in x.columns else pd.Series("",index=x.index)
    mask=group.str.contains("liên ngân hàng",regex=False,na=False) & tenor.str.contains("qua đêm",regex=False,na=False)
    ib=x[mask].copy()

    if len(ib):
        date_source="time" if "time" in ib.columns else "report_time"
        ib["date"]=pd.to_datetime(ib[date_source],errors="coerce")
        ib["overnight_rate"]=pd.to_numeric(ib["value"],errors="coerce")
        keep=["date","overnight_rate"]
        for c in ["unit","source","group_name","name","report_time","time"]:
            if c in ib.columns and c not in keep: keep.append(c)
        ib=ib[keep].dropna(subset=["date","overnight_rate"]).sort_values("date").drop_duplicates("date",keep="last")
        ib["Data Type"]="ACTUAL"; ib["Source Mode"]="BRONZE"; ib["Retrieved At"]=now()
        ib.to_csv(DATA/"interbank_bronze.csv",index=False,encoding="utf-8-sig")
        status.append(["interbank","OK_INTEREST_RATE_FILTER",f"{len(ib)} overnight observations filtered from interest_rate(); source={ib['source'].iloc[-1] if 'source' in ib.columns else ''}",now()])
    else:
        status.append(["interbank","ERROR","interest_rate() returned data but no matching interbank/Qua đêm rows.",now()])
except Exception as e:
    manual=DATA/"interbank_manual.csv"
    if manual.exists() and manual.stat().st_size>50:
        status.append(["interbank","MANUAL_ACTUAL",f"Bronze interest_rate filter failed; manual ACTUAL retained. {str(e)[:350]}",now()])
    else:
        status.append(["interbank","ERROR",f"interest_rate() failed: {str(e)[:450]}",now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(DATA/"refresh_status.csv",index=False,encoding="utf-8-sig")
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

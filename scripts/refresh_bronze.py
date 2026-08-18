
from pathlib import Path
from datetime import datetime
import pandas as pd, numpy as np, json, time, sys, re, unicodedata

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; RAW=DATA/"raw_bank"
DATA.mkdir(exist_ok=True); RAW.mkdir(exist_ok=True)
BANKS=json.loads((ROOT/"config/banks.json").read_text(encoding="utf-8"))

try:
    from vnstock_data import Fundamental, Macro
except Exception as e:
    print("ERROR: vnstock_data unavailable:",repr(e)); sys.exit(2)

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def norm(x):
    s=str(x or "")
    s=unicodedata.normalize("NFKD",s)
    s="".join(ch for ch in s if not unicodedata.combining(ch))
    s=re.sub(r"[^a-zA-Z0-9]+"," ",s).lower().strip()
    return s

def period_key(v):
    s=str(v)
    m=re.match(r"(\d{4})[-_/ ]?Q?(\d{1,2})?",s,re.I)
    if m:
        return (int(m.group(1)),int(m.group(2) or 0))
    return (0,0)

def long_metric(df, ids=(), names=()):
    if df is None or len(df)==0:
        return np.nan
    x=df.copy()
    x.columns=[str(c) for c in x.columns]

    masks=[]
    if "id" in x.columns:
        sid=x["id"].astype(str).str.upper()
        for pat in ids:
            p=str(pat).upper()
            masks.append(sid.eq(p) | sid.str.contains(p,regex=False,na=False))
    if "name" in x.columns:
        sn=x["name"].astype(str).map(norm)
        for pat in names:
            p=norm(pat)
            masks.append(sn.str.contains(p,regex=False,na=False))

    for m in masks:
        if not m.any():
            continue
        z=x[m].copy()
        if "period" in z.columns:
            z["_pk"]=z["period"].map(period_key)
            z=z.sort_values("_pk")
        if "value" in z.columns:
            v=pd.to_numeric(z["value"],errors="coerce").dropna()
            if len(v):
                return float(v.iloc[-1])

    # Wide / financial_health schema fallback.
    for c in x.columns:
        nc=norm(c)
        if any(norm(p) in nc for p in list(ids)+list(names)):
            v=pd.to_numeric(x[c],errors="coerce").dropna()
            if len(v):
                return float(v.iloc[-1])

    # Row-text fallback for semi-structured outputs.
    for _,row in x.iterrows():
        lead=" | ".join(norm(v) for v in row.values[:min(8,len(row))])
        if any(norm(p) in lead for p in list(ids)+list(names)):
            for v0 in reversed(row.values):
                v=pd.to_numeric(pd.Series([v0]),errors="coerce").dropna()
                if len(v):
                    return float(v.iloc[0])
    return np.nan

def safe_call(fn, calls):
    errors=[]
    for label,args in calls:
        try:
            return fn(**args),label,errors
        except Exception as e:
            errors.append(f"{label}: {str(e)[:220]}")
    raise RuntimeError(" | ".join(errors))

def fetch_bank(ticker):
    eq=Fundamental().equity(ticker)

    bs,bs_call,_=safe_call(eq.balance_sheet,[
        ("long Bank",dict(period="quarter",lang="en",format="long",drop_empty=False,com_type="Bank")),
        ("long auto",dict(period="quarter",lang="en",format="long",drop_empty=False)),
        ("minimal",dict(period="quarter")),
    ])
    ratio,ratio_call,_=safe_call(eq.ratio,[
        ("long Bank",dict(period="quarter",lang="en",format="long",drop_empty=False,com_type="Bank")),
        ("long auto",dict(period="quarter",lang="en",format="long",drop_empty=False)),
        ("minimal",dict(period="quarter")),
    ])
    try:
        health=eq.financial_health(scorecard="bank",lang="en",limit=4)
        health_call="scorecard=bank"
    except Exception:
        try:
            health=eq.financial_health(com_type="bank",lang="en",limit=4)
            health_call="com_type=bank"
        except Exception:
            health=pd.DataFrame(); health_call="unavailable"

    for name,df in [("balance_sheet",bs),("ratio",ratio),("financial_health",health)]:
        if df is not None and len(df):
            df.to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")

    # Stable IDs from runtime diagnostic + broad name fallback.
    ldr=long_metric(ratio,
        ids=["RT_BANK_LDR"],
        names=["loan to deposit ratio","loans to deposits","ldr"])
    casa=long_metric(ratio,
        ids=["RT_BANK_CASA"],
        names=["casa","current account saving account","current account savings"])
    nim=long_metric(ratio,
        ids=["RT_BANK_NIM"],
        names=["net interest margin","nim"])
    if pd.isna(nim):
        nim=long_metric(health,ids=["RT_BANK_NIM"],names=["net interest margin","nim"])

    loans=long_metric(bs,
        ids=["BS_CUSTOMER_LOANS","BS_LOANS_TO_CUSTOMERS","BS_LOANS_AND_ADVANCES_TO_CUSTOMERS"],
        names=["loans to customers","customer loans","loans and advances to customers"])
    deposits=long_metric(bs,
        ids=["BS_CUSTOMER_DEPOSITS"],
        names=["customer deposits","deposits from customers"])
    assets=long_metric(bs,
        ids=["BS_TOTAL_ASSETS"],
        names=["total assets"])

    interbank_liab=long_metric(bs,
        ids=[
            "BS_PLACEMENTS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
            "BS_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
            "BS_DEPOSITS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS"
        ],
        names=[
            "placements and borrowings from credit institutions",
            "deposits and borrowings from credit institutions",
            "borrowings from credit institutions",
            "amounts due to credit institutions"
        ])

    if pd.isna(ldr) and pd.notna(loans) and pd.notna(deposits) and deposits!=0:
        ldr=loans/deposits

    ibdep=interbank_liab/assets if pd.notna(interbank_liab) and pd.notna(assets) and assets!=0 else np.nan
    gap=(loans-deposits)/deposits if pd.notna(loans) and pd.notna(deposits) and deposits!=0 else np.nan

    vals=[ldr,casa,ibdep,gap,nim]
    coverage=float(pd.Series(vals).notna().mean())
    metric_count=int(pd.Series(vals).notna().sum())
    return [
        ticker,*vals,coverage,metric_count,
        "ACTUAL","BRONZE",
        "OK" if coverage>=.60 else "PARTIAL",
        f"BS={bs_call}; Ratio={ratio_call}; Health={health_call}",
        now()
    ]

status=[]; rows=[]
for t in BANKS:
    try:
        rows.append(fetch_bank(t))
        status.append(["bank:"+t,"OK","",now()])
    except Exception as e:
        status.append(["bank:"+t,"ERROR",str(e)[:500],now()])
    time.sleep(.20)

pd.DataFrame(rows,columns=[
    "Ticker","LDR","CASA","InterbankDep","CreditDepositGap","NIM",
    "MetricCoverage","ActualMetricCount","Data Type","Source Mode","ParseStatus","ParserCall","Retrieved At"
]).to_csv(DATA/"bank_actuals_bronze.csv",index=False,encoding="utf-8-sig")

m=Macro()

def save_raw(df,name):
    if df is None or len(df)==0:
        return False
    x=df.copy()
    x["Data Type"]="ACTUAL"; x["Source Mode"]="BRONZE"; x["Retrieved At"]=now()
    x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig")
    return True

jobs={
    "omo":lambda:m.currency().omo(start="2018-01-01"),
    "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
    "m2":lambda:m.economy().money_supply(period="month",length=180),
    "credit":lambda:m.economy().credit(period="month",length=180),
    "cpi":lambda:m.economy().cpi(period="month",length=180),
}
for name,fn in jobs.items():
    try:
        status.append([name,"OK" if save_raw(fn(),name) else "EMPTY","",now()])
    except Exception as e:
        status.append([name,"ERROR",str(e)[:450],now()])
    time.sleep(.20)

# Budget is non-core. Try once; do not fail pipeline.
try:
    ok=save_raw(m.economy().state_budget(period="month",length=120),"budget")
    status.append(["budget","OK" if ok else "EMPTY","non-core",now()])
except Exception as e:
    status.append(["budget","DEGRADED",f"non-core dataset unavailable: {str(e)[:300]}",now()])

# ------------------------------------------------------------------
# R7 INTERBANK HARDENING:
# Official docs show interest_rate(period='day', length=365).
# Avoid 3650-day request that triggered backend 500.
# ------------------------------------------------------------------
def extract_interbank_rates(rates):
    if rates is None or len(rates)==0:
        return pd.DataFrame()

    x=rates.reset_index().copy()
    x.columns=[str(c) for c in x.columns]

    # Runtime schema observed in R5: group_name / name / value / time / source.
    if {"group_name","name","value"}.issubset(x.columns):
        g=x["group_name"].astype(str).map(norm)
        n=x["name"].astype(str).map(norm)
        mask=g.str.contains("lai suat binh quan lien ngan hang",regex=False,na=False) | \
             g.str.contains("lien ngan hang",regex=False,na=False)
        mask=mask & (
            n.str.contains("qua dem",regex=False,na=False) |
            n.str.contains("overnight",regex=False,na=False)
        )
        z=x[mask].copy()
        if len(z):
            dc="time" if "time" in z.columns else "report_time" if "report_time" in z.columns else "date"
            z["date"]=pd.to_datetime(z[dc],errors="coerce")
            z["overnight_rate"]=pd.to_numeric(z["value"],errors="coerce")
            keep=["date","overnight_rate"]
            for c in ["unit","source","group_name","name","time","report_time"]:
                if c in z.columns and c not in keep:
                    keep.append(c)
            return z[keep].dropna(subset=["date","overnight_rate"]).sort_values("date").drop_duplicates("date",keep="last")

    # Official long-format alternative: date / rate_type / rate_value.
    if {"rate_type","rate_value"}.issubset(x.columns):
        rt=x["rate_type"].astype(str).map(norm)
        mask=rt.str.contains("overnight",regex=False,na=False) | rt.str.contains("qua dem",regex=False,na=False)
        z=x[mask].copy()
        dc="date" if "date" in z.columns else "time"
        z["date"]=pd.to_datetime(z[dc],errors="coerce")
        z["overnight_rate"]=pd.to_numeric(z["rate_value"],errors="coerce")
        return z[["date","overnight_rate"]].dropna().sort_values("date").drop_duplicates("date",keep="last")

    return pd.DataFrame()

rate_calls=[
    ("day_length_365",dict(period="day",length=365)),
    ("length_365",dict(length=365)),
    ("day_length_180",dict(period="day",length=180)),
    ("length_180",dict(length=180)),
    ("day_length_90",dict(period="day",length=90)),
    ("length_90",dict(length=90)),
]
ib=None; raw_rates=None; errors=[]
for label,args in rate_calls:
    try:
        raw=m.currency().interest_rate(**args)
        candidate=extract_interbank_rates(raw)
        if len(candidate):
            ib=candidate; raw_rates=raw; used_call=label
            break
        errors.append(f"{label}: returned {0 if raw is None else len(raw)} rows but no ON match")
    except Exception as e:
        errors.append(f"{label}: {str(e)[:220]}")

if ib is not None and len(ib):
    raw_rates.to_csv(DATA/"interest_rate_raw_bronze.csv",index=True,encoding="utf-8-sig")
    ib["Data Type"]="ACTUAL"; ib["Source Mode"]="BRONZE"; ib["Retrieved At"]=now()
    ib.to_csv(DATA/"interbank_bronze.csv",index=False,encoding="utf-8-sig")
    status.append([
        "interbank","OK_INTEREST_RATE_FILTER",
        f"call={used_call}; observations={len(ib)}; latest={ib['date'].max()}",
        now()
    ])
else:
    manual=DATA/"interbank_manual.csv"
    old=DATA/"interbank_bronze.csv"
    if old.exists() and old.stat().st_size>100:
        status.append(["interbank","DEGRADED","New refresh failed; retained prior ACTUAL interbank file. "+" | ".join(errors),now()])
    elif manual.exists() and manual.stat().st_size>50:
        status.append(["interbank","MANUAL_ACTUAL","Using manual/public ACTUAL. "+" | ".join(errors),now()])
    else:
        status.append(["interbank","ERROR"," | ".join(errors),now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(
    DATA/"refresh_status.csv",index=False,encoding="utf-8-sig"
)
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

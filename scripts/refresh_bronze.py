
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
    s=str(x if x is not None else "")
    # Vietnamese đ/Đ are not decomposed by NFKD; normalize explicitly.
    s=s.replace("đ","d").replace("Đ","D")
    s=unicodedata.normalize("NFKD",s)
    s="".join(ch for ch in s if not unicodedata.combining(ch))
    s=re.sub(r"[^a-zA-Z0-9]+"," ",s).lower().strip()
    return s

def flatten_frame(df):
    """Normalize MultiIndex index/columns without calling pd.isna on MultiIndex."""
    if df is None:
        return pd.DataFrame()
    x=df.copy()

    # Move index levels to columns safely.
    try:
        if isinstance(x.index,pd.MultiIndex):
            x=x.reset_index()
        elif x.index.name is not None and x.index.name not in x.columns:
            x=x.reset_index()
    except Exception:
        # If reset fails, preserve values and use a simple RangeIndex.
        x=x.copy()
        x.index=pd.RangeIndex(len(x))

    # Flatten MultiIndex columns by keeping non-empty level labels.
    if isinstance(x.columns,pd.MultiIndex):
        cols=[]
        seen={}
        for c in x.columns:
            parts=[str(v).strip() for v in c if str(v).strip() not in {"","None","nan"}]
            name=" | ".join(parts) if parts else "column"
            n=seen.get(name,0)
            seen[name]=n+1
            cols.append(name if n==0 else f"{name}__{n}")
        x.columns=cols
    else:
        x.columns=[str(c) for c in x.columns]
    return x

def period_key(v):
    s=str(v)
    m=re.search(r"(\d{4}).*?(?:Q|quarter)?\s*([1-4])?",s,re.I)
    if m:
        return (int(m.group(1)),int(m.group(2) or 0))
    return (0,0)

def candidate_col(x, names):
    wanted=[norm(n) for n in names]
    # Prefer exact final-level matches first; important for MultiIndex-flattened
    # names such as "meta | name" versus "meta | group_name".
    for c in x.columns:
        nc=norm(c)
        tail=nc.split()[-1] if nc else ""
        if any(w==nc or w==tail or nc.endswith(" "+w) for w in wanted):
            return c
    # Then allow broader contains matching.
    for c in x.columns:
        nc=norm(c)
        if any(w in nc for w in wanted):
            return c
    return None

def metric_from_frame(df, ids=(), names=()):
    x=flatten_frame(df)
    if x.empty:
        return np.nan

    idc=candidate_col(x,["id","code","metric_id"])
    namec=candidate_col(x,["name","metric","indicator","item","label"])
    vc=candidate_col(x,["value","metric_value","ratio_value"])
    pc=candidate_col(x,["period","report_period","quarter","year"])

    masks=[]
    if idc:
        sid=x[idc].astype(str).str.upper()
        for p in ids:
            pu=str(p).upper()
            masks.append(sid.eq(pu) | sid.str.contains(pu,regex=False,na=False))
    if namec:
        sn=x[namec].astype(str).map(norm)
        for p in names:
            pn=norm(p)
            masks.append(sn.str.contains(pn,regex=False,na=False))

    for m in masks:
        if not bool(m.any()):
            continue
        z=x.loc[m].copy()
        if pc:
            z["_period_key"]=z[pc].map(period_key)
            z=z.sort_values("_period_key")
        if vc:
            vals=pd.to_numeric(z[vc],errors="coerce").dropna()
            if len(vals):
                return float(vals.iloc[-1])

        # Wide financial_health: latest numeric period column in matching row.
        for _,row in z.iterrows():
            numeric=[]
            for c in z.columns:
                if c in {idc,namec,pc,"_period_key"}:
                    continue
                v=pd.to_numeric(pd.Series([row[c]]),errors="coerce").dropna()
                if len(v):
                    numeric.append((period_key(c),float(v.iloc[0])))
            if numeric:
                numeric.sort(key=lambda q:q[0])
                return numeric[-1][1]

    # Column-name match fallback.
    for c in x.columns:
        nc=norm(c)
        if any(norm(p) in nc for p in list(ids)+list(names)):
            vals=pd.to_numeric(x[c],errors="coerce").dropna()
            if len(vals):
                return float(vals.iloc[-1])

    # Row text fallback.
    for _,row in x.iterrows():
        text=" | ".join(norm(v) for v in row.values[:min(10,len(row))])
        if any(norm(p) in text for p in list(ids)+list(names)):
            nums=[]
            for v0 in row.values:
                v=pd.to_numeric(pd.Series([v0]),errors="coerce").dropna()
                if len(v):
                    nums.append(float(v.iloc[0]))
            if nums:
                return nums[-1]
    return np.nan

def try_source(label, fn):
    try:
        df=fn()
        return df,f"{label}:OK"
    except Exception as e:
        return pd.DataFrame(),f"{label}:ERROR:{str(e)[:180]}"

def fetch_bank(ticker):
    # IMPORTANT: each source is isolated. Failure of balance_sheet/ratio must not kill ticker.
    eq=Fundamental().equity(ticker)

    health,health_status=try_source("health",
        lambda:eq.financial_health(scorecard="bank",lang="en",limit=4))

    ratio,ratio_status=try_source("ratio-long-bank",
        lambda:eq.ratio(period="quarter",lang="en",format="long",com_type="Bank"))
    if ratio.empty:
        ratio,ratio_status2=try_source("ratio-default",
            lambda:eq.ratio(period="quarter"))
        ratio_status += " | "+ratio_status2

    bs,bs_status=try_source("bs-long-bank",
        lambda:eq.balance_sheet(period="quarter",lang="en",format="long",com_type="Bank"))
    if bs.empty:
        bs,bs_status2=try_source("bs-default",
            lambda:eq.balance_sheet(period="quarter"))
        bs_status += " | "+bs_status2

    for name,df in [("financial_health",health),("ratio",ratio),("balance_sheet",bs)]:
        if df is not None and len(df):
            try:
                flatten_frame(df).to_csv(RAW/f"{ticker}_{name}.csv",index=False,encoding="utf-8-sig")
            except Exception:
                pass

    # Use financial_health FIRST because it is designed for stable bank scorecards.
    ldr=metric_from_frame(health,["RT_BANK_LDR"],["loan to deposit ratio","ldr"])
    if pd.isna(ldr):
        ldr=metric_from_frame(ratio,["RT_BANK_LDR"],["loan to deposit ratio","ldr"])

    casa=metric_from_frame(health,["RT_BANK_CASA"],["casa","current account saving"])
    if pd.isna(casa):
        casa=metric_from_frame(ratio,["RT_BANK_CASA"],["casa","current account saving"])

    nim=metric_from_frame(health,["RT_BANK_NIM"],["net interest margin","nim"])
    if pd.isna(nim):
        nim=metric_from_frame(ratio,["RT_BANK_NIM"],["net interest margin","nim"])

    loans=metric_from_frame(bs,
        ["BS_CUSTOMER_LOANS","BS_LOANS_TO_CUSTOMERS","BS_LOANS_AND_ADVANCES_TO_CUSTOMERS"],
        ["loans to customers","customer loans","loans and advances to customers"])
    deposits=metric_from_frame(bs,
        ["BS_CUSTOMER_DEPOSITS"],
        ["customer deposits","deposits from customers"])
    assets=metric_from_frame(bs,
        ["BS_TOTAL_ASSETS"],
        ["total assets"])
    interbank_liab=metric_from_frame(bs,
        ["BS_PLACEMENTS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
         "BS_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
         "BS_DEPOSITS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS"],
        ["placements and borrowings from credit institutions",
         "deposits and borrowings from credit institutions",
         "amounts due to credit institutions"])

    if pd.isna(ldr) and pd.notna(loans) and pd.notna(deposits) and deposits!=0:
        ldr=float(loans/deposits)
    ibdep=float(interbank_liab/assets) if pd.notna(interbank_liab) and pd.notna(assets) and assets!=0 else np.nan
    gap=float((loans-deposits)/deposits) if pd.notna(loans) and pd.notna(deposits) and deposits!=0 else np.nan

    vals=[ldr,casa,ibdep,gap,nim]
    actual_count=int(pd.Series(vals,dtype="float64").notna().sum())
    coverage=actual_count/5

    return [
        ticker,*vals,coverage,actual_count,
        "ACTUAL","BRONZE",
        "OK" if coverage>=.60 else "PARTIAL",
        f"{health_status} || {ratio_status} || {bs_status}",
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
    x=flatten_frame(df)
    x["Data Type"]="ACTUAL"; x["Source Mode"]="BRONZE"; x["Retrieved At"]=now()
    x.to_csv(DATA/f"{name}_bronze.csv",index=False,encoding="utf-8-sig")
    return True

for name,fn in {
    "omo":lambda:m.currency().omo(start="2018-01-01"),
    "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
    "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
    "m2":lambda:m.economy().money_supply(period="month",length=180),
    "credit":lambda:m.economy().credit(period="month",length=180),
    "cpi":lambda:m.economy().cpi(period="month",length=180),
}.items():
    try:
        status.append([name,"OK" if save_raw(fn(),name) else "EMPTY","",now()])
    except Exception as e:
        status.append([name,"ERROR",str(e)[:450],now()])
    time.sleep(.20)

try:
    ok=save_raw(m.economy().state_budget(period="month",length=120),"budget")
    status.append(["budget","OK" if ok else "EMPTY","non-core",now()])
except Exception as e:
    status.append(["budget","DEGRADED",f"non-core dataset unavailable: {str(e)[:300]}",now()])

def find_interbank_on(raw):
    x=flatten_frame(raw)
    if x.empty:
        return pd.DataFrame()

    # Create normalized text across every non-numeric/textual column.
    text_cols=[]
    for c in x.columns:
        if x[c].dtype=="object" or "string" in str(x[c].dtype).lower():
            text_cols.append(c)

    if text_cols:
        row_text=x[text_cols].fillna("").astype(str).agg(" | ".join,axis=1).map(norm)
    else:
        row_text=pd.Series("",index=x.index)

    interbank_mask=row_text.str.contains("lien ngan hang",regex=False,na=False) | \
                   row_text.str.contains("interbank",regex=False,na=False)
    on_mask=row_text.str.contains("qua dem",regex=False,na=False) | \
            row_text.str.contains("overnight",regex=False,na=False)
    z=x[interbank_mask & on_mask].copy()

    # If group label is absent but tenor is explicit, accept Overnight rows only if source/table is the
    # interest-rate table and at least one other row contains interbank wording.
    if z.empty and bool(interbank_mask.any()) and bool(on_mask.any()):
        z=x[on_mask].copy()

    if z.empty:
        return pd.DataFrame()

    # Identify datetime column.
    dc=None
    for cand in ["time","date","report_time","datetime","period"]:
        c=candidate_col(z,[cand])
        if c:
            parsed=pd.to_datetime(z[c],errors="coerce")
            if parsed.notna().sum()>0:
                dc=c;break
    if dc is None:
        # Try every column.
        for c in z.columns:
            parsed=pd.to_datetime(z[c],errors="coerce")
            if parsed.notna().sum()>=max(2,len(z)//3):
                dc=c;break

    # Identify value/rate column.
    vc=candidate_col(z,["value","rate_value","overnight_rate","rate"])
    if vc is None:
        best=None;count=0
        for c in z.columns:
            vals=pd.to_numeric(z[c],errors="coerce")
            n=vals.notna().sum()
            if n>count:
                best,count=c,n
        vc=best

    if dc is None or vc is None:
        return pd.DataFrame()

    out=pd.DataFrame({
        "date":pd.to_datetime(z[dc],errors="coerce"),
        "overnight_rate":pd.to_numeric(z[vc],errors="coerce")
    })
    # Keep useful lineage fields.
    for cand in ["source","unit","group_name","name","rate_type"]:
        c=candidate_col(z,[cand])
        if c and c not in out.columns:
            out[cand]=z[c].values
    return out.dropna(subset=["date","overnight_rate"]).sort_values("date").drop_duplicates("date",keep="last")

rate_calls=[
    ("day_length_365",dict(period="day",length=365)),
    ("length_365",dict(length=365)),
    ("day_length_180",dict(period="day",length=180)),
    ("length_180",dict(length=180)),
    ("day_length_90",dict(period="day",length=90)),
    ("length_90",dict(length=90)),
]
ib=None;raw_success=None;used_call=None;errors=[]

for label,args in rate_calls:
    try:
        raw=m.currency().interest_rate(**args)
        candidate=find_interbank_on(raw)
        if len(candidate):
            ib=candidate;raw_success=raw;used_call=label
            break
        schema=flatten_frame(raw)
        errors.append(f"{label}: returned {len(schema)} rows; cols={list(schema.columns)[:12]}; no ON match")
    except Exception as e:
        errors.append(f"{label}: {str(e)[:220]}")

if ib is not None and len(ib):
    flatten_frame(raw_success).to_csv(DATA/"interest_rate_raw_bronze.csv",index=False,encoding="utf-8-sig")
    ib["Data Type"]="ACTUAL";ib["Source Mode"]="BRONZE";ib["Retrieved At"]=now()
    ib.to_csv(DATA/"interbank_bronze.csv",index=False,encoding="utf-8-sig")
    status.append(["interbank","OK_INTEREST_RATE_FILTER",
                   f"call={used_call}; observations={len(ib)}; latest={ib['date'].max()}",now()])
else:
    old=DATA/"interbank_bronze.csv";manual=DATA/"interbank_manual.csv"
    if old.exists() and old.stat().st_size>100:
        status.append(["interbank","DEGRADED","Refresh failed; retained prior ACTUAL. "+" | ".join(errors),now()])
    elif manual.exists() and manual.stat().st_size>50:
        status.append(["interbank","MANUAL_ACTUAL","Using manual/public ACTUAL. "+" | ".join(errors),now()])
    else:
        status.append(["interbank","ERROR"," | ".join(errors),now()])

pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]).to_csv(
    DATA/"refresh_status.csv",index=False,encoding="utf-8-sig"
)
print(pd.DataFrame(status,columns=["dataset","status","message","Retrieved At"]))

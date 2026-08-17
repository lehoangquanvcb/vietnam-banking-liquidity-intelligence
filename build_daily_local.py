
from pathlib import Path
import pandas as pd, numpy as np

DATA=Path(__file__).parent/"data"

def load(n):
    p=DATA/f"{n}.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def datecol(df):
    for c in ["time","date","report_time","period"]:
        if c in df.columns:return c
    return None

def findcol(df,keys):
    for c in df.columns:
        s=str(c).lower()
        if any(k.lower()==s for k in keys):return c
    for c in df.columns:
        s=str(c).lower()
        if any(k.lower() in s for k in keys):return c
    return None

def series(name,keys):
    df=load(name)
    if df.empty:return pd.DataFrame()
    dc=datecol(df);vc=findcol(df,keys)
    if not dc or not vc:return pd.DataFrame()
    x=df[[dc,vc]].copy();x.columns=["date",name]
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    x[name]=pd.to_numeric(x[name],errors="coerce")
    return x.dropna(subset=["date"]).groupby("date",as_index=False).last()

def z(s,w=60):
    m=s.rolling(w,min_periods=20).mean()
    sd=s.rolling(w,min_periods=20).std()
    return (s-m)/sd.replace(0,np.nan)

def main():
    parts=[series("omo",["netflow_amount","netflow","net"]),
           series("interbank",["overnight","on","qua đêm"]),
           series("fx",["usd","usd_vnd"])]
    parts=[p for p in parts if len(p)]
    if not parts:
        pd.DataFrame(columns=["date","omo","interbank","fx","LPI"]).to_csv(DATA/"daily_features.csv",index=False)
        return
    out=parts[0]
    for p in parts[1:]:out=out.merge(p,on="date",how="outer")
    out=out.sort_values("date")
    if "interbank" in out:out["on_z"]=z(out["interbank"])
    if "omo" in out:out["omo_z"]=-z(out["omo"])
    if "fx" in out:
        out["fx_ret5"]=np.log(out["fx"]).diff(5)
        out["fx_z"]=z(out["fx_ret5"])
    comps=[c for c in ["on_z","omo_z","fx_z"] if c in out]
    if comps:out["LPI"]=out[comps].mean(axis=1,skipna=True)
    out.to_csv(DATA/"daily_features.csv",index=False,encoding="utf-8-sig")

if __name__=="__main__":main()

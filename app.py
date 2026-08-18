
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json

ROOT=Path(__file__).parent
DATA=ROOT/"data"
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="Vietnam Banking Liquidity Intelligence",layout="wide")
st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG")
st.caption("Bronze Data Pipeline • System Liquidity • Stress Test • Bank Vulnerability")

def load(name):
    try:return pd.read_csv(DATA/f"{name}.csv")
    except:return pd.DataFrame()

def safe_df(df):
    x=df.copy()
    for c in x.columns:
        if x[c].dtype=="object":
            x[c]=x[c].map(lambda v:"" if pd.isna(v) else str(v))
    return x

def ratio(s):
    x=pd.to_numeric(s,errors="coerce")
    return np.where(np.abs(x)>2,x/100,x)

def score(df,mult=1.35,pass_through=2.0):
    if df.empty:return df
    d=df.copy()
    for c in ["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]:
        if c not in d.columns:d[c]=np.nan
        d[c]=ratio(d[c])
    d["LiquidityBuffer"]=1-d["LDR"]
    fields=["LDR","CASA","InterbankDep","CreditDepositGap","NIM","LiquidityBuffer"]
    d["Coverage"]=d[fields].notna().mean(axis=1)
    raw=50+35*(d.LDR-.85)-25*(d.CASA-.20)+45*d.InterbankDep+30*d.CreditDepositGap-10*(d.NIM-.03)-20*(d.LiquidityBuffer-.15)
    d["BaseVulnerability"]=raw.clip(0,100)
    d.loc[d.Coverage<.5,"BaseVulnerability"]=np.nan
    d["StressVulnerability"]=(d.BaseVulnerability*mult).clip(0,100)
    d["FundingCostShock_ppt"]=pass_through*d.StressVulnerability/100
    d["StressedNIM"]=np.maximum(0,d.NIM-d.FundingCostShock_ppt/100)
    d["Watch"]=np.select([(d.StressVulnerability>=75)|(d.StressedNIM<.02),d.StressVulnerability>=60],["ĐỎ","VÀNG"],default="XANH")
    return d.sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

macro=load("macro_public_snapshot")
actual=load("bank_actuals_bronze")
fallback=load("bank_fallback_assumptions")
refresh=load("refresh_status")

# Use Bronze actual first; fallback only for missing tickers.
actual_good=actual.copy()
if len(actual_good):
    actual_good=actual_good[
        actual_good[["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]].notna().sum(axis=1)>=3
    ]
missing=fallback[~fallback.Ticker.isin(actual_good.Ticker)] if len(actual_good) else fallback.copy()
bank=pd.concat([actual_good,missing],ignore_index=True) if len(actual_good) else missing.copy()

bronze_count=int((bank["Source Mode"]=="BRONZE").sum())
fallback_count=int((bank["Data Type"]=="ASSUMPTION").sum())

def mv(ind):
    q=macro[macro.Indicator==ind]
    return float(q.Value.iloc[0]) if len(q) else np.nan
credit,dep,cpi,trade=mv("Tăng trưởng tín dụng YTD"),mv("Tăng trưởng huy động YTD"),mv("CPI YoY"),mv("Cán cân thương mại")
gap=credit-dep
pressure=float(np.clip(gap/3+max(0,cpi-4)/2+max(0,-trade)/20,0,3))
sc=score(bank)

# Data age
last_refresh=""
if len(actual) and "Retrieved At" in actual.columns:
    ts=pd.to_datetime(actual["Retrieved At"],errors="coerce").max()
    if pd.notna(ts):last_refresh=str(ts)

with st.sidebar:
    st.subheader("TRẠNG THÁI DỮ LIỆU")
    if bronze_count:
        st.success(f"🟢 Bronze ACTUAL: {bronze_count}/{len(BANKS)} ngân hàng")
    else:
        st.warning("🟠 Chưa có Bronze ACTUAL trong repo")
    st.write(f"Fallback: **{fallback_count}**")
    if last_refresh:st.caption(f"Bronze refresh gần nhất: {last_refresh}")
    st.divider()
    st.caption("Dữ liệu Bronze được cập nhật từ máy ổn định/self-hosted runner rồi push lên GitHub. Streamlit không cài Sponsor và không tiêu tốn API quota.")

tabs=st.tabs(["Trung tâm điều hành","Xếp hạng ngân hàng","Mô phỏng Stress","Chi tiết ngân hàng","Thanh khoản hệ thống","Chất lượng dữ liệu"])

with tabs[0]:
    a,b,c,d=st.columns(4)
    a.metric("Bronze ACTUAL",bronze_count)
    b.metric("Fallback",fallback_count)
    c.metric("Funding gap",f"{gap:.2f} ppt")
    d.metric("System Pressure",f"{pressure:.2f}/3")
    if bronze_count==0:
        st.warning("Chưa chạy Bronze refresh. Hãy chạy REFRESH_BRONZE_AND_PUSH.bat trên máy đã cài Vnstock Sponsor.")
    top=sc.head(10)
    st.subheader("Top 10 nhạy cảm với stress thanh khoản")
    st.bar_chart(top.set_index("Ticker")[["StressVulnerability"]],height=320)
    st.dataframe(safe_df(top[["Ticker","Source Mode","Data Type","LDR","CASA","NIM","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]]),hide_index=True)

with tabs[1]:
    st.dataframe(safe_df(sc),hide_index=True)

with tabs[2]:
    x,y,z=st.columns(3)
    mult=x.slider("Hệ số stress",1.0,2.2,1.35,.05)
    passt=y.slider("Funding pass-through (ppt)",.5,4.0,2.0,.25)
    lpi=z.slider("Liquidity pressure",0.0,3.0,pressure,.1)
    stressed=score(bank,mult*(1+.12*lpi),passt)
    st.bar_chart(stressed.set_index("Ticker")[["BaseVulnerability","StressVulnerability"]],height=340)
    st.dataframe(safe_df(stressed[["Ticker","Source Mode","Data Type","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]]),hide_index=True)

with tabs[3]:
    tick=st.selectbox("Ngân hàng",sc.Ticker.tolist())
    r=sc[sc.Ticker==tick].iloc[0]
    a,b,c,d=st.columns(4)
    a.metric("Nguồn",str(r["Source Mode"]))
    b.metric("Vulnerability",f"{r.StressVulnerability:.1f}")
    c.metric("Funding cost",f"+{r.FundingCostShock_ppt:.2f} ppt")
    d.metric("Stressed NIM",f"{r.StressedNIM:.2%}")
    st.dataframe(safe_df(pd.DataFrame({
        "Chỉ tiêu":["LDR","CASA","Interbank dependence","Credit-deposit gap","NIM","Coverage","Watch"],
        "Giá trị":[r.LDR,r.CASA,r.InterbankDep,r.CreditDepositGap,r.NIM,r.Coverage,r.Watch]
    })),hide_index=True)

with tabs[4]:
    st.dataframe(safe_df(macro),hide_index=True)
    a,b=st.columns(2)
    a.metric("Funding gap",f"{gap:.2f} ppt")
    b.metric("System Pressure Proxy",f"{pressure:.2f}/3")

with tabs[5]:
    st.subheader("Bronze refresh status")
    st.dataframe(safe_df(refresh),hide_index=True)
    st.subheader("Data lineage")
    st.dataframe(safe_df(bank.groupby(["Source Mode","Data Type"]).size().reset_index(name="Rows")),hide_index=True)
    st.info("Streamlit production không import vnstock/vnstock_data. Vì vậy app không thể bị lỗi installer/rate-limit của Vnstock.")

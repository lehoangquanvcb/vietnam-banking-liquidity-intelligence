
import streamlit as st
import pandas as pd, numpy as np
from pathlib import Path
from bank_stress import score, read_actuals

ROOT=Path(__file__).parent; DATA=ROOT/"data"
st.set_page_config(page_title="Vietnam Banking Liquidity V6",layout="wide")
st.title("VIETNAM MONETARY & BANKING LIQUIDITY INTELLIGENCE — V6")
st.caption("Vnstock Bronze Sponsor • System Liquidity → Bank Funding → NIM Stress → Watchlist")

def load(name):
    p=DATA/f"{name}.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

tabs=st.tabs(["Control Center","Bank Ranking","Stress Lab","Bank Detail","System Liquidity","Data Quality"])

with tabs[0]:
    actual=read_actuals()
    stressed=score(actual) if len(actual) else pd.DataFrame()
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Bank universe","20")
    c2.metric("Banks with actual data",str(len(actual)))
    if len(stressed):
        c3.metric("RED watch",str((stressed.WatchFlag=="RED").sum()))
        c4.metric("Median vulnerability",f"{stressed.StressVulnerability.median():.1f}")
    else:
        c3.metric("RED watch","N/A"); c4.metric("Median vulnerability","N/A")
    st.info("Run: `python bank_data.py` → `python bank_stress.py`. V6 will not fabricate missing bank statements.")

with tabs[1]:
    d=load("bank_stress")
    if len(d):
        st.bar_chart(d.set_index("Ticker")[["StressVulnerability"]])
        st.dataframe(d,use_container_width=True,hide_index=True)
    else: st.warning("No bank stress output yet.")

with tabs[2]:
    actual=read_actuals()
    c1,c2,c3=st.columns(3)
    mult=c1.slider("System stress multiplier",1.0,2.0,1.35,.05)
    pass_through=c2.slider("Max funding cost pass-through (ppt)",0.5,4.0,2.0,.25)
    lpi=c3.slider("System LPI scenario",-1.0,3.0,1.5,.1)
    if len(actual):
        # LPI adds non-linear scaling above neutral
        effective=mult*(1+max(0,lpi)*0.10)
        d=score(actual,effective,pass_through)
        st.dataframe(d,use_container_width=True,hide_index=True)
        st.bar_chart(d.set_index("Ticker")[["BaseVulnerability","StressVulnerability"]])
    else: st.warning("Run bank_data.py first.")

with tabs[3]:
    d=load("bank_stress")
    if len(d):
        tick=st.selectbox("Bank",d.Ticker.tolist())
        r=d[d.Ticker==tick].iloc[0]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Stress Vulnerability",f"{r.StressVulnerability:.1f}")
        c2.metric("Funding Cost Shock",f"+{r.FundingCostShock_ppt:.2f} ppt")
        c3.metric("Stressed NIM",f"{r.StressedNIM:.2%}" if pd.notna(r.StressedNIM) else "N/A")
        c4.metric("Watch",r.WatchFlag)
        st.dataframe(pd.DataFrame(r).reset_index().rename(columns={"index":"Metric",0:"Value"}),use_container_width=True,hide_index=True)

with tabs[4]:
    d=load("daily_features")
    if len(d):
        st.dataframe(d.tail(120),use_container_width=True,hide_index=True)
        if "LPI" in d:
            d["date"]=pd.to_datetime(d["date"])
            st.line_chart(d.set_index("date")[["LPI"]].tail(250))
    else: st.warning("System daily model data not found. V6 is compatible with V5 daily_features.csv.")

with tabs[5]:
    s=load("bank_refresh_status")
    if len(s): st.dataframe(s,use_container_width=True,hide_index=True)
    st.markdown("""
**Data rules**
- ACTUAL: Vnstock Fundamental / Macro or official source.
- CALC: derived only from ACTUAL inputs.
- ESTIMATE: explicit methodology required.
- ASSUMPTION: scenario/manual input only.
- Missing bank metrics remain blank; data coverage gates vulnerability output.
""")


import streamlit as st
import pandas as pd, numpy as np, json
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

ROOT=Path(__file__).parent
DATA=ROOT/"data"; OUT=DATA/"model_outputs"

st.set_page_config(page_title="Vietnam Banking Liquidity Intelligence",layout="wide")
st.markdown("""
<style>
.block-container{padding-top:2.6rem!important;padding-bottom:2.4rem}
h1{font-size:clamp(1.55rem,2.2vw,2.15rem)!important;line-height:1.28!important;margin:.2rem 0 .7rem 0!important}
[data-testid="stMetricValue"]{font-size:1.42rem}
div[data-testid="stTabs"] button{white-space:nowrap}
</style>
""",unsafe_allow_html=True)
st.title("TRUNG TÂM DỰ BÁO & PHÂN TÍCH THANH KHOẢN HỆ THỐNG NGÂN HÀNG")
st.caption("Bronze ACTUAL • Forecast • Regime • Bank Funding Stress • Explainable Model")

def csv(path):
    try:return pd.read_csv(path)
    except:return pd.DataFrame()
def js(path):
    try:return json.loads(Path(path).read_text(encoding="utf-8"))
    except:return {}
def safe(df):
    x=df.copy()
    for c in x.columns:
        if x[c].dtype=="object":x[c]=x[c].map(lambda v:"" if pd.isna(v) else str(v))
    return x

banks=csv(DATA/"bank_actuals_bronze.csv")
daily=csv(OUT/"daily_liquidity_panel.csv")
lpi_fc=csv(OUT/"lpi_forecast.csv")
ib_fc=csv(OUT/"interbank_forecast.csv")
regime=csv(OUT/"regime_probabilities.csv")
bank_fc=csv(OUT/"bank_stress_forecast.csv")
diag=csv(OUT/"model_diagnostics.csv")
refresh=csv(DATA/"refresh_status.csv")
summary=js(OUT/"model_summary.json")

def fan(history,forecast,col,title,ytitle,lpi=False):
    fig=go.Figure()
    if len(history) and col in history:
        h=history[["date",col]].copy()
        h["date"]=pd.to_datetime(h["date"],errors="coerce")
        h[col]=pd.to_numeric(h[col],errors="coerce")
        h=h.dropna()
        if len(h):
            h=h[h.date>=h.date.max()-pd.Timedelta(days=365)]
            fig.add_trace(go.Scatter(x=h.date,y=h[col],mode="lines",name="Actual",line=dict(width=2.2)))
    if lpi:
        fig.add_hrect(y0=-5,y1=-1,opacity=.05,line_width=0,annotation_text="Dư thừa")
        fig.add_hrect(y0=-1,y1=1,opacity=.03,line_width=0,annotation_text="Trung tính")
        fig.add_hrect(y0=1,y1=2,opacity=.05,line_width=0,annotation_text="Căng vừa")
        fig.add_hrect(y0=2,y1=8,opacity=.07,line_width=0,annotation_text="Căng cao")
        for y in [-1,1,2]:fig.add_hline(y=y,line_dash="dot",opacity=.35)
    if len(forecast):
        f=forecast.copy();f["date"]=pd.to_datetime(f["date"],errors="coerce")
        for c in ["forecast","p10","p90","p025","p975"]:f[c]=pd.to_numeric(f[c],errors="coerce")
        f=f.dropna(subset=["date","forecast"])
        if len(f):
            fig.add_trace(go.Scatter(x=f.date,y=f.p975,line=dict(width=0),showlegend=False,hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=f.date,y=f.p025,fill="tonexty",line=dict(width=0),name="95% CI",opacity=.12))
            fig.add_trace(go.Scatter(x=f.date,y=f.p90,line=dict(width=0),showlegend=False,hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=f.date,y=f.p10,fill="tonexty",line=dict(width=0),name="80% CI",opacity=.22))
            fig.add_trace(go.Scatter(x=f.date,y=f.forecast,mode="lines+markers",name="Forecast",line=dict(width=3,dash="dash")))
    fig.update_layout(title=title,height=430,yaxis_title=ytitle,legend_orientation="h",hovermode="x unified",margin=dict(l=20,r=20,t=55,b=20))
    return fig

cur_lpi=float(pd.to_numeric(daily.get("LPI"),errors="coerce").dropna().iloc[-1]) if len(daily) and "LPI" in daily and pd.to_numeric(daily["LPI"],errors="coerce").notna().any() else None
f5=float(lpi_fc.iloc[4].forecast) if len(lpi_fc)>=5 else None
f20=float(lpi_fc.iloc[19].forecast) if len(lpi_fc)>=20 else None

def state(x):
    if x is None or pd.isna(x):return "Không đủ dữ liệu"
    if x>=2:return "Căng thẳng cao"
    if x>=1:return "Căng thẳng vừa"
    if x>-1:return "Trung tính"
    return "Dư thừa"

with st.sidebar:
    st.subheader("TRẠNG THÁI HỆ THỐNG")
    valid_banks=int((pd.to_numeric(banks.get("MetricCoverage"),errors="coerce")>=.60).sum()) if len(banks) and "MetricCoverage" in banks else 0
    st.success(f"🟢 Bronze file: {len(banks)} ngân hàng") if len(banks) else st.warning("🟠 Chưa có Bronze bank file")
    st.write(f"Bronze đủ stress metrics: **{valid_banks}**")
    st.write(f"LPI model: **{summary.get('lpi',{}).get('status','NO_MODEL')}**")
    st.write(f"Interbank: **{summary.get('interbank',{}).get('status','NO_MODEL')}**")
    st.write(f"Interbank source: **{summary.get('interbank_source','NONE')}**")
    st.caption("Upgrade package không chứa data/, nên không ghi đè Bronze ACTUAL khi copy code mới.")

tabs=st.tabs(["Tổng quan","Thanh khoản hệ thống","Lãi suất liên ngân hàng","Ngân hàng & Funding Stress","Stress Lab","Diagnostics & dữ liệu"])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("LPI hiện tại",f"{cur_lpi:.2f}" if cur_lpi is not None else "N/A")
    c2.metric("Dự báo 1 tuần",f"{f5:.2f}" if f5 is not None else "N/A",delta=f"{f5-cur_lpi:+.2f}" if f5 is not None and cur_lpi is not None else None)
    c3.metric("Dự báo 1 tháng",f"{f20:.2f}" if f20 is not None else "N/A",delta=f"{f20-cur_lpi:+.2f}" if f20 is not None and cur_lpi is not None else None)
    c4.metric("Trạng thái 1 tháng",state(f20))
    if len(lpi_fc):
        st.plotly_chart(fan(daily,lpi_fc,"LPI","LPI — 12 tháng gần nhất & dự báo 20 ngày","LPI (z-score)",True),use_container_width=True)
        st.caption("Ngưỡng đọc nhanh: <−1 dư thừa | −1 đến 1 trung tính | 1–2 căng vừa | >2 căng cao. Dải 80%/95% phản ánh bất định dự báo.")
    else:
        st.warning("Chưa có LPI forecast. Chạy REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat.")
    d=summary.get("lpi",{})
    if d:
        st.markdown(f"**Mô hình:** {d.get('model','N/A')} · **RMSE:** {d.get('rmse','N/A')} · **Skill vs Naive:** {d.get('skill_vs_naive','N/A')}")

with tabs[1]:
    st.subheader("LPI và các drivers")
    if len(daily):
        cols=[c for c in ["ON_z","FX_z","OMO_z","LPI"] if c in daily.columns]
        t=daily[["date"]+cols].copy();t["date"]=pd.to_datetime(t["date"],errors="coerce")
        if len(t):t=t[t.date>=t.date.max()-pd.Timedelta(days=540)]
        fig=go.Figure()
        names={"ON_z":"ON/Interbank","FX_z":"FX pressure","OMO_z":"OMO pressure","LPI":"LPI"}
        for c in cols:
            fig.add_trace(go.Scatter(x=t.date,y=pd.to_numeric(t[c],errors="coerce"),mode="lines",name=names[c],line=dict(width=3 if c=="LPI" else 1.3),opacity=1 if c=="LPI" else .65))
        fig.add_hline(y=0,line_dash="dot",opacity=.4);fig.update_layout(height=430,hovermode="x unified",legend_orientation="h")
        st.plotly_chart(fig,use_container_width=True)
        st.caption("ON tăng → stress tăng; FX tăng nhanh → stress tăng; OMO bơm ròng → stress giảm. LPI cần tối thiểu 2 thành phần thực.")
    if len(regime):
        r=regime.copy();r["date"]=pd.to_datetime(r["date"],errors="coerce");r=r[r.date>=r.date.max()-pd.Timedelta(days=730)]
        fig=go.Figure()
        for c,n in [("P_Excess","Dư thừa"),("P_Neutral","Trung tính"),("P_Stress","Căng thẳng")]:
            if c in r:fig.add_trace(go.Scatter(x=r.date,y=pd.to_numeric(r[c],errors="coerce"),mode="lines",name=n))
        fig.update_layout(height=350,yaxis_range=[0,1],yaxis_tickformat=".0%",hovermode="x unified",legend_orientation="h",title="Xác suất chế độ thanh khoản — làm mượt 20 ngày")
        st.plotly_chart(fig,use_container_width=True)

with tabs[2]:
    st.subheader("Lãi suất liên ngân hàng")
    has_ib=len(daily) and "interbank" in daily and pd.to_numeric(daily["interbank"],errors="coerce").notna().any()
    if has_ib:
        if len(ib_fc):
            st.plotly_chart(fan(daily,ib_fc,"interbank","Lãi suất ON — Actual & Forecast","%/năm"),use_container_width=True)
        else:
            t=daily[["date","interbank"]].dropna().copy();t["date"]=pd.to_datetime(t.date);t=t[t.date>=t.date.max()-pd.Timedelta(days=365)]
            st.plotly_chart(px.line(t,x="date",y="interbank",title="Lãi suất ON thực — 12 tháng"),use_container_width=True)
            st.warning("Đã có interbank ACTUAL nhưng chưa đủ ngưỡng forecast.")
    else:
        st.warning("Chưa có chuỗi interbank thực. Hệ thống không dùng deposit/lending rate để giả làm interbank.")
        st.markdown("Nguồn ưu tiên: **Vnstock Bronze interbank_rate → data/interbank_manual.csv (ACTUAL/public)**.")
        if len(refresh):
            st.dataframe(safe(refresh[refresh.dataset.astype(str).str.contains("interbank",case=False,na=False)]),hide_index=True,use_container_width=True)

with tabs[3]:
    st.subheader("Funding Stress theo ngân hàng")
    if len(bank_fc):
        hs=list(bank_fc.Horizon.dropna().unique());h=st.selectbox("Horizon",hs,index=min(1,len(hs)-1))
        b=bank_fc[bank_fc.Horizon==h].copy()
        b["StressVulnerability"]=pd.to_numeric(b.StressVulnerability,errors="coerce")
        v=b.dropna(subset=["StressVulnerability"]).sort_values("StressVulnerability",ascending=False)
        if len(v):
            fig=px.bar(v,x="Ticker",y="StressVulnerability",color="Watch",hover_data=["Coverage","Data Type","Source Mode","FundingCostShock_ppt","StressedNIM"])
            fig.update_layout(height=430,yaxis_range=[0,105]);st.plotly_chart(fig,use_container_width=True)
            st.info(f"Bronze đủ coverage: **{int((v.SourceMode=='BRONZE').sum()) if 'SourceMode' in v else int((v['Source Mode']=='BRONZE').sum())}** · Fallback: **{int((v['Source Mode']=='FALLBACK').sum())}**")
        st.dataframe(safe(b),hide_index=True,use_container_width=True)
    else:st.warning("Chưa có bank stress output.")

with tabs[4]:
    st.subheader("Stress Lab")
    if len(bank_fc):
        b=bank_fc[bank_fc.Horizon=="Current"].copy();b["BaseVulnerability"]=pd.to_numeric(b.BaseVulnerability,errors="coerce");b=b.dropna(subset=["BaseVulnerability"])
        if len(b):
            shock=st.slider("Cú sốc LPI bổ sung",0.0,3.0,1.0,.1);passmax=st.slider("Funding cost pass-through tối đa (ppt)",.5,4.0,2.0,.25)
            b["ScenarioVulnerability"]=(b.BaseVulnerability*(1+.15*shock)).clip(0,100)
            b["ScenarioFundingCost_ppt"]=passmax*b.ScenarioVulnerability/100
            fig=px.bar(b.sort_values("ScenarioVulnerability",ascending=False),x="Ticker",y="ScenarioVulnerability",title="Vulnerability dưới kịch bản tùy chỉnh")
            fig.update_layout(height=430,yaxis_range=[0,105]);st.plotly_chart(fig,use_container_width=True)
            st.dataframe(safe(b[["Ticker","ScenarioVulnerability","ScenarioFundingCost_ppt","Data Type","Source Mode"]]),hide_index=True,use_container_width=True)
            st.caption("Stress Lab là scenario analysis. Slider là ASSUMPTION; dữ liệu nền vẫn ưu tiên Bronze ACTUAL khi đạt coverage.")
        else:st.error("Không có BaseVulnerability hợp lệ.")
    else:st.warning("Chưa có bank stress output.")

with tabs[5]:
    st.subheader("Model Diagnostics")
    st.dataframe(safe(diag),hide_index=True,use_container_width=True) if len(diag) else st.warning("Chưa có diagnostics.")
    st.subheader("Bronze Data Quality")
    if len(banks):
        show=[c for c in ["Ticker","LDR","CASA","InterbankDep","CreditDepositGap","NIM","MetricCoverage","ParseStatus"] if c in banks.columns]
        st.dataframe(safe(banks[show]),hide_index=True,use_container_width=True)
    if len(refresh):
        st.subheader("Refresh Log");st.dataframe(safe(refresh),hide_index=True,use_container_width=True)

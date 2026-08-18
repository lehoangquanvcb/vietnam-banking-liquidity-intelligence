
import streamlit as st
import pandas as pd, numpy as np, json
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

ROOT=Path(__file__).parent;DATA=ROOT/"data";OUT=DATA/"model_outputs"
st.set_page_config(page_title="Vietnam Banking Liquidity Intelligence",layout="wide")
st.markdown("""
<style>
.block-container{padding-top:2.7rem!important;padding-bottom:2.4rem}
h1{font-size:clamp(1.55rem,2.2vw,2.1rem)!important;line-height:1.3!important;margin:.1rem 0 .7rem!important}
[data-testid="stMetricValue"]{font-size:1.4rem}
div[data-testid="stTabs"] button{white-space:nowrap}
</style>
""",unsafe_allow_html=True)
st.title("TRUNG TÂM DỰ BÁO & PHÂN TÍCH THANH KHOẢN HỆ THỐNG NGÂN HÀNG")
st.caption("Bronze ACTUAL • Forecast Governance • Regime • Bank Funding Stress • Explainable Model")

def read_csv(p):
    try:return pd.read_csv(p)
    except:return pd.DataFrame()
def read_json(p):
    try:return json.loads(Path(p).read_text(encoding="utf-8"))
    except:return {}
def safe(df):
    x=df.copy()
    for c in x.columns:
        if x[c].dtype=="object":
            x[c]=x[c].map(lambda v:"" if pd.isna(v) else str(v))
    return x

banks=read_csv(DATA/"bank_actuals_bronze.csv")
daily=read_csv(OUT/"daily_liquidity_panel.csv")
lpi_fc=read_csv(OUT/"lpi_forecast.csv")
ib_fc=read_csv(OUT/"interbank_forecast.csv")
regime=read_csv(OUT/"regime_probabilities.csv")
bank_fc=read_csv(OUT/"bank_stress_forecast.csv")
diag=read_csv(OUT/"model_diagnostics.csv")
refresh=read_csv(DATA/"refresh_status.csv")
summary=read_json(OUT/"model_summary.json")

def finite_num(x):
    try:
        v=float(x)
        return v if np.isfinite(v) else None
    except:return None

def state(x):
    if x is None:return "Không đủ dữ liệu"
    if x>=2:return "Căng thẳng cao"
    if x>=1:return "Căng thẳng vừa"
    if x>-1:return "Trung tính"
    return "Dư thừa"

def fan(history,forecast,col,title,ytitle,lpi=False):
    fig=go.Figure()
    if len(history) and col in history.columns:
        h=history[["date",col]].copy()
        h["date"]=pd.to_datetime(h.date,errors="coerce");h[col]=pd.to_numeric(h[col],errors="coerce")
        h=h.dropna()
        if len(h):
            h=h[h.date>=h.date.max()-pd.Timedelta(days=365)]
            fig.add_trace(go.Scatter(x=h.date,y=h[col],mode="lines",name="Actual",line=dict(width=2.2)))
    if lpi:
        for y in [-1,1,2]:fig.add_hline(y=y,line_dash="dot",opacity=.35)
        fig.add_annotation(xref="paper",x=1.0,y=-1,text="Dư thừa",showarrow=False,xanchor="left")
        fig.add_annotation(xref="paper",x=1.0,y=0,text="Trung tính",showarrow=False,xanchor="left")
        fig.add_annotation(xref="paper",x=1.0,y=1.5,text="Căng vừa",showarrow=False,xanchor="left")
        fig.add_annotation(xref="paper",x=1.0,y=2.5,text="Căng cao",showarrow=False,xanchor="left")
    if len(forecast):
        f=forecast.copy();f["date"]=pd.to_datetime(f.date,errors="coerce")
        for c in ["forecast","p10","p90","p025","p975"]:f[c]=pd.to_numeric(f[c],errors="coerce")
        f=f.dropna(subset=["date","forecast"])
        if len(f):
            fig.add_trace(go.Scatter(x=f.date,y=f.p975,line=dict(width=0),showlegend=False,hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=f.date,y=f.p025,fill="tonexty",line=dict(width=0),name="95% CI",opacity=.12))
            fig.add_trace(go.Scatter(x=f.date,y=f.p90,line=dict(width=0),showlegend=False,hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=f.date,y=f.p10,fill="tonexty",line=dict(width=0),name="80% CI",opacity=.22))
            fig.add_trace(go.Scatter(x=f.date,y=f.forecast,mode="lines+markers",name="Forecast",line=dict(width=3,dash="dash")))
    fig.update_layout(title=title,height=430,yaxis_title=ytitle,legend_orientation="h",hovermode="x unified",margin=dict(l=20,r=70,t=55,b=20))
    return fig

lpi_hist=pd.to_numeric(daily["LPI"],errors="coerce").dropna() if len(daily) and "LPI" in daily.columns else pd.Series(dtype=float)
cur=finite_num(lpi_hist.iloc[-1]) if len(lpi_hist) else None
f5=finite_num(lpi_fc.iloc[4]["forecast"]) if len(lpi_fc)>=5 else None
f20=finite_num(lpi_fc.iloc[19]["forecast"]) if len(lpi_fc)>=20 else None

with st.sidebar:
    st.subheader("TRẠNG THÁI HỆ THỐNG")
    if len(banks):
        st.success(f"🟢 Bronze file: {len(banks)} ngân hàng")
    else:
        st.warning("🟠 Chưa có Bronze bank file")
    if len(banks) and "MetricCoverage" in banks.columns:
        coverage=pd.to_numeric(banks["MetricCoverage"],errors="coerce")
        valid=int((coverage>=.60).sum())
    else:
        valid=0
    st.write(f"Bronze đủ stress metrics: **{valid}**")
    st.write(f"LPI model: **{summary.get('lpi',{}).get('status','NO_MODEL')}**")
    st.write(f"Interbank model: **{summary.get('interbank',{}).get('status','NO_MODEL')}**")
    st.write(f"Interbank source: **{summary.get('interbank_source','NONE')}**")
    st.caption("Code-only upgrade: package không chứa data/, nên không ghi đè Bronze ACTUAL.")

tabs=st.tabs(["Tổng quan","Thanh khoản hệ thống","Lãi suất liên ngân hàng","Ngân hàng & Funding Stress","Stress Lab","Diagnostics & dữ liệu"])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("LPI hiện tại",f"{cur:.2f}" if cur is not None else "N/A")
    c2.metric("Dự báo 1 tuần",f"{f5:.2f}" if f5 is not None else "N/A",delta=f"{f5-cur:+.2f}" if f5 is not None and cur is not None else None)
    c3.metric("Dự báo 1 tháng",f"{f20:.2f}" if f20 is not None else "N/A",delta=f"{f20-cur:+.2f}" if f20 is not None and cur is not None else None)
    c4.metric("Trạng thái 1 tháng",state(f20))

    ld=summary.get("lpi",{})
    if ld.get("status")=="OK_BENCHMARK":
        st.warning("Mô hình ARIMA không thắng naive benchmark trong backtest. Production forecast đang dùng **NAIVE_RANDOM_WALK** và được gắn độ tin cậy LOW.")
    elif ld.get("status")=="OK":
        skill=finite_num(ld.get("skill_vs_naive"))
        if skill is not None:
            st.success(f"Forecast model thắng naive benchmark; Skill vs Naive = {skill:.1%}. Độ tin cậy: {ld.get('confidence_grade','N/A')}.")
    if len(lpi_fc):
        st.plotly_chart(fan(daily,lpi_fc,"LPI","LPI — 12 tháng gần nhất & dự báo 20 ngày","LPI (z-score)",True),use_container_width=True)
        st.caption("Ngưỡng đọc: <−1 dư thừa | −1–1 trung tính | 1–2 căng vừa | >2 căng cao. Dải 80%/95% là bất định dự báo.")
    else:
        st.warning("Chưa có LPI forecast. Chạy REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat.")

with tabs[1]:
    st.subheader("LPI và các động lực")
    if len(daily):
        cols=[c for c in ["ON_z","FX_z","OMO_z","LPI"] if c in daily.columns]
        if cols:
            t=daily[["date"]+cols].copy();t["date"]=pd.to_datetime(t.date,errors="coerce")
            t=t[t.date>=t.date.max()-pd.Timedelta(days=540)]
            fig=go.Figure()
            labels={"ON_z":"ON/Interbank","FX_z":"FX pressure","OMO_z":"OMO pressure","LPI":"LPI"}
            for c in cols:
                fig.add_trace(go.Scatter(x=t.date,y=pd.to_numeric(t[c],errors="coerce"),mode="lines",name=labels[c],line=dict(width=3 if c=="LPI" else 1.2),opacity=1 if c=="LPI" else .65))
            fig.add_hline(y=0,line_dash="dot",opacity=.4)
            fig.update_layout(height=430,hovermode="x unified",legend_orientation="h",title="Drivers — 18 tháng gần nhất")
            st.plotly_chart(fig,use_container_width=True)
            st.info("LPI chỉ được tính khi có ít nhất **2 thành phần ACTUAL**. ON tăng và FX pressure tăng làm stress cao hơn; OMO bơm ròng làm stress thấp hơn.")
    if len(regime):
        r=regime.copy();r["date"]=pd.to_datetime(r.date,errors="coerce");r=r[r.date>=r.date.max()-pd.Timedelta(days=730)]
        fig=go.Figure()
        for c,n in [("P_Excess","Dư thừa"),("P_Neutral","Trung tính"),("P_Stress","Căng thẳng")]:
            if c in r.columns:fig.add_trace(go.Scatter(x=r.date,y=pd.to_numeric(r[c],errors="coerce"),mode="lines",name=n))
        fig.update_layout(height=350,yaxis_range=[0,1],yaxis_tickformat=".0%",hovermode="x unified",legend_orientation="h",title="Xác suất chế độ — làm mượt 20 ngày")
        st.plotly_chart(fig,use_container_width=True)

with tabs[2]:
    st.subheader("Lãi suất liên ngân hàng")
    has_ib=len(daily) and "interbank" in daily.columns and pd.to_numeric(daily["interbank"],errors="coerce").notna().any()
    if has_ib:
        if len(ib_fc):
            st.plotly_chart(fan(daily,ib_fc,"interbank","Lãi suất ON — Actual & Forecast","%/năm"),use_container_width=True)
            idg=summary.get("interbank",{})
            if idg.get("status")=="OK_BENCHMARK":
                st.warning("ARIMA không thắng naive benchmark; đang dùng benchmark với confidence LOW.")
        else:
            t=daily[["date","interbank"]].dropna().copy();t["date"]=pd.to_datetime(t.date,errors="coerce")
            t=t[t.date>=t.date.max()-pd.Timedelta(days=365)]
            st.plotly_chart(px.line(t,x="date",y="interbank",title="Lãi suất ON thực — 12 tháng"),use_container_width=True)
            st.warning("Đã có interbank ACTUAL nhưng chưa đủ ngưỡng forecast.")
    else:
        st.warning("Chưa có chuỗi interbank thực. Hệ thống **không dùng deposit/lending rate để giả làm interbank**.")
        st.markdown("Nguồn ưu tiên: **Vnstock true interbank → `data/interbank_manual.csv` ACTUAL/public**.")
        if len(refresh) and "dataset" in refresh.columns:
            ir=refresh[refresh.dataset.astype(str).str.contains("interbank",case=False,na=False)]
            if len(ir):st.dataframe(safe(ir),hide_index=True,use_container_width=True)

with tabs[3]:
    st.subheader("Funding Stress theo ngân hàng")
    if len(bank_fc):
        hs=list(bank_fc["Horizon"].dropna().unique())
        h=st.selectbox("Horizon",hs,index=min(1,len(hs)-1))
        b=bank_fc[bank_fc.Horizon==h].copy()
        b["StressVulnerability"]=pd.to_numeric(b.StressVulnerability,errors="coerce")
        valid=b.dropna(subset=["StressVulnerability"]).sort_values("StressVulnerability",ascending=False)
        if len(valid):
            fig=px.bar(valid,x="Ticker",y="StressVulnerability",color="Watch",hover_data=["Coverage","Data Type","Source Mode","FundingCostShock_ppt","StressedNIM"])
            fig.update_layout(height=430,yaxis_range=[0,105]);st.plotly_chart(fig,use_container_width=True)
            bronze_used=int((valid["Source Mode"]=="BRONZE").sum())
            fallback_used=int((valid["Source Mode"]=="FALLBACK").sum())
            st.info(f"Stress model dùng **{bronze_used} Bronze đủ coverage** và **{fallback_used} fallback ASSUMPTION**. Không có dòng rỗng được chấm điểm.")
        else:
            st.error("Không có dòng StressVulnerability hợp lệ. Hãy chạy lại BAT để tái xây dựng model outputs.")
        st.dataframe(safe(b),hide_index=True,use_container_width=True)
    else:
        st.warning("Chưa có bank stress output.")

with tabs[4]:
    st.subheader("Stress Lab")
    if len(bank_fc):
        b=bank_fc[bank_fc.Horizon=="Current"].copy()
        b["BaseVulnerability"]=pd.to_numeric(b.BaseVulnerability,errors="coerce")
        b=b.dropna(subset=["BaseVulnerability"])
        if len(b):
            shock=st.slider("Cú sốc LPI bổ sung",0.0,3.0,1.0,.1)
            passmax=st.slider("Funding cost pass-through tối đa (ppt)",.5,4.0,2.0,.25)
            b["ScenarioVulnerability"]=(b.BaseVulnerability*(1+.15*shock)).clip(0,100)
            b["ScenarioFundingCost_ppt"]=passmax*b.ScenarioVulnerability/100
            fig=px.bar(b.sort_values("ScenarioVulnerability",ascending=False),x="Ticker",y="ScenarioVulnerability",color="Source Mode",title="Vulnerability dưới kịch bản tùy chỉnh")
            fig.update_layout(height=430,yaxis_range=[0,105]);st.plotly_chart(fig,use_container_width=True)
            st.dataframe(safe(b[["Ticker","ScenarioVulnerability","ScenarioFundingCost_ppt","Data Type","Source Mode"]]),hide_index=True,use_container_width=True)
            st.caption("Stress Lab là scenario analysis. Slider là ASSUMPTION; nền dữ liệu ưu tiên Bronze ACTUAL nếu coverage đạt ngưỡng.")
        else:
            st.error("Không có BaseVulnerability hợp lệ. Chạy lại BAT mới; model sẽ fallback ticker-level nếu Bronze chưa đủ coverage.")
    else:
        st.warning("Chưa có bank stress output.")

with tabs[5]:
    st.subheader("Model Diagnostics")
    if len(diag):
        st.dataframe(safe(diag),hide_index=True,use_container_width=True)
    else:
        st.warning("Chưa có diagnostics.")
    st.markdown("**Governance:** ARIMA chỉ được dùng nếu RMSE holdout thấp hơn naive benchmark. Nếu không, model tự chuyển sang `NAIVE_RANDOM_WALK` và confidence = LOW.")
    st.subheader("Bronze Data Quality")
    if len(banks):
        cols=[c for c in ["Ticker","LDR","CASA","InterbankDep","CreditDepositGap","NIM","MetricCoverage","ParseStatus"] if c in banks.columns]
        st.dataframe(safe(banks[cols]),hide_index=True,use_container_width=True)
    if len(refresh):
        st.subheader("Refresh Log")
        st.dataframe(safe(refresh),hide_index=True,use_container_width=True)

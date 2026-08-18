
import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

ROOT=Path(__file__).parent
DATA=ROOT/"data"
OUT=DATA/"model_outputs"

st.set_page_config(page_title="Vietnam Banking Liquidity Intelligence",layout="wide")

st.markdown("""
<style>
.block-container{padding-top:2.4rem;padding-bottom:2.5rem}
[data-testid="stMetricValue"]{font-size:1.45rem}
h1{font-size:clamp(1.55rem,2.3vw,2.15rem)!important;line-height:1.28!important;margin-top:.35rem!important;padding-top:.25rem!important}
h2{font-size:1.35rem!important}
.smallnote{font-size:.88rem;color:#888}
div[data-testid="stTabs"] button{white-space:nowrap}
</style>
""",unsafe_allow_html=True)

st.title("TRUNG TÂM DỰ BÁO & PHÂN TÍCH THANH KHOẢN HỆ THỐNG NGÂN HÀNG")
st.caption("Vnstock Bronze Data Pipeline • Forecast • Regime • Stress Test • Explainable Banking Intelligence")

def load_csv(path):
    p=Path(path)
    try:return pd.read_csv(p)
    except:return pd.DataFrame()

def load_json(path):
    p=Path(path)
    try:return json.loads(p.read_text(encoding="utf-8"))
    except:return {}

def safe_df(df):
    x=df.copy()
    for c in x.columns:
        if x[c].dtype=="object":
            x[c]=x[c].map(lambda v:"" if pd.isna(v) else str(v))
    return x

def state_badge(state):
    mapping={"Căng thẳng cao":"🔴","Căng thẳng vừa":"🟠","Trung tính":"🟢","Dư thừa thanh khoản":"🔵","Không đủ dữ liệu":"⚪"}
    return f"{mapping.get(state,'⚪')} {state}"

def fan_chart(history,forecast,hist_col,title,ytitle,is_lpi=False):
    fig=go.Figure()
    if len(history):
        h=history.dropna(subset=["date",hist_col]).copy()
        h["date"]=pd.to_datetime(h["date"])
        # Forecast view should prioritize the recent decision horizon, not the whole multi-year history.
        cutoff=h["date"].max()-pd.Timedelta(days=365)
        h=h[h["date"]>=cutoff]
        fig.add_trace(go.Scatter(x=h["date"],y=h[hist_col],mode="lines",name="Actual",line=dict(width=2)))
    if is_lpi:
        # Economic reading bands.
        fig.add_hrect(y0=-5,y1=-1,opacity=.06,line_width=0,annotation_text="Dư thừa")
        fig.add_hrect(y0=-1,y1=1,opacity=.03,line_width=0,annotation_text="Trung tính")
        fig.add_hrect(y0=1,y1=2,opacity=.05,line_width=0,annotation_text="Căng vừa")
        fig.add_hrect(y0=2,y1=8,opacity=.07,line_width=0,annotation_text="Căng cao")
        for y in [-1,1,2]:
            fig.add_hline(y=y,line_dash="dot",opacity=.45)
    if len(forecast):
        f=forecast.copy()
        f["date"]=pd.to_datetime(f["date"])
        fig.add_trace(go.Scatter(x=f["date"],y=f["p975"],line=dict(width=0),showlegend=False,hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=f["date"],y=f["p025"],fill="tonexty",line=dict(width=0),name="95% CI",opacity=.12))
        fig.add_trace(go.Scatter(x=f["date"],y=f["p90"],line=dict(width=0),showlegend=False,hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=f["date"],y=f["p10"],fill="tonexty",line=dict(width=0),name="80% CI",opacity=.22))
        fig.add_trace(go.Scatter(x=f["date"],y=f["forecast"],mode="lines+markers",name="Forecast",line=dict(width=3,dash="dash")))
    fig.update_layout(
        title=title,yaxis_title=ytitle,xaxis_title="",height=430,legend_orientation="h",
        hovermode="x unified",margin=dict(l=20,r=20,t=55,b=20)
    )
    return fig

daily=load_csv(OUT/"daily_liquidity_panel.csv")
lpi_fc=load_csv(OUT/"lpi_forecast.csv")
ib_fc=load_csv(OUT/"interbank_forecast.csv")
drivers=load_csv(OUT/"drivers.csv")
regime=load_csv(OUT/"regime_probabilities.csv")
bank_fc=load_csv(OUT/"bank_stress_forecast.csv")
diag=load_csv(OUT/"model_diagnostics.csv")
var_fc=load_csv(OUT/"monthly_var_forecast.csv")
refresh=load_csv(DATA/"refresh_status.csv")
actual_banks=load_csv(DATA/"bank_actuals_bronze.csv")
explain=load_json(OUT/"explanation.json")
summary=load_json(OUT/"model_summary.json")

bronze_count=len(actual_banks) if len(actual_banks) else 0
last_update=""
if len(actual_banks) and "Retrieved At" in actual_banks.columns:
    ts=pd.to_datetime(actual_banks["Retrieved At"],errors="coerce").max()
    if pd.notna(ts):last_update=str(ts)

with st.sidebar:
    st.subheader("TRẠNG THÁI HỆ THỐNG")
    if bronze_count:
        st.success(f"🟢 Bronze ACTUAL: {bronze_count} ngân hàng")
    else:
        st.warning("🟠 Chưa có Bronze ACTUAL")
    if last_update:st.caption(f"Cập nhật: {last_update}")
    lpi_status=summary.get("lpi",{}).get("status","NO_MODEL")
    st.write(f"LPI model: **{lpi_status}**")
    st.write(f"Interbank model: **{summary.get('interbank',{}).get('status','NO_MODEL')}**")
    st.write(f"Regime model: **{summary.get('regime',{}).get('status','NO_MODEL')}**")
    st.divider()
    st.caption("Bronze acquisition chạy trên máy/self-hosted runner; Streamlit chỉ đọc ACTUAL CSV + model outputs từ GitHub.")

tabs=st.tabs([
    "Tổng quan dự báo",
    "Thanh khoản hệ thống",
    "Lãi suất liên ngân hàng",
    "Ngân hàng & Funding Stress",
    "Kịch bản Stress",
    "Giải thích mô hình",
    "Diagnostics & dữ liệu"
])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    cur=explain.get("current_lpi")
    f5=explain.get("forecast_5d")
    f20=explain.get("forecast_20d")
    c1.metric("LPI hiện tại",f"{cur:.2f}" if cur is not None else "N/A")
    c2.metric("Dự báo 1 tuần",f"{f5:.2f}" if f5 is not None else "N/A",
              delta=(f"{f5-cur:+.2f}" if f5 is not None and cur is not None else None))
    c3.metric("Dự báo 1 tháng",f"{f20:.2f}" if f20 is not None else "N/A",
              delta=(f"{f20-cur:+.2f}" if f20 is not None and cur is not None else None))
    c4.metric("Trạng thái 1 tháng",explain.get("forecast_20d_state","N/A"))

    if explain:
        st.info(f"**Đánh giá:** {state_badge(explain.get('current_state','Không đủ dữ liệu'))} → "
                f"1 tuần: **{explain.get('forecast_5d_state','N/A')}** → "
                f"1 tháng: **{explain.get('forecast_20d_state','N/A')}**.")

    if len(daily) and len(lpi_fc):
        st.plotly_chart(fan_chart(daily,lpi_fc,"LPI","LPI — 12 tháng gần nhất & dự báo 20 ngày","LPI (z-score)",is_lpi=True),
                        use_container_width=True)
        st.caption("Ngưỡng đọc nhanh: <−1 dư thừa | −1 đến 1 trung tính | 1–2 căng vừa | >2 căng cao. Vùng xanh/đỏ là dải bất định 80%/95%, không phải kịch bản chắc chắn.")

    col1,col2=st.columns([1.2,1])
    with col1:
        st.subheader("Các động lực chính")
        if len(drivers):
            chart=px.bar(drivers.head(6).sort_values("Contribution z"),x="Contribution z",y="Driver",orientation="h",
                         title="Đóng góp hiện tại vào áp lực thanh khoản")
            chart.update_layout(height=330,margin=dict(l=20,r=20,t=50,b=20))
            st.plotly_chart(chart,use_container_width=True)
        else:
            st.warning("Chưa đủ dữ liệu để xác định drivers.")
    with col2:
        st.subheader("Kết luận điều hành")
        if explain:
            st.markdown(f"""
**Mô hình được chọn:** {explain.get('selected_model','N/A')}

**Tại sao mô hình ra kết quả này?**  
Các drivers có độ lệch chuẩn lớn nhất đang quyết định hướng của LPI. Mô hình không dùng một con số giả định cố định mà chọn ARIMA có RMSE ngoài mẫu thấp nhất.

**Kết quả nói lên điều gì?**  
{explain.get('so_what','')}

**Độ tin cậy:**  
{explain.get('confidence','')}
""")
        else:
            st.warning("Chưa có model explanation. Chạy scripts/build_models.py.")

with tabs[1]:
    st.subheader("Liquidity Pressure Index (LPI)")
    st.markdown("""
LPI là chỉ số tổng hợp chuẩn hóa từ **lãi suất liên ngân hàng, áp lực tỷ giá và OMO**.  
Giá trị dương cao hơn = thanh khoản căng hơn; giá trị âm = thanh khoản dư thừa hơn.
""")
    if len(daily):
        cols=[c for c in ["ON_z","FX_z","OMO_z","LPI"] if c in daily.columns]
        if cols:
            temp=daily[["date"]+cols].copy()
            temp["date"]=pd.to_datetime(temp["date"])
            cutoff=temp["date"].max()-pd.Timedelta(days=540)
            temp=temp[temp["date"]>=cutoff]
            fig=go.Figure()
            labels={"ON_z":"ON/Interbank","FX_z":"FX pressure","OMO_z":"OMO pressure","LPI":"LPI"}
            for c in cols:
                width=3 if c=="LPI" else 1.35
                opacity=1 if c=="LPI" else .65
                fig.add_trace(go.Scatter(x=temp["date"],y=temp[c],mode="lines",name=labels.get(c,c),
                                         line=dict(width=width),opacity=opacity))
            fig.add_hline(y=0,line_dash="dot",opacity=.4)
            fig.update_layout(height=430,title="LPI và drivers — 18 tháng gần nhất",legend_orientation="h",hovermode="x unified")
            st.plotly_chart(fig,use_container_width=True)
            st.caption("ON/Interbank tăng → tăng stress; FX tăng nhanh → tăng stress; OMO bơm ròng → giảm stress. LPI là đường tổng hợp đậm.")

    if len(regime):
        st.subheader("Xác suất chế độ thanh khoản")
        r=regime.copy();r["date"]=pd.to_datetime(r["date"])
        r=r[r["date"]>=r["date"].max()-pd.Timedelta(days=730)]
        fig=go.Figure()
        names={"P_Excess":"Dư thừa","P_Neutral":"Trung tính","P_Stress":"Căng thẳng"}
        for c in ["P_Excess","P_Neutral","P_Stress"]:
            if c in r:
                fig.add_trace(go.Scatter(x=r["date"],y=r[c],mode="lines",name=names[c],line=dict(width=2)))
        fig.update_layout(height=350,yaxis_tickformat=".0%",yaxis_range=[0,1],
                          title="Markov regime probabilities — xác suất làm mượt 20 ngày",
                          hovermode="x unified",legend_orientation="h")
        st.plotly_chart(fig,use_container_width=True)
        st.caption("Xác suất đã được làm mượt 20 ngày để nhìn xu hướng chế độ, thay vì các chuyển trạng thái nhiễu theo từng ngày.")

    if len(var_fc):
        st.subheader("Triển vọng trung hạn 1–3 tháng")
        st.dataframe(safe_df(var_fc),hide_index=True,use_container_width=True)
        st.caption("VAR chỉ chạy khi có đủ chuỗi tháng thực. Các biến được chuyển sang sai phân/log-change trước khi ước lượng để giảm rủi ro hồi quy giả.")

with tabs[2]:
    st.subheader("Dự báo lãi suất liên ngân hàng")
    has_ib=len(daily) and "interbank_bronze" in daily.columns and pd.to_numeric(daily["interbank_bronze"],errors="coerce").notna().any()
    if has_ib:
        if len(ib_fc):
            st.plotly_chart(fan_chart(daily,ib_fc,"interbank_bronze","Lãi suất liên ngân hàng — Actual & Forecast","%/năm"),
                            use_container_width=True)
            d=summary.get("interbank",{})
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Model",d.get("model","N/A"))
            c2.metric("Quan sát",d.get("nobs","N/A"))
            c3.metric("RMSE",f"{d.get('rmse'):.3f}" if isinstance(d.get("rmse"),(int,float)) else "N/A")
            c4.metric("Skill vs Naive",f"{d.get('skill_vs_naive'):.1%}" if isinstance(d.get("skill_vs_naive"),(int,float)) else "N/A")
            st.caption("Forecast chỉ được công bố khi đủ dữ liệu thực và qua production gate. Skill > 0 nghĩa là tốt hơn benchmark giữ nguyên mức gần nhất.")
        else:
            temp=daily[["date","interbank_bronze"]].dropna().copy()
            temp["date"]=pd.to_datetime(temp["date"])
            temp=temp[temp["date"]>=temp["date"].max()-pd.Timedelta(days=365)]
            fig=px.line(temp,x="date",y="interbank_bronze",title="Lãi suất liên ngân hàng — dữ liệu thực 12 tháng")
            fig.update_layout(height=420,hovermode="x unified",yaxis_title="%/năm")
            st.plotly_chart(fig,use_container_width=True)
            st.warning("Đã có dữ liệu interbank thực nhưng chưa đủ production gate để forecast.")
    else:
        st.warning("Chưa lấy được chuỗi interbank thực. Refresh mới sẽ thử lần lượt `interbank_rate`, `currency.interest_rate` và legacy `interest_rate`; không tạo chuỗi giả.")
        if len(refresh):
            ir=refresh[refresh["dataset"].astype(str).str.contains("interbank",case=False,na=False)]
            if len(ir):
                st.dataframe(safe_df(ir),hide_index=True,use_container_width=True)

with tabs[3]:
    st.subheader("Funding Stress theo ngân hàng")
    if len(bank_fc):
        horizons=list(bank_fc["Horizon"].dropna().unique())
        h=st.selectbox("Horizon",horizons,index=min(1,len(horizons)-1) if horizons else 0)
        b=bank_fc[bank_fc["Horizon"]==h].copy()
        b["StressVulnerability"]=pd.to_numeric(b["StressVulnerability"],errors="coerce")
        b["Coverage"]=pd.to_numeric(b.get("Coverage"),errors="coerce")
        valid=b.dropna(subset=["StressVulnerability"]).sort_values("StressVulnerability",ascending=False)
        if len(valid):
            fig=px.bar(valid,x="Ticker",y="StressVulnerability",color="Watch",
                       title=f"Bank Stress Vulnerability — {h}",
                       hover_data=["FundingCostShock_ppt","StressedNIM","Data Type","Source Mode","Coverage"])
            fig.update_layout(height=430,yaxis_range=[0,max(100,float(valid["StressVulnerability"].max())*1.08)])
            st.plotly_chart(fig,use_container_width=True)
            bronze_used=int((valid["Source Mode"]=="BRONZE").sum())
            fallback_used=int((valid["Source Mode"]=="FALLBACK").sum())
            st.info(f"Mô hình đang dùng **{bronze_used} ngân hàng Bronze đủ coverage** và **{fallback_used} fallback ASSUMPTION**. Bronze chỉ được dùng khi có ít nhất 3/5 chỉ tiêu định lượng.")
        else:
            st.error("Bank stress chưa có dòng nào đủ dữ liệu định lượng. Chạy lại BAT mới để model tự fallback các ticker Bronze chưa parse đủ LDR/CASA/NIM.")
        st.dataframe(safe_df(b),hide_index=True,use_container_width=True)
        st.markdown("""
**Cách đọc:** 0–60 tương đối thấp; 60–75 cần theo dõi; ≥75 là vùng stress cao theo rule của mô hình.  
Điểm chịu tác động của **LDR, CASA, phụ thuộc liên ngân hàng, credit–deposit gap, NIM** và LPI dự báo.
""")
    else:
        st.warning("Chưa có bank stress forecast. Chạy REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat.")

with tabs[4]:
    st.subheader("Stress Lab")
    if len(bank_fc):
        base_now=bank_fc[bank_fc["Horizon"]=="Current"].copy()
        base_now["BaseVulnerability"]=pd.to_numeric(base_now["BaseVulnerability"],errors="coerce")
        base_now["StressedNIM"]=pd.to_numeric(base_now["StressedNIM"],errors="coerce")
        base_now["FundingCostShock_ppt"]=pd.to_numeric(base_now["FundingCostShock_ppt"],errors="coerce")
        base_now=base_now.dropna(subset=["BaseVulnerability"])
        if len(base_now):
            lpi_shock=st.slider("Cú sốc LPI bổ sung",0.0,3.0,1.0,.1)
            funding_cap=st.slider("Funding cost pass-through tối đa (ppt)",0.5,4.0,2.0,.25)
            sim=base_now.copy()
            sim["ScenarioVulnerability"]=(sim["BaseVulnerability"]*(1+.15*lpi_shock)).clip(0,100)
            sim["ScenarioFundingCost_ppt"]=funding_cap*sim["ScenarioVulnerability"]/100
            current_nim=np.maximum(0,sim["StressedNIM"]+sim["FundingCostShock_ppt"]/100)
            sim["ScenarioNIM"]=np.maximum(0,current_nim-sim["ScenarioFundingCost_ppt"]/100)
            sim["ScenarioWatch"]=np.select(
                [(sim["ScenarioVulnerability"]>=75)|(sim["ScenarioNIM"]<.02),sim["ScenarioVulnerability"]>=60],
                ["RED","AMBER"],default="GREEN"
            )
            fig=px.bar(sim.sort_values("ScenarioVulnerability",ascending=False),x="Ticker",y="ScenarioVulnerability",
                       color="ScenarioWatch",title="Vulnerability dưới kịch bản stress tùy chỉnh")
            fig.update_layout(height=430,yaxis_range=[0,105])
            st.plotly_chart(fig,use_container_width=True)
            st.dataframe(safe_df(sim[["Ticker","ScenarioVulnerability","ScenarioFundingCost_ppt","ScenarioNIM","ScenarioWatch","Data Type","Source Mode"]]),
                         hide_index=True,use_container_width=True)
            st.caption("Đây là scenario analysis, không phải forecast xác suất. Slider là ASSUMPTION; dữ liệu nền vẫn tuân theo Bronze ACTUAL → fallback nếu thiếu.")
        else:
            st.error("Không có BaseVulnerability hợp lệ. Chạy lại BAT mới để tái xây dựng bank stress với ticker-level fallback.")
    else:
        st.warning("Chưa có dữ liệu để mô phỏng.")

with tabs[5]:
    st.subheader("Mô hình nào đang được dùng và vì sao?")
    if explain:
        st.markdown(f"""
### 1. LPI Forecast
**Model:** `{explain.get('selected_model','N/A')}`

**Lý do chọn:** {explain.get('why_model','')}

**Ý nghĩa:** LPI không dự báo trực tiếp “tiền dư/thừa bao nhiêu tỷ đồng”; nó đo **áp lực tương đối** của hệ thống so với lịch sử gần đây.

### 2. Regime Model
**Markov Switching 3 trạng thái:** Excess / Neutral / Stress.  
Mô hình phù hợp vì thanh khoản ngân hàng có tính “chế độ”: cùng một mức ON rate có thể mang ý nghĩa khác trong giai đoạn bình thường và giai đoạn FX stress.

### 3. Bank Stress Transmission
LPI dự báo được truyền xuống từng ngân hàng qua cấu trúc funding.  
Ngân hàng **LDR cao, CASA thấp, phụ thuộc liên ngân hàng cao và NIM buffer thấp** sẽ có độ nhạy lớn hơn.

### 4. Độ tin cậy
{explain.get('confidence','')}

### 5. Khi nào forecast có thể sai?
{explain.get('caveats','')}
""")
        if explain.get("top_drivers"):
            st.subheader("Drivers tại thời điểm gần nhất")
            st.dataframe(safe_df(pd.DataFrame(explain["top_drivers"])),hide_index=True,use_container_width=True)
    else:
        st.warning("Chưa có explanation.json.")

with tabs[6]:
    st.subheader("Model Diagnostics")
    if len(diag):
        st.dataframe(safe_df(diag),hide_index=True,use_container_width=True)
        st.markdown("""
**Các chỉ tiêu chính**
- **RMSE / MAE:** sai số dự báo ngoài mẫu; càng thấp càng tốt.
- **Naive RMSE:** benchmark giữ nguyên giá trị cuối cùng.
- **Skill vs Naive:** >0 là mô hình tốt hơn benchmark; <0 là mô hình chưa tạo giá trị.
- **AIC/BIC:** dùng để so sánh độ phù hợp có phạt độ phức tạp, không phải thước đo duy nhất.
""")
    st.subheader("Chất lượng dữ liệu Bronze")
    if len(refresh):
        st.dataframe(safe_df(refresh),hide_index=True,use_container_width=True)
    st.caption("Mô hình không synthetic-fill chuỗi production. Nếu dữ liệu không đủ, trạng thái sẽ là INSUFFICIENT_ACTUAL_HISTORY.")

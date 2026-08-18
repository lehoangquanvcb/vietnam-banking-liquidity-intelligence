
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
.block-container{padding-top:1rem;padding-bottom:2rem}
[data-testid="stMetricValue"]{font-size:1.45rem}
h1{font-size:1.9rem!important}
h2{font-size:1.35rem!important}
.smallnote{font-size:.88rem;color:#888}
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

def fan_chart(history,forecast,hist_col,title,ytitle):
    fig=go.Figure()
    if len(history):
        h=history.dropna(subset=["date",hist_col]).tail(180)
        fig.add_trace(go.Scatter(x=pd.to_datetime(h["date"]),y=h[hist_col],mode="lines",name="Actual"))
    if len(forecast):
        f=forecast.copy()
        f["date"]=pd.to_datetime(f["date"])
        fig.add_trace(go.Scatter(x=f["date"],y=f["p975"],line=dict(width=0),showlegend=False,hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=f["date"],y=f["p025"],fill="tonexty",line=dict(width=0),name="95% CI",opacity=.15))
        fig.add_trace(go.Scatter(x=f["date"],y=f["p90"],line=dict(width=0),showlegend=False,hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=f["date"],y=f["p10"],fill="tonexty",line=dict(width=0),name="80% CI",opacity=.25))
        fig.add_trace(go.Scatter(x=f["date"],y=f["forecast"],mode="lines+markers",name="Forecast"))
    fig.update_layout(title=title,yaxis_title=ytitle,xaxis_title="",height=420,legend_orientation="h",margin=dict(l=20,r=20,t=50,b=20))
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
        st.plotly_chart(fan_chart(daily,lpi_fc,"LPI","Liquidity Pressure Index — Actual & Forecast","LPI (z-score composite)"),
                        use_container_width=True)

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
            fig=go.Figure()
            for c in cols:
                fig.add_trace(go.Scatter(x=temp["date"],y=temp[c],mode="lines",name=c))
            fig.update_layout(height=430,title="LPI và các thành phần chuẩn hóa",legend_orientation="h")
            st.plotly_chart(fig,use_container_width=True)

    if len(regime):
        st.subheader("Xác suất chế độ thanh khoản")
        r=regime.copy();r["date"]=pd.to_datetime(r["date"])
        fig=go.Figure()
        for c in ["P_Excess","P_Neutral","P_Stress"]:
            if c in r:fig.add_trace(go.Scatter(x=r["date"],y=r[c],stackgroup="one",name=c))
        fig.update_layout(height=350,yaxis_tickformat=".0%",title="Markov-switching regime probabilities")
        st.plotly_chart(fig,use_container_width=True)
        st.caption("Mô hình Markov Switching cho phép trạng thái thanh khoản chuyển đổi theo xác suất thay vì ép hệ thống vào một ngưỡng cố định.")

    if len(var_fc):
        st.subheader("Triển vọng trung hạn 1–3 tháng")
        st.dataframe(safe_df(var_fc),hide_index=True,use_container_width=True)
        st.caption("VAR chỉ chạy khi có đủ chuỗi tháng thực. Các biến được chuyển sang sai phân/log-change trước khi ước lượng để giảm rủi ro hồi quy giả.")

with tabs[2]:
    st.subheader("Dự báo lãi suất liên ngân hàng")
    if len(daily) and "interbank_bronze" in daily.columns and len(ib_fc):
        st.plotly_chart(fan_chart(daily,ib_fc,"interbank_bronze","Lãi suất ON — Actual & Forecast","Lãi suất"),
                        use_container_width=True)
        d=summary.get("interbank",{})
        st.markdown(f"""
**Mô hình:** {d.get('model','N/A')}  
**Số quan sát:** {d.get('nobs','N/A')}  
**RMSE backtest:** {d.get('rmse','N/A')}  
**RMSE naive:** {d.get('naive_rmse','N/A')}  

Mô hình được lựa chọn theo sai số dự báo ngoài mẫu. Nếu `Skill vs Naive > 0`, mô hình tạo thêm giá trị so với việc đơn giản giữ nguyên lãi suất cuối kỳ.
""")
    else:
        st.warning("Interbank live hiện chưa đủ/endpoint đang lỗi. Hệ thống không tự tạo chuỗi giả; forecast ON chỉ xuất hiện khi dữ liệu thực đạt ngưỡng.")

with tabs[3]:
    st.subheader("Funding Stress theo ngân hàng")
    if len(bank_fc):
        horizons=list(bank_fc["Horizon"].dropna().unique())
        h=st.selectbox("Horizon",horizons,index=min(1,len(horizons)-1) if horizons else 0)
        b=bank_fc[bank_fc["Horizon"]==h].sort_values("StressVulnerability",ascending=False)
        fig=px.bar(b,x="Ticker",y="StressVulnerability",color="Watch",
                   title=f"Bank Stress Vulnerability — {h}",hover_data=["FundingCostShock_ppt","StressedNIM","Data Type"])
        fig.update_layout(height=420)
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(safe_df(b),hide_index=True,use_container_width=True)
        st.markdown("""
**Cách đọc:** điểm càng cao nghĩa là ngân hàng càng nhạy với cú sốc thanh khoản hệ thống.  
Điểm chịu tác động của LDR, CASA, phụ thuộc nguồn vốn liên ngân hàng, credit–deposit gap, NIM và LPI dự báo.
""")
    else:
        st.warning("Chưa có bank stress forecast.")

with tabs[4]:
    st.subheader("Stress Lab")
    if len(bank_fc):
        base_now=bank_fc[bank_fc["Horizon"]=="Current"].copy()
        lpi_shock=st.slider("Cú sốc LPI bổ sung",0.0,3.0,1.0,.1)
        funding_cap=st.slider("Funding cost pass-through tối đa (ppt)",0.5,4.0,2.0,.25)
        # Re-scale using current base vulnerability.
        sim=base_now.copy()
        sim["ScenarioVulnerability"]=(sim["BaseVulnerability"]*(1+.15*lpi_shock)).clip(0,100)
        sim["ScenarioFundingCost_ppt"]=funding_cap*sim["ScenarioVulnerability"]/100
        sim["ScenarioNIM"]=np.maximum(0,pd.to_numeric(sim["StressedNIM"],errors="coerce")+pd.to_numeric(sim["FundingCostShock_ppt"],errors="coerce")/100-sim["ScenarioFundingCost_ppt"]/100)
        fig=px.bar(sim.sort_values("ScenarioVulnerability",ascending=False),x="Ticker",y="ScenarioVulnerability",
                   title="Vulnerability dưới kịch bản stress tùy chỉnh")
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(safe_df(sim[["Ticker","ScenarioVulnerability","ScenarioFundingCost_ppt","ScenarioNIM","Data Type","Source Mode"]]),
                     hide_index=True,use_container_width=True)
        st.caption("Stress Lab là mô phỏng kịch bản, không phải forecast xác suất. Các slider là ASSUMPTION và được tách khỏi dữ liệu ACTUAL.")
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

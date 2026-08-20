from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "model_outputs"

st.set_page_config(page_title="Vietnam Banking Liquidity Intelligence", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:2.5rem;padding-bottom:2rem}
h1{font-size:clamp(1.55rem,2.2vw,2.15rem)!important;line-height:1.3!important;margin:.1rem 0 .6rem!important}
[data-testid="stMetricValue"]{font-size:1.4rem}
div[data-testid="stTabs"] button{white-space:nowrap}
</style>
""", unsafe_allow_html=True)

st.title("TRUNG TÂM DỰ BÁO & PHÂN TÍCH THANH KHOẢN HỆ THỐNG NGÂN HÀNG")
st.caption("Bronze ACTUAL • Forecast Governance • Liquidity Regime • Bank Funding Stress")


def csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def js(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def safe(df):
    x = df.copy()
    for c in x.columns:
        if x[c].dtype == "object":
            x[c] = x[c].map(lambda v: "" if pd.isna(v) else str(v))
    return x


def num(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except Exception:
        return None


def state(v):
    if v is None: return "Không đủ dữ liệu"
    if v >= 2: return "Căng thẳng cao"
    if v >= 1: return "Căng thẳng vừa"
    if v > -1: return "Trung tính"
    return "Dư thừa"


bank = csv(DATA / "bank_metrics.csv")
log = csv(DATA / "refresh_log.csv")
panel = csv(OUT / "daily_panel.csv")
lpi_fc = csv(OUT / "lpi_forecast.csv")
ib_fc = csv(OUT / "interbank_forecast.csv")
regime = csv(OUT / "regime.csv")
stress = csv(OUT / "bank_stress.csv")
diag = csv(OUT / "diagnostics.csv")
summary = js(OUT / "summary.json")

lpi_hist = pd.to_numeric(panel["LPI"], errors="coerce").dropna() if len(panel) and "LPI" in panel.columns else pd.Series(dtype=float)
cur = num(lpi_hist.iloc[-1]) if len(lpi_hist) else None
f5 = num(lpi_fc.iloc[4]["forecast"]) if len(lpi_fc) >= 5 else None
f20 = num(lpi_fc.iloc[19]["forecast"]) if len(lpi_fc) >= 20 else None

with st.sidebar:
    st.subheader("TRẠNG THÁI HỆ THỐNG")
    if len(bank):
        actual_count = pd.to_numeric(bank.get("ActualMetricCount"), errors="coerce").fillna(0)
        st.success(f"Bronze bank file: {len(bank)} ngân hàng")
        st.write(f"Có ≥1 metric thực: **{int((actual_count > 0).sum())}**")
        st.write(f"Có ≥3/5 metric thực: **{int((actual_count >= 3).sum())}**")
    else:
        st.warning("Chưa có bank_metrics.csv")
    ib = csv(DATA / "interbank.csv")
    ib_obs = len(ib)
    ib_expl = 40
    ib_prod = 80
    st.write(f"Interbank ACTUAL: **{ib_obs} quan sát**")
    if ib_obs < ib_expl:
        st.caption(f"Cần thêm {ib_expl-ib_obs} quan sát để mở forecast exploratory; {ib_prod-ib_obs} để đạt production.")
    elif ib_obs < ib_prod:
        st.caption(f"Đã đủ exploratory; cần thêm {ib_prod-ib_obs} quan sát để đạt production.")
    else:
        st.caption("Interbank history đã đạt ngưỡng production.")
    st.write(f"LPI model: **{summary.get('lpi',{}).get('status','NO_MODEL')}**")
    ib_sum = summary.get("interbank", {})
    st.write(f"Interbank model: **{ib_sum.get('status','NO_MODEL')}**")
    if ib_sum.get("forecast_tier"):
        st.caption(f"Forecast tier: {ib_sum.get('forecast_tier')}")
    bs = summary.get("bank_stress", {})
    if bs:
        st.caption(f"Stress lineage: {bs.get('bronze',0)} Bronze · {bs.get('actual_mixed',0)} Actual mixed-source · {bs.get('hybrid',0)} Hybrid · {bs.get('fallback',0)} Fallback")


def fan(history, forecast, col, title, ytitle, thresholds=False):
    fig = go.Figure()
    if len(history) and col in history.columns:
        h = history[["date", col]].copy()
        h["date"] = pd.to_datetime(h.date, errors="coerce")
        h[col] = pd.to_numeric(h[col], errors="coerce")
        h = h.dropna()
        if len(h):
            h = h[h.date >= h.date.max() - pd.Timedelta(days=365)]
            fig.add_trace(go.Scatter(x=h.date, y=h[col], mode="lines", name="Actual", line=dict(width=2.2)))
    if thresholds:
        for y in [-1, 1, 2]: fig.add_hline(y=y, line_dash="dot", opacity=.35)
    if len(forecast):
        f = forecast.copy(); f["date"] = pd.to_datetime(f.date, errors="coerce")
        for c in ["forecast","p10","p90","p025","p975"]: f[c] = pd.to_numeric(f[c], errors="coerce")
        f = f.dropna(subset=["date","forecast"])
        if len(f):
            fig.add_trace(go.Scatter(x=f.date, y=f.p975, line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=f.date, y=f.p025, fill="tonexty", line=dict(width=0), name="95% CI", opacity=.12))
            fig.add_trace(go.Scatter(x=f.date, y=f.p90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=f.date, y=f.p10, fill="tonexty", line=dict(width=0), name="80% CI", opacity=.22))
            fig.add_trace(go.Scatter(x=f.date, y=f.forecast, mode="lines+markers", name="Forecast", line=dict(width=3, dash="dash")))
    fig.update_layout(title=title, height=430, yaxis_title=ytitle, hovermode="x unified", legend_orientation="h", margin=dict(l=20,r=20,t=55,b=20))
    return fig


tabs = st.tabs(["Tổng quan", "Thanh khoản hệ thống", "Lãi suất liên ngân hàng", "Funding Stress", "Stress Lab", "Dữ liệu & mô hình"])

with tabs[0]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("LPI hiện tại", f"{cur:.2f}" if cur is not None else "N/A")
    c2.metric("Dự báo 1 tuần", f"{f5:.2f}" if f5 is not None else "N/A", delta=f"{f5-cur:+.2f}" if f5 is not None and cur is not None else None)
    c3.metric("Dự báo 1 tháng", f"{f20:.2f}" if f20 is not None else "N/A", delta=f"{f20-cur:+.2f}" if f20 is not None and cur is not None else None)
    c4.metric("Trạng thái 1 tháng", state(f20))
    ldiag = summary.get("lpi", {})
    if ldiag.get("status") == "OK_BENCHMARK":
        st.warning("ARIMA không thắng naive benchmark; forecast production dùng NAIVE_RANDOM_WALK, Confidence=LOW.")
    elif ldiag.get("status") == "OK":
        skill = num(ldiag.get("skill_vs_naive"))
        if skill is not None:
            st.success(f"{ldiag.get('model')} thắng naive benchmark; Skill vs Naive = {skill:.1%}; Confidence={ldiag.get('confidence')}.")
    if len(lpi_fc):
        st.plotly_chart(fan(panel, lpi_fc, "LPI", "Liquidity Pressure Index — Actual & Forecast", "LPI (z-score)", True), use_container_width=True)
        st.caption("Ngưỡng đọc nhanh: <−1 dư thừa | −1 đến 1 trung tính | 1–2 căng vừa | >2 căng cao.")
    else:
        st.warning("Chưa có LPI forecast. Hãy chạy RUN_UPDATE_AND_PUSH.bat.")

with tabs[1]:
    st.subheader("Các động lực thanh khoản")
    if len(panel):
        cols = [c for c in ["ON_z","FX_z","OMO_z","LPI"] if c in panel.columns]
        t = panel[["date"] + cols].copy(); t["date"] = pd.to_datetime(t.date, errors="coerce")
        if len(t): t = t[t.date >= t.date.max() - pd.Timedelta(days=540)]
        fig = go.Figure()
        labels = {"ON_z":"Interbank ON", "FX_z":"FX pressure", "OMO_z":"OMO pressure", "LPI":"LPI"}
        for c in cols:
            fig.add_trace(go.Scatter(x=t.date, y=pd.to_numeric(t[c], errors="coerce"), mode="lines", name=labels[c], line=dict(width=3 if c == "LPI" else 1.2), opacity=1 if c == "LPI" else .65))
        fig.add_hline(y=0, line_dash="dot", opacity=.4)
        fig.update_layout(height=430, hovermode="x unified", legend_orientation="h")
        st.plotly_chart(fig, use_container_width=True)
    if len(regime):
        r = regime.copy(); r["date"] = pd.to_datetime(r.date, errors="coerce")
        fig = go.Figure()
        for c,n in [("P_Excess","Dư thừa"),("P_Neutral","Trung tính"),("P_Stress","Căng thẳng")]:
            fig.add_trace(go.Scatter(x=r.date, y=pd.to_numeric(r[c], errors="coerce"), mode="lines", name=n))
        fig.update_layout(title="Xác suất chế độ thanh khoản", height=350, yaxis_range=[0,1], yaxis_tickformat=".0%", legend_orientation="h")
        st.plotly_chart(fig, use_container_width=True)

with tabs[2]:
    st.subheader("Lãi suất liên ngân hàng qua đêm")
    ib = csv(DATA / "interbank.csv")
    if len(ib):
        ib["date"] = pd.to_datetime(ib.date, errors="coerce")
        ib["overnight_rate"] = pd.to_numeric(ib.overnight_rate, errors="coerce")
        ib = ib.sort_values("date").drop_duplicates("date", keep="last")
        ib_status = summary.get("interbank", {}).get("status")
        ib_tier = summary.get("interbank", {}).get("forecast_tier", "ACTUAL_ONLY")
        if len(ib_fc):
            st.plotly_chart(fan(ib, ib_fc, "overnight_rate", "Interbank ON — Actual & Forecast", "%/năm"), use_container_width=True)
            if ib_tier == "EXPLORATORY" or ib_status == "EXPLORATORY_LOW_CONFIDENCE":
                st.warning("Forecast ON hiện chỉ ở mức EXPLORATORY / LOW CONFIDENCE vì lịch sử thực chưa đạt 80 quan sát. Không nên dùng như forecast production.")
            else:
                st.success("Interbank ON forecast đã đạt ngưỡng lịch sử production.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ib.tail(260)["date"], y=ib.tail(260)["overnight_rate"], mode="lines+markers", name="Actual ON"))
            fig.update_layout(title="Interbank ON — Actual", height=430, yaxis_title="%/năm", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            need_exp = max(0, 40-len(ib)); need_prod = max(0, 80-len(ib))
            st.info(f"Có {len(ib)} quan sát ON thực. Cần thêm {need_exp} để mở forecast exploratory và {need_prod} để đạt ngưỡng production.")
        st.caption(f"Lịch sử đang tích lũy từ {ib['date'].min().date()} đến {ib['date'].max().date()}; mỗi lần refresh sẽ append + deduplicate, không xóa lịch sử cũ.")
    else:
        st.warning("Chưa lấy được Interbank ON từ Vnstock. App không thay thế bằng lãi suất tiền gửi/cho vay.")
        if len(log):
            z = log[log.dataset.astype(str).str.contains("interbank", case=False, na=False)]
            if len(z): st.dataframe(safe(z), hide_index=True, use_container_width=True)

with tabs[3]:
    st.subheader("Funding Stress theo ngân hàng")
    if len(stress):
        hs = list(stress.Horizon.dropna().unique())
        horizon = st.selectbox("Horizon", hs, index=min(1, len(hs)-1))
        b = stress[stress.Horizon == horizon].copy()
        b["StressVulnerability"] = pd.to_numeric(b.StressVulnerability, errors="coerce")
        valid = b.dropna(subset=["StressVulnerability"]).sort_values("StressVulnerability", ascending=False)
        if len(valid):
            fig = px.bar(valid, x="Ticker", y="StressVulnerability", color="SourceMode", hover_data=["ActualMetricCount","MetricCoverage","FundingCostShock_ppt","StressedNIM","Watch"])
            fig.update_layout(height=430, yaxis_range=[0,105])
            st.plotly_chart(fig, use_container_width=True)
            st.info(f"Lineage: {(valid.SourceMode=='BRONZE').sum()} Bronze · {(valid.SourceMode=='ACTUAL_MIXED_SOURCE').sum()} Actual mixed-source · {(valid.SourceMode=='HYBRID').sum()} Hybrid · {(valid.SourceMode=='FALLBACK').sum()} Fallback")
        st.dataframe(safe(b[["Ticker","ActualMetricCount","MetricCoverage","BaseVulnerability","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch","DataType","SourceMode"]]), hide_index=True, use_container_width=True)
    else:
        st.warning("Chưa có bank_stress.csv. Hãy chạy RUN_UPDATE_AND_PUSH.bat.")

with tabs[4]:
    st.subheader("Stress Lab")
    b = stress[stress.Horizon == "Current"].copy() if len(stress) else pd.DataFrame()
    if len(b):
        shock = st.slider("Cú sốc LPI bổ sung", 0.0, 3.0, 1.0, .1)
        passmax = st.slider("Funding-cost pass-through tối đa (ppt)", .5, 4.0, 2.0, .25)
        b["ScenarioVulnerability"] = (pd.to_numeric(b.BaseVulnerability, errors="coerce") * (1 + .15*shock)).clip(0,100)
        b["ScenarioFundingCost_ppt"] = passmax * b.ScenarioVulnerability / 100
        fig = px.bar(b.sort_values("ScenarioVulnerability", ascending=False), x="Ticker", y="ScenarioVulnerability", color="SourceMode", hover_data=["ActualMetricCount"])
        fig.update_layout(height=430, yaxis_range=[0,105])
        st.plotly_chart(fig, use_container_width=True)
        st.caption("HYBRID = giữ các metric Bronze thực và chỉ bù metric thiếu bằng assumption. FALLBACK = toàn bộ 5 metric là assumption.")
    else:
        st.warning("Chưa có dữ liệu stress.")

with tabs[5]:
    st.subheader("Model Diagnostics")
    if len(diag): st.dataframe(safe(diag), hide_index=True, use_container_width=True)
    st.subheader("Bank Data Quality")
    st.caption("CASA ưu tiên Vnstock trực tiếp; nếu Vnstock không có, hệ thống dùng CASA ACTUAL từ CASA_INPUT/public source. Nếu cả hai đều thiếu, model chỉ dùng assumption cho riêng CASA và vẫn gắn HYBRID. CASASource/CASASourceURL cho biết lineage.")
    if len(bank):
        cols = [c for c in ["Ticker","LDR","CASA","CASASource","CASADataType","CASAPeriod","CASASourceName","CASASourceURL","DemandDeposits","CustomerDeposits","InterbankDep","CreditDepositGap","NIM","ActualMetricCount","MetricCoverage","ParseStatus","ParserLog"] if c in bank.columns]
        st.dataframe(safe(bank[cols]), hide_index=True, use_container_width=True)
    st.subheader("Refresh Log")
    if len(log): st.dataframe(safe(log), hide_index=True, use_container_width=True)

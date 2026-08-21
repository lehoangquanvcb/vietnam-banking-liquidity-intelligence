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
[data-testid="stMetricValue"]{font-size:1.35rem}
[data-testid="stMetricLabel"]{font-weight:650}
div[data-testid="stTabs"] button{white-space:nowrap}
div[data-testid="stMetric"]{padding:.35rem .15rem}
hr{margin:.7rem 0 1rem}
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


def interbank_interpretation(current, forecast20, diag_info):
    if current is None or forecast20 is None:
        return "Chưa đủ dữ liệu để diễn giải hướng lãi suất liên ngân hàng."
    delta = forecast20 - current
    if delta >= 1.0:
        direction = "tăng đáng kể"
        meaning = "hàm ý áp lực funding ngắn hạn có xu hướng gia tăng nếu các điều kiện khác không đổi"
    elif delta >= .3:
        direction = "tăng nhẹ"
        meaning = "hàm ý thanh khoản có thể bớt thuận lợi hơn"
    elif delta <= -1.0:
        direction = "giảm đáng kể"
        meaning = "hàm ý áp lực funding ngắn hạn có thể hạ nhiệt"
    elif delta <= -.3:
        direction = "giảm nhẹ"
        meaning = "hàm ý điều kiện thanh khoản có thể thuận lợi hơn"
    else:
        direction = "đi ngang"
        meaning = "hàm ý mô hình chưa thấy thay đổi đáng kể so với mức ON gần nhất"
    model = diag_info.get("model", "N/A")
    skill = num(diag_info.get("skill_vs_naive"))
    skill_text = f"; Skill vs Naive {skill:.1%}" if skill is not None else ""
    tier = diag_info.get("forecast_tier", "N/A")
    return f"Mô hình {model} dự báo ON 20D {direction} ({delta:+.2f} điểm %); {meaning}. Tier={tier}{skill_text}."


def interbank_liquidity_message(ib_info, current, champion20, challenger20=None):
    ms = ib_info.get("market_state", {}) if isinstance(ib_info, dict) else {}
    regime = ms.get("market_regime_vi", "Chưa xác định")
    momentum = ms.get("momentum_vi", "Chưa xác định")
    pct = num(ms.get("current_percentile"))
    vol = num(ms.get("change_volatility"))

    messages=[]
    if pct is not None:
        if pct >= .75:
            messages.append(f"ON hiện tại nằm quanh percentile {pct:.0%} của lịch sử ACTUAL — mặt bằng đang ở vùng cao tương đối.")
        elif pct <= .25:
            messages.append(f"ON hiện tại nằm quanh percentile {pct:.0%} — mặt bằng đang ở vùng thấp tương đối.")
        else:
            messages.append(f"ON hiện tại nằm quanh percentile {pct:.0%} — chưa phải vùng cực đoan của lịch sử ACTUAL.")
    messages.append(f"Trạng thái mô tả: **{regime}**; động lượng gần đây: **{momentum}**.")
    if vol is not None:
        messages.append(f"Độ biến động thay đổi ON giữa các quan sát khoảng **{vol:.2f} điểm %**.")

    if current is not None and champion20 is not None:
        d = champion20-current
        if d <= -.5:
            messages.append("Champion nghiêng về **hạ nhiệt funding pressure** trong 20D.")
        elif d >= .5:
            messages.append("Champion nghiêng về **gia tăng funding pressure** trong 20D.")
        else:
            messages.append("Champion chưa cho tín hiệu thay đổi mạnh về funding pressure trong 20D.")

    if challenger20 is not None and champion20 is not None:
        dc = challenger20-current if current is not None else None
        if dc is not None and abs(challenger20-champion20) >= .5:
            messages.append(
                "Champion và Challenger đang phân kỳ đáng kể; đây là dấu hiệu **model uncertainty cao**, "
                "nên ưu tiên quản trị theo dải kịch bản thay vì một điểm forecast."
            )
        else:
            messages.append("Champion và Challenger tương đối đồng thuận về hướng đi.")
    return " ".join(messages)


def model_role_badge(role):
    if role == "STATISTICAL_CHAMPION":
        return "🏆 Statistical Champion"
    if role == "DIRECTIONAL_CHALLENGER":
        return "🧭 Directional Challenger"
    return "Candidate"


bank = csv(DATA / "bank_metrics.csv")
log = csv(DATA / "refresh_log.csv")
panel = csv(OUT / "daily_panel.csv")
lpi_fc = csv(OUT / "lpi_forecast.csv")
ib_fc = csv(OUT / "interbank_forecast.csv")
regime = csv(OUT / "regime.csv")
stress = csv(OUT / "bank_stress.csv")
diag = csv(OUT / "diagnostics.csv")
summary = js(OUT / "summary.json")
cfg = js(ROOT / "config" / "model_config.json")
ib_comp = csv(OUT / "interbank_model_comparison.csv")
ib_challenger_fc = csv(OUT / "interbank_challenger_forecast.csv")

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
    ib_expl = int(cfg.get("min_interbank_exploratory_observations", 18))
    ib_prod = int(cfg.get("min_interbank_production_observations", 60))
    st.write(f"Interbank ACTUAL: **{ib_obs} quan sát**")
    if ib_obs < ib_expl:
        st.caption(f"Forecast exploratory chưa mở: cần thêm {ib_expl-ib_obs} quan sát; cần thêm {ib_prod-ib_obs} để đạt production.")
    elif ib_obs < ib_prod:
        st.caption(f"Forecast exploratory: ĐÃ MỞ · cần thêm {ib_prod-ib_obs} quan sát để đạt production ({ib_prod}).")
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
    ib_info = summary.get("interbank", {})

    if len(ib):
        ib["date"] = pd.to_datetime(ib.date, errors="coerce")
        ib["overnight_rate"] = pd.to_numeric(ib.overnight_rate, errors="coerce")
        ib = ib.dropna(subset=["date","overnight_rate"]).sort_values("date").drop_duplicates("date", keep="last")

        ib_status = ib_info.get("status")
        ib_tier = ib_info.get("forecast_tier", "ACTUAL_ONLY")
        current_on = num(ib.iloc[-1]["overnight_rate"]) if len(ib) else None
        champion = ib_info.get("model","N/A")
        challenger_info = ib_info.get("challenger", {}) if isinstance(ib_info.get("challenger", {}), dict) else {}
        challenger = challenger_info.get("model")
        champion_flat = bool(ib_info.get("champion_is_flat", False))

        def fc_at(df,h):
            return num(df.iloc[h-1]["forecast"]) if len(df) >= h else None

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("ON hiện tại", f"{current_on:.2f}%" if current_on is not None else "N/A")
        c2.metric("Champion", champion)
        c3.metric("Dự báo 5D", f"{fc_at(ib_fc,5):.2f}%" if fc_at(ib_fc,5) is not None else "N/A")
        c4.metric("Dự báo 20D", f"{fc_at(ib_fc,20):.2f}%" if fc_at(ib_fc,20) is not None else "N/A")
        c5.metric("Challenger", challenger or "Không có")
        c6.metric("Tier", ib_tier)

        # Executive interpretation strip.
        champ20=fc_at(ib_fc,20)
        chall20=fc_at(ib_challenger_fc,20)
        if len(ib_fc):
            if champion_flat and challenger:
                st.warning(
                    f"**{champion}** là Statistical Champion theo rolling RMSE nhưng forecast khá phẳng. "
                    f"Dashboard giữ nguyên Champion để đảm bảo governance và hiển thị **{challenger}** như Directional Challenger, "
                    "không dùng Challenger để thay thế kết quả chính."
                )
            elif champion_flat:
                st.info(
                    f"**{champion}** là Champion và đang tạo forecast phẳng. Không có Challenger nào vừa đủ khác biệt về hướng đi "
                    "vừa đạt tiêu chuẩn RMSE; hệ thống không ép một model kém hơn chỉ để tạo đường forecast đẹp."
                )
            else:
                st.success(f"Champion **{champion}** vừa tốt hơn benchmark vừa tạo đường forecast có thông tin hướng đi.")

        # Actual + champion fan + challenger overlay.
        fig = fan(ib, ib_fc, "overnight_rate", "Interbank ON — Actual, Champion & Risk Bands", "%/năm")
        if len(ib_challenger_fc):
            cf=ib_challenger_fc.copy()
            cf["date"]=pd.to_datetime(cf["date"],errors="coerce")
            cf["forecast"]=pd.to_numeric(cf["forecast"],errors="coerce")
            fig.add_trace(go.Scatter(
                x=cf["date"],y=cf["forecast"],mode="lines+markers",
                name=f"Challenger: {challenger}",line=dict(width=2,dash="dot")
            ))
        st.plotly_chart(fig,use_container_width=True)

        # Term structure comparison.
        if len(ib_fc):
            st.markdown("### Term structure dự báo")
            horizons=[1,5,10,20]
            term=[]
            for h in horizons:
                term.append({
                    "Horizon":f"{h}D",
                    "Champion":fc_at(ib_fc,h),
                    "Challenger":fc_at(ib_challenger_fc,h),
                    "Current":current_on,
                })
            termdf=pd.DataFrame(term)
            left,right=st.columns([1.25,1])
            with left:
                tf=go.Figure()
                tf.add_trace(go.Scatter(x=termdf.Horizon,y=termdf.Champion,mode="lines+markers",name=f"Champion: {champion}",line=dict(width=3)))
                if termdf.Challenger.notna().any():
                    tf.add_trace(go.Scatter(x=termdf.Horizon,y=termdf.Challenger,mode="lines+markers",name=f"Challenger: {challenger}",line=dict(width=2,dash="dot")))
                if current_on is not None:
                    tf.add_hline(y=current_on,line_dash="dash",opacity=.4,annotation_text="ON hiện tại")
                tf.update_layout(height=330,yaxis_title="%/năm",legend_orientation="h",margin=dict(l=20,r=20,t=35,b=20))
                st.plotly_chart(tf,use_container_width=True)
            with right:
                display=termdf.copy()
                display["Δ Champion"]=display["Champion"]-current_on if current_on is not None else np.nan
                display["Δ Challenger"]=display["Challenger"]-current_on if current_on is not None else np.nan
                st.dataframe(
                    display.style.format({
                        "Champion":"{:.2f}","Challenger":"{:.2f}","Current":"{:.2f}",
                        "Δ Champion":"{:+.2f}","Δ Challenger":"{:+.2f}"
                    }),
                    hide_index=True,use_container_width=True
                )

        # Market regime / risk state.
        st.markdown("### Trạng thái thị trường & hàm ý thanh khoản")
        ms=ib_info.get("market_state",{}) if isinstance(ib_info.get("market_state",{}),dict) else {}
        r1,r2,r3,r4=st.columns(4)
        pct=num(ms.get("current_percentile"))
        vol=num(ms.get("change_volatility"))
        r1.metric("Regime", ms.get("market_regime_vi","N/A"))
        r2.metric("Momentum", ms.get("momentum_vi","N/A"))
        r3.metric("Percentile hiện tại", f"{pct:.0%}" if pct is not None else "N/A")
        r4.metric("Volatility ΔON", f"{vol:.2f} ppt" if vol is not None else "N/A")
        st.info(interbank_liquidity_message(ib_info,current_on,champ20,chall20))

        # Model governance scorecard.
        st.markdown("### Champion–Challenger Model Scorecard")
        if len(ib_comp):
            comp=ib_comp.copy()
            for c in ["RMSE","MAE","SkillVsNaive","Forecast1D","Forecast5D","Forecast20D","DirectionalMove20D","ForecastPathRange"]:
                if c in comp.columns:
                    comp[c]=pd.to_numeric(comp[c],errors="coerce")
            if "Role" not in comp.columns:
                comp["Role"]=np.where(comp.get("Selected",False),"STATISTICAL_CHAMPION","CANDIDATE")
            comp["Vai trò"]=comp["Role"].map(model_role_badge)

            g1,g2=st.columns([1,1.2])
            with g1:
                b=comp.sort_values("RMSE",ascending=True).copy()
                figm=px.bar(
                    b,x="RMSE",y="Model",orientation="h",color="Role",
                    hover_data=["MAE","SkillVsNaive","DirectionalMove20D"] if "DirectionalMove20D" in b.columns else ["MAE","SkillVsNaive"],
                    title="Rolling-origin RMSE — càng thấp càng tốt"
                )
                figm.update_layout(height=430,yaxis={"categoryorder":"total descending"})
                st.plotly_chart(figm,use_container_width=True)
            with g2:
                cols=[c for c in ["Vai trò","Model","RMSE","MAE","SkillVsNaive","Forecast20D","DirectionalMove20D","IsFlat","RollingPoints"] if c in comp.columns]
                st.dataframe(
                    safe(comp.sort_values("RMSE")[cols]),
                    hide_index=True,use_container_width=True,height=430
                )

            skill=num(ib_info.get("skill_vs_naive")); rmse=num(ib_info.get("rmse")); naive=num(ib_info.get("naive_rmse"))
            champion_msg = (
                f"**Statistical Champion: {champion}.** "
                + (f"Rolling RMSE {rmse:.3f} so với Naive {naive:.3f}; Skill vs Naive {skill:.1%}. " if rmse is not None and naive is not None and skill is not None else "")
            )
            if challenger:
                prem=num(challenger_info.get("rmse_premium_vs_champion"))
                champion_msg += (
                    f"**Directional Challenger: {challenger}**"
                    + (f", RMSE cao hơn Champion {prem:.1%}" if prem is not None else "")
                    + ". Challenger chỉ dùng để đọc hướng/rủi ro mô hình, không thay Champion."
                )
            st.write(champion_msg)

        # Horizon uncertainty table.
        if len(ib_fc):
            st.markdown("### Dải dự báo Champion")
            rows=[]
            for h,label in [(1,"1D"),(5,"5D"),(10,"10D"),(20,"20D")]:
                if len(ib_fc)>=h:
                    r=ib_fc.iloc[h-1]
                    rows.append({
                        "Horizon":label,
                        "Forecast":num(r.get("forecast")),
                        "80% Low":num(r.get("p10")),"80% High":num(r.get("p90")),
                        "95% Low":num(r.get("p025")),"95% High":num(r.get("p975")),
                        "Δ vs Current":num(r.get("forecast"))-current_on if current_on is not None and num(r.get("forecast")) is not None else None,
                        "Tier":ib_tier,
                    })
            htab=pd.DataFrame(rows)
            st.dataframe(
                htab.style.format({
                    "Forecast":"{:.2f}","80% Low":"{:.2f}","80% High":"{:.2f}",
                    "95% Low":"{:.2f}","95% High":"{:.2f}","Δ vs Current":"{:+.2f}"
                }),
                hide_index=True,use_container_width=True
            )

        # Governance notice.
        if ib_tier=="EXPLORATORY" or ib_status=="EXPLORATORY_LOW_CONFIDENCE":
            st.warning(
                f"Forecast ON vẫn là **EXPLORATORY / LOW CONFIDENCE** vì mới có {len(ib)} quan sát ACTUAL, "
                f"dưới ngưỡng production {int(cfg.get('min_interbank_production_observations',60))}. "
                "Champion–Challenger giúp đọc model risk tốt hơn nhưng không làm tăng chất lượng dữ liệu nền."
            )
        else:
            st.success("Interbank ON forecast đã đạt ngưỡng lịch sử production và Champion vẫn phải vượt Naive theo governance.")

        st.caption(
            f"Lịch sử ACTUAL từ {ib['date'].min().date()} đến {ib['date'].max().date()}; "
            "refresh append + deduplicate, không xóa lịch sử cũ."
        )
    else:
        st.warning("Chưa lấy được Interbank ON từ Vnstock. App không thay thế bằng lãi suất tiền gửi/cho vay.")
        if len(log):
            z=log[log.dataset.astype(str).str.contains("interbank",case=False,na=False)]
            if len(z):
                st.dataframe(safe(z),hide_index=True,use_container_width=True)

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

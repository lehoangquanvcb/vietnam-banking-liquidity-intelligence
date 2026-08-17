
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import json

ROOT=Path(__file__).parent
DATA=ROOT/"data"
CFG=ROOT/"config"
BANKS=json.loads((CFG/"banks.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="Vietnam Banking Liquidity V6.2",layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem}
[data-testid="stMetricValue"]{font-size:1.5rem}
h1{font-size:2rem!important}
[data-testid="stAlert"]{border-radius:10px}
</style>
""",unsafe_allow_html=True)

st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG — V6.2")
st.caption("Cloud Stable • Dữ liệu Vnstock Bronze refresh từ máy local • Stress thanh khoản • Xếp hạng ngân hàng")

def load_csv(name):
    p=DATA/f"{name}.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()

def frac(s):
    x=pd.to_numeric(s,errors="coerce")
    return np.where(np.abs(x)>2,x/100.0,x)

def score_banks(df,stress_multiplier=1.35,max_funding_pass=2.0):
    if df.empty:
        return pd.DataFrame()
    d=df.copy()
    needed=["LDR Proxy","CASA Proxy","NIM","Total Assets","Interbank Borrowing","Customer Loans","Customer Deposits"]
    for c in needed:
        if c not in d.columns:
            d[c]=np.nan
        d[c]=pd.to_numeric(d[c],errors="coerce")
    d["LDR"]=frac(d["LDR Proxy"])
    d["CASA"]=frac(d["CASA Proxy"])
    d["NIM_f"]=frac(d["NIM"])
    d["InterbankDep"]=d["Interbank Borrowing"]/d["Total Assets"]
    d["CreditDepositGap"]=(d["Customer Loans"]-d["Customer Deposits"])/d["Customer Deposits"]
    d["LiquidityBuffer"]=1-d["LDR"]
    metrics=["LDR","CASA","InterbankDep","CreditDepositGap","NIM_f","LiquidityBuffer"]
    d["DataCoverage"]=d[metrics].notna().mean(axis=1)
    raw=(50
         +35*(d["LDR"]-.85)
         -25*(d["CASA"]-.20)
         +45*d["InterbankDep"]
         +30*d["CreditDepositGap"]
         -10*(d["NIM_f"]-.03)
         -20*(d["LiquidityBuffer"]-.15))
    d["BaseVulnerability"]=raw.clip(0,100)
    d.loc[d["DataCoverage"]<.5,"BaseVulnerability"]=np.nan
    d["StressVulnerability"]=(d["BaseVulnerability"]*stress_multiplier).clip(0,100)
    d["FundingCostShock_ppt"]=max_funding_pass*d["StressVulnerability"]/100
    d["StressedNIM"]=np.maximum(0,d["NIM_f"]-d["FundingCostShock_ppt"]/100)
    d["WatchFlag"]=np.select(
        [(d["StressVulnerability"]>=75)|(d["StressedNIM"]<.02),d["StressVulnerability"]>=60],
        ["ĐỎ","VÀNG"],default="XANH"
    )
    d["Rank"]=d["StressVulnerability"].rank(ascending=False,method="min")
    return d.sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

def data_age(df):
    for c in ["Retrieved At","retrieved_at","Updated At","updated_at"]:
        if c in df.columns:
            ts=pd.to_datetime(df[c],errors="coerce",utc=True).max()
            if pd.notna(ts):
                now=pd.Timestamp.now(tz="UTC")
                return (now-ts).total_seconds()/3600, ts
    return None,None

bank_actuals=load_csv("bank_actuals")
bank_status=load_csv("bank_refresh_status")
macro_status=load_csv("macro_refresh_status")
daily=load_csv("daily_features")
bank_stress=score_banks(bank_actuals) if len(bank_actuals) else pd.DataFrame()

with st.sidebar:
    st.subheader("TRẠNG THÁI DỮ LIỆU")
    st.write("Nguồn: **Vnstock Bronze Sponsor (local refresh)**")
    st.write(f"Ngân hàng theo dõi: **{len(BANKS)}**")
    age,ts=data_age(bank_actuals)
    if age is None:
        st.error("Chưa có dữ liệu ngân hàng.")
    else:
        st.write(f"Lần cập nhật gần nhất: **{ts.strftime('%d/%m/%Y %H:%M UTC')}**")
        if age>48:
            st.warning(f"Dữ liệu đã cũ khoảng {age:.0f} giờ.")
        else:
            st.success(f"Dữ liệu mới: {age:.1f} giờ.")
    st.caption("Để cập nhật: chạy `REFRESH_AND_PUSH.bat` trên máy local.")

tabs=st.tabs([
    "Trung tâm điều hành",
    "Xếp hạng ngân hàng",
    "Mô phỏng Stress",
    "Chi tiết ngân hàng",
    "Thanh khoản hệ thống",
    "Chất lượng dữ liệu",
])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Số ngân hàng theo dõi",len(BANKS))
    c2.metric("Có dữ liệu thực",len(bank_actuals))
    c3.metric("Cảnh báo ĐỎ",int((bank_stress.WatchFlag=="ĐỎ").sum()) if len(bank_stress) else 0)
    c4.metric("Vulnerability trung vị",f"{bank_stress.StressVulnerability.median():.1f}" if len(bank_stress) and bank_stress.StressVulnerability.notna().any() else "N/A")

    if bank_actuals.empty:
        st.warning("Chưa có `data/bank_actuals.csv`. App vẫn hoạt động bình thường nhưng chưa thể xếp hạng ngân hàng. Hãy chạy REFRESH_AND_PUSH.bat trên máy có Vnstock Sponsor.")
    elif len(bank_stress):
        top=bank_stress.dropna(subset=["StressVulnerability"]).head(10)
        if len(top):
            st.subheader("Ngân hàng nhạy cảm nhất với stress thanh khoản")
            st.bar_chart(top.set_index("Ticker")[["StressVulnerability"]],height=320)
            st.dataframe(top[["Ticker","StressVulnerability","FundingCostShock_ppt","StressedNIM","WatchFlag","DataCoverage"]],use_container_width=True,hide_index=True)

with tabs[1]:
    if len(bank_stress):
        show=bank_stress.rename(columns={
            "Ticker":"Mã","Period":"Kỳ","LDR":"LDR","CASA":"CASA",
            "InterbankDep":"Phụ thuộc liên ngân hàng","CreditDepositGap":"Khoảng cách tín dụng-tiền gửi",
            "NIM_f":"NIM","LiquidityBuffer":"Bộ đệm thanh khoản","DataCoverage":"Độ phủ dữ liệu",
            "BaseVulnerability":"Rủi ro cơ sở","StressVulnerability":"Rủi ro sau stress",
            "FundingCostShock_ppt":"Chi phí vốn +ppt","StressedNIM":"NIM sau stress",
            "WatchFlag":"Cảnh báo","Rank":"Xếp hạng"
        })
        st.dataframe(show,use_container_width=True,hide_index=True)
    else:
        st.info("Chưa có đủ dữ liệu thực để xếp hạng.")

with tabs[2]:
    c1,c2,c3=st.columns(3)
    multiplier=c1.slider("Hệ số stress hệ thống",1.0,2.0,1.35,.05)
    funding_pass=c2.slider("Mức truyền dẫn chi phí vốn tối đa (ppt)",0.5,4.0,2.0,.25)
    lpi=c3.slider("Kịch bản LPI hệ thống",-1.0,3.0,1.5,.1)
    if len(bank_actuals):
        effective=multiplier*(1+max(0,lpi)*0.10)
        d=score_banks(bank_actuals,effective,funding_pass)
        st.bar_chart(d.dropna(subset=["StressVulnerability"]).set_index("Ticker")[["BaseVulnerability","StressVulnerability"]],height=360)
        st.dataframe(d,use_container_width=True,hide_index=True)
    else:
        st.info("Chưa có dữ liệu thực để chạy stress.")

with tabs[3]:
    if len(bank_stress):
        tick=st.selectbox("Chọn ngân hàng",bank_stress.Ticker.tolist())
        r=bank_stress[bank_stress.Ticker==tick].iloc[0]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Stress Vulnerability",f"{r.StressVulnerability:.1f}" if pd.notna(r.StressVulnerability) else "N/A")
        c2.metric("Chi phí vốn tăng",f"+{r.FundingCostShock_ppt:.2f} ppt" if pd.notna(r.FundingCostShock_ppt) else "N/A")
        c3.metric("NIM sau stress",f"{r.StressedNIM:.2%}" if pd.notna(r.StressedNIM) else "N/A")
        c4.metric("Cảnh báo",r.WatchFlag)
        detail=pd.DataFrame({
            "Chỉ tiêu":["LDR","CASA","Phụ thuộc liên ngân hàng","Khoảng cách tín dụng-tiền gửi","NIM","Độ phủ dữ liệu"],
            "Giá trị":[r.LDR,r.CASA,r.InterbankDep,r.CreditDepositGap,r.NIM_f,r.DataCoverage]
        })
        st.dataframe(detail,use_container_width=True,hide_index=True)
    else:
        st.info("Chưa có dữ liệu ngân hàng.")

with tabs[4]:
    if len(daily):
        if "date" in daily.columns:
            daily["date"]=pd.to_datetime(daily["date"],errors="coerce")
        if "LPI" in daily.columns and "date" in daily.columns:
            st.subheader("Liquidity Pressure Index")
            st.line_chart(daily.dropna(subset=["date"]).set_index("date")[["LPI"]].tail(250),height=320)
        st.dataframe(daily.tail(120),use_container_width=True,hide_index=True)
    else:
        st.info("Chưa có `data/daily_features.csv`. Chạy refresh local nếu muốn hiển thị thanh khoản hệ thống.")

with tabs[5]:
    st.subheader("Trạng thái refresh ngân hàng")
    if len(bank_status):
        st.dataframe(bank_status,use_container_width=True,hide_index=True)
    else:
        st.info("Chưa có log refresh ngân hàng.")
    st.subheader("Trạng thái refresh vĩ mô")
    if len(macro_status):
        st.dataframe(macro_status,use_container_width=True,hide_index=True)
    else:
        st.info("Chưa có log refresh vĩ mô.")
    st.markdown("""
**Quy tắc dữ liệu**
- `ACTUAL`: lấy trực tiếp từ Vnstock/nguồn chính thức.
- `CALC`: tính từ ACTUAL.
- `ESTIMATE`: phải có phương pháp rõ.
- `ASSUMPTION`: chỉ dùng cho kịch bản.
- Không tạo synthetic history để lấp dữ liệu production.
""")

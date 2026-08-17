
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import time, json, re

ROOT=Path(__file__).parent
DATA=ROOT/"data"
CFG=ROOT/"config"
DATA.mkdir(exist_ok=True)

st.set_page_config(page_title="Vietnam Banking Liquidity V6.1", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem}
[data-testid="stMetricValue"]{font-size:1.5rem}
h1{font-size:2rem!important}
.small-note{font-size:.9rem;color:#888}
</style>
""", unsafe_allow_html=True)

st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG — V6.1")
st.caption("Vnstock Bronze Sponsor • Tự động cập nhật • Stress thanh khoản • Xếp hạng ngân hàng • NIM/Funding Pressure")

BANKS=json.loads((CFG/"banks.json").read_text(encoding="utf-8"))
SPONSOR=json.loads((CFG/"vnstock_bronze.json").read_text(encoding="utf-8"))

def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df, keys):
    if df is None or len(df)==0: return None
    for c in df.columns:
        n=norm(c)
        if any(k in n for k in keys):
            vals=pd.to_numeric(df[c],errors="coerce").dropna()
            if len(vals): return float(vals.iloc[0])
    for lc in df.columns[:min(3,len(df.columns))]:
        labels=df[lc].astype(str).map(norm)
        mask=pd.Series(False,index=df.index)
        for k in keys:
            mask |= labels.str.contains(k,regex=False)
        if mask.any():
            for vc in reversed(df.columns):
                if vc==lc: continue
                vals=pd.to_numeric(df.loc[mask,vc],errors="coerce").dropna()
                if len(vals): return float(vals.iloc[0])
    return None

def latest_period(*dfs):
    for df in dfs:
        if df is None or len(df)==0: continue
        for c in ["report_time","year","quarter","period","time"]:
            if c in df.columns:
                v=df[c].dropna()
                if len(v): return str(v.iloc[0])
    return ""

def frac(x):
    x=pd.to_numeric(x,errors="coerce")
    return np.where(np.abs(x)>2,x/100.0,x)

def score_banks(df, stress_multiplier=1.35, max_funding_pass=2.0):
    if df.empty: return df
    d=df.copy()
    for c in ["LDR Proxy","CASA Proxy","NIM","Total Assets","Interbank Borrowing","Customer Loans","Customer Deposits"]:
        if c in d.columns: d[c]=pd.to_numeric(d[c],errors="coerce")
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
        [(d["StressVulnerability"]>=75)|(d["StressedNIM"]<.02), d["StressVulnerability"]>=60],
        ["ĐỎ","VÀNG"], default="XANH")
    d["Rank"]=d["StressVulnerability"].rank(ascending=False,method="min")
    return d.sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

@st.cache_data(ttl=60*60, show_spinner=False)
def fetch_bank_data_cached(bank_list):
    from vnstock_data import Fundamental
    fun=Fundamental()
    rows=[]; status=[]
    for symbol in bank_list:
        try:
            eq=fun.equity(symbol)
            bs=eq.balance_sheet(period="Q")
            inc=eq.income_statement(period="Q")
            try:
                ratio=eq.financial_ratio()
            except Exception:
                try: ratio=eq.ratio(period="Q")
                except Exception: ratio=pd.DataFrame()
            assets=find_metric(bs,["total assets","tổng tài sản"])
            loans=find_metric(bs,["customer loans","loans to customers","cho vay khách hàng"])
            deposits=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
            ib=find_metric(bs,["borrowings from other credit institutions","interbank borrowing","vay các tổ chức tín dụng","tiền gửi và vay các tổ chức tín dụng"])
            current=find_metric(bs,["current account","demand deposit","tiền gửi không kỳ hạn"])
            totaldep=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
            nii=find_metric(inc,["net interest income","thu nhập lãi thuần"])
            nim=find_metric(ratio,["nim","net interest margin"])
            ldr=find_metric(ratio,["ldr","loan to deposit"])
            casa=find_metric(ratio,["casa"])
            if ldr is None and loans is not None and deposits not in (None,0): ldr=loans/deposits
            if casa is None and current is not None and totaldep not in (None,0): casa=current/totaldep
            rows.append({
                "Ticker":symbol,"Period":latest_period(bs,inc,ratio),
                "Total Assets":assets,"Customer Loans":loans,"Customer Deposits":deposits,
                "Interbank Borrowing":ib,"Current Accounts":current,"Total Deposits":totaldep,
                "Net Interest Income":nii,"Average Earning Assets":None,"NIM":nim,
                "LDR Proxy":ldr,"CASA Proxy":casa,"Data Type":"ACTUAL",
                "Retrieved At":datetime.now().isoformat(timespec="seconds")
            })
            status.append([symbol,"OK",""])
        except Exception as e:
            status.append([symbol,"ERROR",repr(e)])
        time.sleep(0.12)
    return pd.DataFrame(rows), pd.DataFrame(status,columns=["Ticker","Status","Message"])

def load_local_bank_data():
    p=DATA/"bank_actuals.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def save_session_csv(df, name):
    # Community Cloud filesystem may reset between restarts; this is only runtime cache.
    try:
        df.to_csv(DATA/f"{name}.csv",index=False,encoding="utf-8-sig")
    except Exception:
        pass

def get_bank_data(force=False):
    local=load_local_bank_data()
    if force:
        fetch_bank_data_cached.clear()
        local=pd.DataFrame()
    if len(local):
        try:
            ts=pd.to_datetime(local["Retrieved At"],errors="coerce").max()
            if pd.notna(ts) and datetime.now()-ts.to_pydatetime()<timedelta(hours=12):
                return local, pd.DataFrame({"Ticker":local["Ticker"],"Status":"CACHE","Message":""})
        except Exception:
            pass
    actual,status=fetch_bank_data_cached(tuple(BANKS))
    if len(actual): save_session_csv(actual,"bank_actuals")
    if len(status): save_session_csv(status,"bank_refresh_status")
    return actual,status

with st.sidebar:
    st.subheader("TRẠNG THÁI DỮ LIỆU")
    st.write(f"Vnstock: **Bronze Sponsor profile**")
    st.write(f"Ngân hàng theo dõi: **{len(BANKS)}**")
    st.write("Cache BCTC: **12 giờ**")
    refresh=st.button("🔄 Cập nhật dữ liệu Vnstock")
    st.caption("Dữ liệu thiếu sẽ để trống; app không tự tạo số liệu ngân hàng giả.")

with st.spinner("Đang tải dữ liệu ngân hàng..." if refresh else "Đang khởi tạo dữ liệu..."):
    bank_actuals, bank_status = get_bank_data(force=refresh)

stress_default=1.35
pass_default=2.0
bank_stress=score_banks(bank_actuals,stress_default,pass_default) if len(bank_actuals) else pd.DataFrame()
if len(bank_stress): save_session_csv(bank_stress,"bank_stress")

tabs=st.tabs([
    "Trung tâm điều hành",
    "Xếp hạng ngân hàng",
    "Mô phỏng Stress",
    "Chi tiết ngân hàng",
    "Thanh khoản hệ thống",
    "Chất lượng dữ liệu"
])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Số ngân hàng theo dõi",len(BANKS))
    c2.metric("Có dữ liệu thực",len(bank_actuals))
    c3.metric("Cảnh báo ĐỎ", int((bank_stress.WatchFlag=="ĐỎ").sum()) if len(bank_stress) else 0)
    c4.metric("Vulnerability trung vị", f"{bank_stress.StressVulnerability.median():.1f}" if len(bank_stress) and bank_stress.StressVulnerability.notna().any() else "N/A")

    if len(bank_stress):
        top=bank_stress.dropna(subset=["StressVulnerability"]).head(10)
        if len(top):
            st.subheader("Top ngân hàng nhạy cảm với stress thanh khoản")
            st.bar_chart(top.set_index("Ticker")[["StressVulnerability"]],height=320)
            st.dataframe(
                top[["Ticker","StressVulnerability","FundingCostShock_ppt","StressedNIM","WatchFlag","DataCoverage"]],
                use_container_width=True,hide_index=True
            )
    else:
        st.warning("Chưa có đủ dữ liệu ngân hàng để tính vulnerability.")

with tabs[1]:
    if len(bank_stress):
        show=bank_stress.copy()
        show=show.rename(columns={
            "Ticker":"Mã","LDR":"LDR","CASA":"CASA","InterbankDep":"Phụ thuộc liên ngân hàng",
            "CreditDepositGap":"Khoảng cách tín dụng-tiền gửi","NIM_f":"NIM","DataCoverage":"Độ phủ dữ liệu",
            "BaseVulnerability":"Rủi ro cơ sở","StressVulnerability":"Rủi ro sau stress",
            "FundingCostShock_ppt":"Chi phí vốn +ppt","StressedNIM":"NIM sau stress","WatchFlag":"Cảnh báo","Rank":"Xếp hạng"
        })
        st.dataframe(show,use_container_width=True,hide_index=True)
    else: st.warning("Chưa có kết quả xếp hạng.")

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
    else: st.warning("Chưa có dữ liệu thực để chạy stress.")

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
    else: st.warning("Chưa có dữ liệu chi tiết.")

with tabs[4]:
    st.subheader("Thanh khoản hệ thống")
    st.info("V6.1 tập trung Cloud-ready cho bank overlay. Có thể nối lại toàn bộ daily LPI/OMO/Interbank engine của V5/V6 vào cùng app sau khi phần bank data chạy ổn định.")
    st.markdown("""
    **Luồng truyền dẫn đang sử dụng:**

    Thanh khoản hệ thống → chi phí vốn → NIM → vulnerability → cảnh báo ngân hàng.
    """)

with tabs[5]:
    st.subheader("Trạng thái tải dữ liệu")
    if len(bank_status):
        st.dataframe(bank_status,use_container_width=True,hide_index=True)
    coverage=pd.DataFrame({
        "Chỉ tiêu":["Số ngân hàng mục tiêu","Tải được dữ liệu","Tỷ lệ tải thành công"],
        "Giá trị":[len(BANKS),len(bank_actuals),len(bank_actuals)/len(BANKS) if BANKS else 0]
    })
    st.dataframe(coverage,use_container_width=True,hide_index=True)
    st.markdown("""
    **Quy tắc dữ liệu:** `ACTUAL` > `CALC` > `ESTIMATE` > `ASSUMPTION`.
    Các chỉ tiêu BCTC không lấy được từ Vnstock được để trống. Chỉ ngân hàng có độ phủ dữ liệu từ 50% trở lên mới được tính vulnerability.
    """)

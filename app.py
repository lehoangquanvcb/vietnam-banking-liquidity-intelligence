
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import json, re, time, os
from sponsor_bootstrap import install_sponsor, sponsor_available, set_runtime_key

ROOT=Path(__file__).parent
DATA=ROOT/"data"
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="Vietnam Banking Liquidity V6.4",layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem}
[data-testid="stMetricValue"]{font-size:1.45rem}
h1{font-size:1.95rem!important}
</style>
""",unsafe_allow_html=True)

st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG — V6.4")
st.caption("Sponsor-Aware • Vnstock Bronze → Community → Public Snapshot → Fallback • Stress thanh khoản • Xếp hạng ngân hàng")

def load(name):
    p=DATA/f"{name}.csv"
    try:return pd.read_csv(p)
    except:return pd.DataFrame()

def secret_api_key():
    try:
        return str(st.secrets.get("VNSTOCK_API_KEY","")).strip()
    except Exception:
        return ""

if "session_api_key" not in st.session_state:
    st.session_state.session_api_key=""
if "sponsor_install_message" not in st.session_state:
    st.session_state.sponsor_install_message=""

stored_key=secret_api_key()
api_key=stored_key or st.session_state.session_api_key
if api_key:
    set_runtime_key(api_key)

sponsor_ok,sponsor_detail=sponsor_available()
data_mode="BRONZE" if sponsor_ok and api_key else "FREE"

def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df,keys):
    if df is None or len(df)==0:return None
    if "id" in df.columns:
        ids=df["id"].astype(str).str.lower()
        for k in keys:
            m=ids.str.contains(k.lower(),regex=False)
            if m.any():
                for c in reversed(df.columns):
                    if c in ["id","name","unit","order","level","period","report_period"]:continue
                    v=pd.to_numeric(df.loc[m,c],errors="coerce").dropna()
                    if len(v):return float(v.iloc[0])
    if "name" in df.columns:
        names=df["name"].astype(str).map(norm)
        for k in keys:
            m=names.str.contains(norm(k),regex=False)
            if m.any():
                for c in reversed(df.columns):
                    if c=="name":continue
                    v=pd.to_numeric(df.loc[m,c],errors="coerce").dropna()
                    if len(v):return float(v.iloc[0])
    for c in df.columns:
        n=norm(c)
        if any(norm(k) in n for k in keys):
            v=pd.to_numeric(df[c],errors="coerce").dropna()
            if len(v):return float(v.iloc[0])
    return None

def latest_period(*dfs):
    for df in dfs:
        if df is None or len(df)==0:continue
        for c in ["period","report_period","report_time","year","quarter","time"]:
            if c in df.columns:
                v=df[c].dropna()
                if len(v):return str(v.iloc[0])
    return ""

@st.cache_data(ttl=6*3600,show_spinner=False)
def fetch_banks(mode, bank_list, key_marker):
    rows=[]; status=[]
    try:
        if mode=="BRONZE":
            from vnstock_data import Fundamental
            source_label="Vnstock Bronze Sponsor"
        else:
            from vnstock import Fundamental
            source_label="Vnstock Community"
    except Exception as e:
        return pd.DataFrame(),pd.DataFrame([["*","IMPORT_ERROR",str(e)]],columns=["Ticker","Status","Message"])

    fun=Fundamental()
    for symbol in bank_list:
        try:
            eq=fun.equity(symbol)
            # Try Sponsor/Unified UI signatures, then fallbacks.
            try: bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
            except Exception:
                try: bs=eq.balance_sheet(period="Q")
                except Exception: bs=eq.balance_sheet()
            try: inc=eq.income_statement(period="quarter",lang="en",format="long",com_type="bank")
            except Exception:
                try: inc=eq.income_statement(period="Q")
                except Exception: inc=eq.income_statement()
            try: ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
            except Exception:
                try: ratio=eq.financial_ratio()
                except Exception:
                    try: ratio=eq.ratio(period="Q")
                    except Exception: ratio=pd.DataFrame()

            loans=find_metric(bs,["customer loans","loans to customers","bs_customer_loans","cho vay khách hàng"])
            deposits=find_metric(bs,["customer deposits","deposits from customers","bs_customer_deposits","tiền gửi khách hàng"])
            assets=find_metric(bs,["total assets","bs_total_assets","tổng tài sản"])
            ib=find_metric(bs,["interbank borrowing","borrowings from other credit institutions","tiền gửi và vay các tổ chức tín dụng"])
            nim=find_metric(ratio,["nim","net interest margin"])
            ldr=find_metric(ratio,["ldr","loan to deposit"])
            casa=find_metric(ratio,["casa","current account saving account"])

            if ldr is None and loans is not None and deposits not in (None,0):ldr=loans/deposits
            ibdep=(ib/assets) if ib is not None and assets not in (None,0) else np.nan
            gap=((loans-deposits)/deposits) if loans is not None and deposits not in (None,0) else np.nan
            rows.append([symbol,latest_period(bs,inc,ratio),ldr,casa,ibdep,gap,nim,"ACTUAL",source_label])
            status.append([symbol,"OK",""])
        except Exception as e:
            status.append([symbol,"ERROR",str(e)[:240]])
        time.sleep(.06 if mode=="BRONZE" else .15)

    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Note"]
    return pd.DataFrame(rows,columns=cols),pd.DataFrame(status,columns=["Ticker","Status","Message"])

def clean_ratio(x):
    x=pd.to_numeric(x,errors="coerce")
    return np.where(np.abs(x)>2,x/100.0,x)

def score(df,mult=1.35,max_pass=2.0):
    if df.empty:return df
    d=df.copy()
    for c in ["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]:
        d[c]=clean_ratio(d[c])
    d["LiquidityBuffer"]=1-d["LDR"]
    fields=["LDR","CASA","InterbankDep","CreditDepositGap","NIM","LiquidityBuffer"]
    d["Coverage"]=d[fields].notna().mean(axis=1)
    raw=(50+35*(d["LDR"]-.85)-25*(d["CASA"]-.20)+45*d["InterbankDep"]
         +30*d["CreditDepositGap"]-10*(d["NIM"]-.03)-20*(d["LiquidityBuffer"]-.15))
    d["BaseVulnerability"]=raw.clip(0,100)
    d.loc[d["Coverage"]<.5,"BaseVulnerability"]=np.nan
    d["StressVulnerability"]=(d["BaseVulnerability"]*mult).clip(0,100)
    d["FundingCostShock_ppt"]=max_pass*d["StressVulnerability"]/100
    d["StressedNIM"]=np.maximum(0,d["NIM"]-d["FundingCostShock_ppt"]/100)
    d["Watch"]=np.select([(d["StressVulnerability"]>=75)|(d["StressedNIM"]<.02),d["StressVulnerability"]>=60],
                         ["ĐỎ","VÀNG"],default="XANH")
    d["Rank"]=d["StressVulnerability"].rank(ascending=False,method="min")
    return d.sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

macro=load("macro_public_snapshot")
fallback=load("bank_fallback_assumptions")

with st.sidebar:
    st.subheader("KẾT NỐI VNSTOCK")
    if sponsor_ok and api_key:
        st.success("🟢 BRONZE CONNECTED")
        st.caption("Backend đang dùng `vnstock_data` Sponsor.")
    elif api_key:
        st.warning("🟠 Có API Key nhưng Sponsor chưa cài/kết nối.")
    else:
        st.info("🔵 FREE MODE")

    if not stored_key:
        key_input=st.text_input(
            "Vnstock API Key",
            type="password",
            value=st.session_state.session_api_key,
            help="Chỉ lưu trong session hiện tại; không ghi ra GitHub/file."
        )
        if st.button("Kết nối Bronze"):
            st.session_state.session_api_key=key_input.strip()
            if st.session_state.session_api_key:
                with st.spinner("Đang cài/xác thực Vnstock Sponsor..."):
                    ok,msg=install_sponsor(st.session_state.session_api_key)
                st.session_state.sponsor_install_message=msg
                fetch_banks.clear()
                st.rerun()
    else:
        st.success("API Key được đọc từ Streamlit Secrets.")

    if st.session_state.sponsor_install_message and not sponsor_ok:
        with st.expander("Chi tiết kết nối Sponsor"):
            st.code(st.session_state.sponsor_install_message)

    st.divider()
    st.write("**Ưu tiên dữ liệu:**")
    st.write("1. Bronze Sponsor")
    st.write("2. Vnstock Community")
    st.write("3. Public ACTUAL snapshot")
    st.write("4. ASSUMPTION fallback")

    if st.button("Làm mới dữ liệu"):
        fetch_banks.clear()
        st.rerun()

# Fetch Sponsor first if connected; if no useful rows, automatically try Community.
live=pd.DataFrame(); live_status=pd.DataFrame()
mode_used="BRONZE" if sponsor_ok and api_key else "FREE"
key_marker="configured" if api_key else "none"

with st.spinner(f"Đang tải dữ liệu ngân hàng ({mode_used})..."):
    live,live_status=fetch_banks(mode_used,tuple(BANKS),key_marker)

def useful(df):
    if df.empty:return pd.DataFrame()
    return df[df[["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]].notna().sum(axis=1)>=3].copy()

live_good=useful(live)
if mode_used=="BRONZE" and len(live_good)<5:
    free,free_status=fetch_banks("FREE",tuple(BANKS),"fallback")
    free_good=useful(free)
    # Bronze actual rows take priority; Free fills missing tickers.
    if len(free_good):
        free_good=free_good[~free_good["Ticker"].isin(live_good["Ticker"])]
        live_good=pd.concat([live_good,free_good],ignore_index=True)
        live_status=pd.concat([live_status,free_status],ignore_index=True)

# Fill only missing tickers with explicit assumptions.
fb=fallback[~fallback["Ticker"].isin(live_good["Ticker"])] if len(live_good) else fallback.copy()
bank_data=pd.concat([live_good,fb],ignore_index=True) if len(live_good) else fb

actual_count=int((bank_data["Data Type"]=="ACTUAL").sum())
assumption_count=int((bank_data["Data Type"]=="ASSUMPTION").sum())
bronze_count=int(bank_data["Note"].astype(str).str.contains("Bronze",case=False).sum())
free_count=int(bank_data["Note"].astype(str).str.contains("Community",case=False).sum())
base_score=score(bank_data)

def mval(ind):
    q=macro[macro["Indicator"]==ind]
    return float(q["Value"].iloc[0]) if len(q) else np.nan
credit=mval("Tăng trưởng tín dụng YTD")
deposit=mval("Tăng trưởng huy động YTD")
cpi=mval("CPI YoY")
trade=mval("Cán cân thương mại")
funding_gap=credit-deposit if pd.notna(credit) and pd.notna(deposit) else np.nan
system_pressure=np.clip((funding_gap/3 if pd.notna(funding_gap) else 0)+(max(0,cpi-4)/2 if pd.notna(cpi) else 0)+(max(0,-trade)/20 if pd.notna(trade) else 0),0,3)

tabs=st.tabs(["Trung tâm điều hành","Thanh khoản hệ thống","Xếp hạng ngân hàng","Mô phỏng Stress","Chi tiết ngân hàng","Nguồn & chất lượng dữ liệu"])

with tabs[0]:
    st.subheader("Trạng thái kết nối")
    c0,c00,c000,c0000=st.columns(4)
    c0.metric("Bronze ACTUAL",bronze_count)
    c00.metric("Free ACTUAL",free_count)
    c000.metric("Fallback",assumption_count)
    c0000.metric("Backend","BRONZE" if bronze_count else ("FREE" if free_count else "FALLBACK"))
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Tín dụng YTD",f"{credit:.2f}%")
    c2.metric("Huy động YTD",f"{deposit:.2f}%")
    c3.metric("Funding gap",f"{funding_gap:.2f} ppt")
    c4.metric("System Pressure",f"{system_pressure:.2f}/3")
    if bronze_count:
        st.success(f"Đang sử dụng dữ liệu Bronze Sponsor cho {bronze_count} ngân hàng.")
    elif api_key and not sponsor_ok:
        st.warning("API Key đã có nhưng Sponsor runtime chưa kết nối được; app đang tự fallback để không bị gián đoạn.")
    else:
        st.info("App chưa dùng Bronze. Nhập API Key ở sidebar hoặc cấu hình Streamlit Secrets.")
    top=base_score.head(10)
    st.subheader("Top 10 nhạy cảm với stress thanh khoản")
    st.bar_chart(top.set_index("Ticker")[["StressVulnerability"]],height=320)
    st.dataframe(top[["Ticker","Note","Data Type","LDR","CASA","NIM","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]],
                 use_container_width=True,hide_index=True)

with tabs[1]:
    st.dataframe(macro,use_container_width=True,hide_index=True)
    st.markdown(f"""
- Tín dụng YTD: **{credit:.2f}%**
- Huy động YTD: **{deposit:.2f}%**
- Funding gap: **{funding_gap:.2f} điểm %**
- CPI YoY: **{cpi:.2f}%**
- Trade balance 6T: **{trade:.2f} tỷ USD**
- System Pressure Proxy: **{system_pressure:.2f}/3** (`CALC`, không phải dự trữ thực tại NHNN).
""")
    st.progress(min(system_pressure/3,1.0))

with tabs[2]:
    st.dataframe(base_score,use_container_width=True,hide_index=True)

with tabs[3]:
    c1,c2,c3=st.columns(3)
    mult=c1.slider("Hệ số stress hệ thống",1.0,2.2,1.35,.05)
    maxpass=c2.slider("Funding cost pass-through tối đa (ppt)",0.5,4.0,2.0,.25)
    lpi=c3.slider("Liquidity Pressure scenario",0.0,3.0,float(system_pressure),.1)
    d=score(bank_data,mult*(1+0.12*lpi),maxpass)
    st.bar_chart(d.set_index("Ticker")[["BaseVulnerability","StressVulnerability"]],height=360)
    st.dataframe(d[["Ticker","Note","Data Type","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]],
                 use_container_width=True,hide_index=True)

with tabs[4]:
    tick=st.selectbox("Chọn ngân hàng",base_score.Ticker.tolist())
    r=base_score[base_score.Ticker==tick].iloc[0]
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Nguồn",r["Note"])
    c2.metric("Stress Vulnerability",f"{r.StressVulnerability:.1f}")
    c3.metric("Funding cost shock",f"+{r.FundingCostShock_ppt:.2f} ppt")
    c4.metric("NIM sau stress",f"{r.StressedNIM:.2%}" if pd.notna(r.StressedNIM) else "N/A")
    detail=pd.DataFrame([
      ["LDR",r.LDR],["CASA",r.CASA],["Phụ thuộc liên ngân hàng",r.InterbankDep],
      ["Khoảng cách tín dụng-tiền gửi",r.CreditDepositGap],["NIM",r.NIM],
      ["Độ phủ dữ liệu",r.Coverage],["Cảnh báo",r.Watch]
    ],columns=["Chỉ tiêu","Giá trị"])
    st.dataframe(detail,use_container_width=True,hide_index=True)
    if r["Data Type"]=="ASSUMPTION":
        st.warning("Đang dùng giả định fallback, không phải BCTC thực.")

with tabs[5]:
    st.subheader("Backend")
    status_table=pd.DataFrame([
        ["API Key", "Configured" if api_key else "Missing"],
        ["vnstock_data Sponsor", "Available" if sponsor_ok else "Unavailable"],
        ["Bronze rows", bronze_count],
        ["Community rows", free_count],
        ["Assumption rows", assumption_count],
    ],columns=["Component","Status"])
    st.dataframe(status_table,use_container_width=True,hide_index=True)

    st.subheader("API/Data errors")
    if len(live_status):
        st.dataframe(live_status,use_container_width=True,hide_index=True)
    st.info("API Key không được ghi vào CSV, GitHub hoặc log hiển thị của app. Khi nhập ở sidebar, key chỉ tồn tại trong Streamlit session hiện tại.")

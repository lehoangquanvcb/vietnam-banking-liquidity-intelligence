
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import json,re,time,os
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from sponsor_bootstrap import sponsor_available, configure_key, install_sponsor

ROOT=Path(__file__).parent
DATA=ROOT/"data"
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

st.set_page_config(page_title="Vietnam Banking Liquidity V6.5",layout="wide")
st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG — V6.5")
st.caption("Stable Sponsor • Timeout • Circuit Breaker • Bronze → Free → Public → Assumption")

def load(n):
    try:return pd.read_csv(DATA/f"{n}.csv")
    except:return pd.DataFrame()

def safe_df(df):
    """Prevent ArrowInvalid from mixed bytes/objects while preserving numeric columns."""
    if df is None:return pd.DataFrame()
    x=df.copy()
    for c in x.columns:
        if x[c].dtype=="object":
            nonnull=x[c].dropna()
            if len(nonnull):
                types={type(v) for v in nonnull.head(100)}
                if len(types)>1 or bytes in types or bytearray in types:
                    x[c]=x[c].map(lambda v:"" if pd.isna(v) else str(v))
    return x

def secret_key():
    try:return str(st.secrets.get("VNSTOCK_API_KEY","")).strip()
    except:return ""

if "manual_key" not in st.session_state: st.session_state.manual_key=""
if "install_msg" not in st.session_state: st.session_state.install_msg=""
if "api_disabled" not in st.session_state: st.session_state.api_disabled=False

key=secret_key() or st.session_state.manual_key
if key:configure_key(key)
sponsor_ok,sponsor_detail=sponsor_available()

def norm(s):return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df,keys):
    if df is None or len(df)==0:return None
    for label_col in [c for c in ["id","name"] if c in df.columns]:
        lab=df[label_col].astype(str).map(norm)
        for k in keys:
            m=lab.str.contains(norm(k),regex=False)
            if m.any():
                for c in reversed(df.columns):
                    if c in ["id","name","unit","period","report_period","order","level"]:continue
                    v=pd.to_numeric(df.loc[m,c],errors="coerce").dropna()
                    if len(v):return float(v.iloc[0])
    for c in df.columns:
        if any(norm(k) in norm(c) for k in keys):
            v=pd.to_numeric(df[c],errors="coerce").dropna()
            if len(v):return float(v.iloc[0])
    return None

def period_of(*dfs):
    for df in dfs:
        if df is None or len(df)==0:continue
        for c in ["period","report_period","report_time","year","quarter","time"]:
            if c in df.columns and len(df[c].dropna()):return str(df[c].dropna().iloc[0])
    return ""

def get_fun(mode):
    if mode=="BRONZE":
        from vnstock_data import Fundamental
    else:
        from vnstock import Fundamental
    return Fundamental()

def fetch_one(mode,symbol):
    fun=get_fun(mode)
    eq=fun.equity(symbol)
    try:bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
    except:
        try:bs=eq.balance_sheet(period="Q")
        except:bs=eq.balance_sheet()
    try:ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
    except:
        try:ratio=eq.financial_ratio()
        except:
            try:ratio=eq.ratio(period="Q")
            except:ratio=pd.DataFrame()
    loans=find_metric(bs,["customer loans","loans to customers","cho vay khách hàng"])
    dep=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
    assets=find_metric(bs,["total assets","tổng tài sản"])
    ib=find_metric(bs,["interbank borrowing","borrowings from other credit institutions","tiền gửi và vay các tổ chức tín dụng"])
    ldr=find_metric(ratio,["ldr","loan to deposit"])
    casa=find_metric(ratio,["casa","current account saving account"])
    nim=find_metric(ratio,["nim","net interest margin"])
    if ldr is None and loans is not None and dep not in (None,0):ldr=loans/dep
    ibdep=ib/assets if ib is not None and assets not in (None,0) else np.nan
    gap=(loans-dep)/dep if loans is not None and dep not in (None,0) else np.nan
    return [symbol,period_of(bs,ratio),ldr,casa,ibdep,gap,nim,"ACTUAL",mode]

def fetch_probe(mode,symbols,timeout_total=12):
    """Probe at most 3 tickers. If not enough success, circuit-break immediately."""
    ex=ThreadPoolExecutor(max_workers=min(3,len(symbols)))
    futures={ex.submit(fetch_one,mode,s):s for s in symbols}
    done,not_done=wait(futures.keys(),timeout=timeout_total)
    rows=[];errs=[]
    for f in done:
        sym=futures[f]
        try:rows.append(f.result());errs.append([sym,"OK",""])
        except Exception as e:errs.append([sym,"ERROR",str(e)[:180]])
    for f in not_done:
        f.cancel()
        errs.append([futures[f],"TIMEOUT",f">{timeout_total}s"])
    ex.shutdown(wait=False,cancel_futures=True)
    return rows,errs

def fetch_remaining(mode,symbols,timeout_total=20):
    if not symbols:return [],[]
    ex=ThreadPoolExecutor(max_workers=min(6,len(symbols)))
    futures={ex.submit(fetch_one,mode,s):s for s in symbols}
    done,not_done=wait(futures.keys(),timeout=timeout_total)
    rows=[];errs=[]
    for f in done:
        sym=futures[f]
        try:rows.append(f.result());errs.append([sym,"OK",""])
        except Exception as e:errs.append([sym,"ERROR",str(e)[:180]])
    for f in not_done:
        f.cancel();errs.append([futures[f],"TIMEOUT",f">{timeout_total}s"])
    ex.shutdown(wait=False,cancel_futures=True)
    return rows,errs

@st.cache_data(ttl=6*3600,show_spinner=False)
def fetch_backend(mode):
    probe=BANKS[:3]
    rows,errs=fetch_probe(mode,probe,12)
    good=sum(1 for r in rows if sum(pd.notna(r[i]) for i in range(2,7))>=3)
    # Circuit breaker: need at least 2 useful successes among 3 probes.
    if good<2:
        return pd.DataFrame(columns=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode"]), \
               pd.DataFrame(errs,columns=["Ticker","Status","Message"]), "CIRCUIT_OPEN"
    remaining=[s for s in BANKS if s not in probe]
    r2,e2=fetch_remaining(mode,remaining,20)
    rows+=r2;errs+=e2
    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode"]
    return pd.DataFrame(rows,columns=cols),pd.DataFrame(errs,columns=["Ticker","Status","Message"]),"OK"

def ratio(x):
    x=pd.to_numeric(x,errors="coerce")
    return np.where(np.abs(x)>2,x/100,x)

def score(df,m=1.35,p=2.0):
    d=df.copy()
    for c in ["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]:d[c]=ratio(d[c])
    d["LiquidityBuffer"]=1-d["LDR"]
    fields=["LDR","CASA","InterbankDep","CreditDepositGap","NIM","LiquidityBuffer"]
    d["Coverage"]=d[fields].notna().mean(axis=1)
    raw=50+35*(d.LDR-.85)-25*(d.CASA-.20)+45*d.InterbankDep+30*d.CreditDepositGap-10*(d.NIM-.03)-20*(d.LiquidityBuffer-.15)
    d["BaseVulnerability"]=raw.clip(0,100)
    d.loc[d.Coverage<.5,"BaseVulnerability"]=np.nan
    d["StressVulnerability"]=(d.BaseVulnerability*m).clip(0,100)
    d["FundingCostShock_ppt"]=p*d.StressVulnerability/100
    d["StressedNIM"]=np.maximum(0,d.NIM-d.FundingCostShock_ppt/100)
    d["Watch"]=np.select([(d.StressVulnerability>=75)|(d.StressedNIM<.02),d.StressVulnerability>=60],["ĐỎ","VÀNG"],default="XANH")
    return d.sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

macro=load("macro_public_snapshot")
fallback=load("bank_fallback_assumptions")

with st.sidebar:
    st.subheader("KẾT NỐI VNSTOCK")
    if sponsor_ok and key:st.success("🟢 BRONZE CONNECTED")
    elif key:st.warning("🟠 Có API Key; Sponsor chưa kết nối")
    else:st.info("🔵 FREE MODE")

    if not secret_key():
        k=st.text_input("Vnstock API Key",type="password",value=st.session_state.manual_key)
        if st.button("Cài/Kết nối Sponsor"):
            st.session_state.manual_key=k.strip()
            if k.strip():
                with st.spinner("Đang thử cài Sponsor (tối đa 90 giây)..."):
                    ok,msg=install_sponsor(k.strip(),90)
                st.session_state.install_msg=msg
                fetch_backend.clear()
                st.rerun()
    else:
        st.success("API Key đã đọc từ Streamlit Secrets.")

    if st.session_state.install_msg and not sponsor_ok:
        with st.expander("Chi tiết kết nối"):
            st.code(st.session_state.install_msg)

    st.divider()
    st.write("API timeout: **12s probe / 20s batch**")
    st.write("Circuit breaker: **2/3 probe success**")
    if st.button("Làm mới API/cache"):
        fetch_backend.clear()
        st.session_state.api_disabled=False
        st.rerun()

# Backend logic. No automatic Sponsor install.
api_status=[]
live=pd.DataFrame()
bronze_state="NOT_TRIED";free_state="NOT_TRIED"

if not st.session_state.api_disabled:
    if sponsor_ok and key:
        with st.spinner("Kiểm tra Bronze (tối đa ~12 giây)..."):
            b,bs,bronze_state=fetch_backend("BRONZE")
        api_status.append(bs)
        if bronze_state=="OK":live=b
    if live.empty:
        with st.spinner("Kiểm tra Vnstock Free (tối đa ~12 giây)..."):
            f,fs,free_state=fetch_backend("FREE")
        api_status.append(fs)
        if free_state=="OK":live=f
    if bronze_state=="CIRCUIT_OPEN" and free_state=="CIRCUIT_OPEN":
        st.session_state.api_disabled=True

status=pd.concat(api_status,ignore_index=True) if api_status else pd.DataFrame(columns=["Ticker","Status","Message"])

# Keep only useful actual rows, then fill missing tickers with explicit fallback assumptions.
if len(live):
    live=live[live[["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]].notna().sum(axis=1)>=3].copy()
fb=fallback[~fallback.Ticker.isin(live.Ticker)] if len(live) else fallback.copy()
bank=pd.concat([live,fb],ignore_index=True) if len(live) else fb

bronze_count=int((bank["Source Mode"]=="BRONZE").sum())
free_count=int((bank["Source Mode"]=="FREE").sum())
assumption_count=int((bank["Data Type"]=="ASSUMPTION").sum())
sc=score(bank)

def mv(ind):
    q=macro[macro.Indicator==ind]
    return float(q.Value.iloc[0]) if len(q) else np.nan
credit,dep,cpi,trade=mv("Tăng trưởng tín dụng YTD"),mv("Tăng trưởng huy động YTD"),mv("CPI YoY"),mv("Cán cân thương mại")
gap=credit-dep
pressure=float(np.clip(gap/3+max(0,cpi-4)/2+max(0,-trade)/20,0,3))

tabs=st.tabs(["Trung tâm điều hành","Xếp hạng ngân hàng","Mô phỏng Stress","Chi tiết ngân hàng","Thanh khoản hệ thống","Chất lượng dữ liệu"])

with tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Bronze ACTUAL",bronze_count);c2.metric("Free ACTUAL",free_count);c3.metric("Fallback",assumption_count);c4.metric("System Pressure",f"{pressure:.2f}/3")
    if bronze_count:st.success(f"Đang dùng Bronze ACTUAL cho {bronze_count} ngân hàng.")
    elif free_count:st.info(f"Đang dùng Free ACTUAL cho {free_count} ngân hàng; phần còn lại fallback.")
    else:st.warning("API circuit breaker đang mở hoặc live không đủ dữ liệu. Dashboard dùng fallback có nhãn, không tiếp tục gọi API trong các rerun.")
    top=sc.head(10)
    st.bar_chart(top.set_index("Ticker")[["StressVulnerability"]],height=320)
    st.dataframe(safe_df(top[["Ticker","Source Mode","Data Type","LDR","CASA","NIM","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]]),hide_index=True)

with tabs[1]:
    st.dataframe(safe_df(sc),hide_index=True)

with tabs[2]:
    a,b,c=st.columns(3)
    mult=a.slider("Hệ số stress",1.0,2.2,1.35,.05)
    passt=b.slider("Funding pass-through (ppt)",.5,4.0,2.0,.25)
    lpi=c.slider("Liquidity pressure",0.0,3.0,pressure,.1)
    d=score(bank,mult*(1+.12*lpi),passt)
    st.bar_chart(d.set_index("Ticker")[["BaseVulnerability","StressVulnerability"]],height=340)
    st.dataframe(safe_df(d[["Ticker","Source Mode","Data Type","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]]),hide_index=True)

with tabs[3]:
    t=st.selectbox("Ngân hàng",sc.Ticker.tolist())
    r=sc[sc.Ticker==t].iloc[0]
    q1,q2,q3,q4=st.columns(4)
    q1.metric("Nguồn",str(r["Source Mode"]));q2.metric("Vulnerability",f"{r.StressVulnerability:.1f}")
    q3.metric("Funding cost",f"+{r.FundingCostShock_ppt:.2f} ppt");q4.metric("Stressed NIM",f"{r.StressedNIM:.2%}")
    st.dataframe(safe_df(pd.DataFrame(r).reset_index().rename(columns={"index":"Chỉ tiêu",0:"Giá trị"})),hide_index=True)

with tabs[4]:
    st.dataframe(safe_df(macro),hide_index=True)
    st.metric("Funding gap",f"{gap:.2f} ppt")
    st.metric("System Pressure Proxy",f"{pressure:.2f}/3")

with tabs[5]:
    st.write({"Sponsor_available":sponsor_ok,"Bronze_state":bronze_state,"Free_state":free_state,"Circuit_disabled":st.session_state.api_disabled})
    st.dataframe(safe_df(status),hide_index=True)
    st.caption("Nếu cả Bronze và Free fail probe, app dừng gọi API trong session. Bấm 'Làm mới API/cache' để thử lại.")

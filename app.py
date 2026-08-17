
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import json,re,time,os,sys,subprocess,urllib.request,importlib
from concurrent.futures import ThreadPoolExecutor, wait

ROOT=Path(__file__).parent
DATA=ROOT/"data"
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

INSTALLER_URL="https://vnstocks.com/files/vnstock-cli-installer.run"
SPONSOR_VENV=Path("/tmp/vnstock_sponsor_venv")
INSTALLER_PATH=Path("/tmp/vnstock-cli-installer.run")

st.set_page_config(page_title="Vietnam Banking Liquidity V6.5.1",layout="wide")
st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG — V6.5.1")
st.caption("Sponsor Hotfix • Self-contained • Guest rate-limit safe • Bronze → Free Probe → Fallback")

# ---------- Sponsor helpers embedded in app.py ----------
def add_sponsor_site():
    if SPONSOR_VENV.exists():
        for p in list(SPONSOR_VENV.glob("lib/python*/site-packages"))+list(SPONSOR_VENV.glob("Lib/site-packages")):
            s=str(p)
            if s not in sys.path:
                sys.path.insert(0,s)
    importlib.invalidate_caches()

def sponsor_available():
    add_sponsor_site()
    try:
        import vnstock_data
        return True,getattr(vnstock_data,"__version__","available")
    except Exception as e:
        return False,str(e)

def configure_key(key):
    if key:
        os.environ["VNSTOCK_API_KEY"]=key.strip()
        os.environ["VNSTOCK_INTERACTIVE"]="0"
        os.environ["VNSTOCK_LANGUAGE"]="2"

def install_sponsor(key,timeout=90):
    if not key or len(key.strip())<8:
        return False,"API Key chưa hợp lệ."
    configure_key(key)
    ok,detail=sponsor_available()
    if ok:
        return True,f"vnstock_data đã sẵn sàng ({detail})"
    os.environ["VNSTOCK_VENV_PATH"]=str(SPONSOR_VENV)
    try:
        urllib.request.urlretrieve(INSTALLER_URL,INSTALLER_PATH)
        INSTALLER_PATH.chmod(0o755)
    except Exception as e:
        return False,f"Không tải được installer: {e}"
    cmd=[str(INSTALLER_PATH),"--","--non-interactive","--venv-path",str(SPONSOR_VENV),"--language","vi"]
    try:
        p=subprocess.run(cmd,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return False,"Installer quá 90 giây; đã dừng."
    except Exception as e:
        return False,f"Lỗi installer: {e}"
    add_sponsor_site()
    ok,detail=sponsor_available()
    if ok:
        return True,f"Kết nối Sponsor thành công ({detail})"
    log=(p.stdout or "")[-1600:].replace(key.strip(),"***REDACTED***")
    return False,f"Không import được vnstock_data sau cài đặt. Exit={p.returncode}\n{log}"

# ---------- Generic helpers ----------
def load(n):
    try:return pd.read_csv(DATA/f"{n}.csv")
    except:return pd.DataFrame()

def safe_df(df):
    if df is None:return pd.DataFrame()
    x=df.copy()
    for c in x.columns:
        if x[c].dtype=="object":
            x[c]=x[c].map(lambda v:"" if pd.isna(v) else (v.decode(errors="replace") if isinstance(v,(bytes,bytearray)) else str(v)))
    return x

def secret_key():
    try:return str(st.secrets.get("VNSTOCK_API_KEY","")).strip()
    except:return ""

if "manual_key" not in st.session_state:st.session_state.manual_key=""
if "install_msg" not in st.session_state:st.session_state.install_msg=""
if "free_circuit_open" not in st.session_state:st.session_state.free_circuit_open=False
if "bronze_circuit_open" not in st.session_state:st.session_state.bronze_circuit_open=False

key=secret_key() or st.session_state.manual_key
configure_key(key)
sponsor_ok,sponsor_detail=sponsor_available()

def norm(s):return re.sub(r"[^a-z0-9]+"," ",str(s).lower()).strip()

def find_metric(df,keys):
    if df is None or len(df)==0:return None
    for lc in [c for c in ["id","name"] if c in df.columns]:
        labels=df[lc].astype(str).map(norm)
        for k in keys:
            mask=labels.str.contains(norm(k),regex=False)
            if mask.any():
                for c in reversed(df.columns):
                    if c in ["id","name","unit","period","report_period","order","level"]:continue
                    v=pd.to_numeric(df.loc[mask,c],errors="coerce").dropna()
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
            if c in df.columns and len(df[c].dropna()):
                return str(df[c].dropna().iloc[0])
    return ""

def fundamental(mode):
    if mode=="BRONZE":
        from vnstock_data import Fundamental
    else:
        from vnstock import Fundamental
    return Fundamental()

def fetch_one(mode,symbol):
    fun=fundamental(mode)
    eq=fun.equity(symbol)
    try:bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try:bs=eq.balance_sheet(period="Q")
        except Exception:bs=eq.balance_sheet()
    try:ratio=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try:ratio=eq.financial_ratio()
        except Exception:
            try:ratio=eq.ratio(period="Q")
            except Exception:ratio=pd.DataFrame()
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

def parallel_fetch(mode,symbols,timeout,max_workers):
    ex=ThreadPoolExecutor(max_workers=max_workers)
    fut={ex.submit(fetch_one,mode,s):s for s in symbols}
    done,pending=wait(fut.keys(),timeout=timeout)
    rows=[];status=[]
    for f in done:
        s=fut[f]
        try:
            rows.append(f.result());status.append([s,"OK",""])
        except Exception as e:
            msg=str(e)
            status.append([s,"ERROR",msg[:240]])
    for f in pending:
        f.cancel();status.append([fut[f],"TIMEOUT",f">{timeout}s"])
    ex.shutdown(wait=False,cancel_futures=True)
    return rows,status

def useful_rows(rows):
    return [r for r in rows if sum(pd.notna(r[i]) for i in range(2,7))>=3]

@st.cache_data(ttl=6*3600,show_spinner=False)
def fetch_bronze():
    # Bronze only: 3-bank probe then full universe.
    rows,status=parallel_fetch("BRONZE",BANKS[:3],12,3)
    good=useful_rows(rows)
    if len(good)<2:
        return pd.DataFrame(),pd.DataFrame(status,columns=["Ticker","Status","Message"]),"CIRCUIT_OPEN"
    r2,s2=parallel_fetch("BRONZE",BANKS[3:],20,6)
    rows+=r2;status+=s2
    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode"]
    return pd.DataFrame(useful_rows(rows),columns=cols),pd.DataFrame(status,columns=["Ticker","Status","Message"]),"OK"

@st.cache_data(ttl=6*3600,show_spinner=False)
def fetch_free_probe():
    # Guest-safe: ONLY 3 tickers. Never full 20-bank batch.
    rows,status=parallel_fetch("FREE",BANKS[:3],12,1)
    good=useful_rows(rows)
    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode"]
    state="OK_PROBE_ONLY" if len(good)>=1 else "CIRCUIT_OPEN"
    return pd.DataFrame(good,columns=cols),pd.DataFrame(status,columns=["Ticker","Status","Message"]),state

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
    if sponsor_ok and key:
        st.success("🟢 BRONZE CONNECTED")
    elif key:
        st.warning("🟠 Có API Key; Sponsor chưa cài/kết nối")
    else:
        st.info("🔵 FREE/GUEST MODE")

    if not secret_key():
        k=st.text_input("Vnstock API Key",type="password",value=st.session_state.manual_key)
        if st.button("Cài/Kết nối Sponsor"):
            st.session_state.manual_key=k.strip()
            if k.strip():
                with st.spinner("Đang cài Sponsor (tối đa 90 giây)..."):
                    ok,msg=install_sponsor(k.strip(),90)
                st.session_state.install_msg=msg
                fetch_bronze.clear()
                st.rerun()
    else:
        st.success("API Key đã đọc từ Streamlit Secrets.")

    if st.session_state.install_msg and not sponsor_ok:
        with st.expander("Chi tiết kết nối"):
            st.code(st.session_state.install_msg)

    st.divider()
    st.write("**Bảo vệ rate limit**")
    st.write("Bronze: 3 probe → full 20 nếu pass")
    st.write("Free/Guest: **chỉ 3 probe**, không gọi 20 mã")
    if st.button("Làm mới cache/API"):
        fetch_bronze.clear();fetch_free_probe.clear()
        st.session_state.free_circuit_open=False
        st.session_state.bronze_circuit_open=False
        st.rerun()

# Backend decision
status_frames=[]
live=pd.DataFrame()
bronze_state="NOT_AVAILABLE"
free_state="NOT_TRIED"

if sponsor_ok and key and not st.session_state.bronze_circuit_open:
    with st.spinner("Kiểm tra Bronze..."):
        live,bs,bronze_state=fetch_bronze()
    status_frames.append(bs)
    if bronze_state=="CIRCUIT_OPEN":
        st.session_state.bronze_circuit_open=True

# Only small Guest probe if Bronze has no useful rows
if live.empty and not st.session_state.free_circuit_open:
    with st.spinner("Kiểm tra Free/Guest tối đa 3 mã..."):
        free,fs,free_state=fetch_free_probe()
    status_frames.append(fs)
    if free_state=="CIRCUIT_OPEN":
        st.session_state.free_circuit_open=True
    else:
        live=free

status=pd.concat(status_frames,ignore_index=True) if status_frames else pd.DataFrame(columns=["Ticker","Status","Message"])

fb=fallback[~fallback.Ticker.isin(live.Ticker)] if len(live) else fallback.copy()
bank=pd.concat([live,fb],ignore_index=True) if len(live) else fb.copy()

bronze_count=int((bank["Source Mode"]=="BRONZE").sum())
free_count=int((bank["Source Mode"]=="FREE").sum())
assump=int((bank["Data Type"]=="ASSUMPTION").sum())
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
    c1.metric("Bronze ACTUAL",bronze_count)
    c2.metric("Free ACTUAL",free_count)
    c3.metric("Fallback",assump)
    c4.metric("System Pressure",f"{pressure:.2f}/3")
    if bronze_count:
        st.success(f"Bronze đang cung cấp dữ liệu ACTUAL cho {bronze_count} ngân hàng.")
    elif free_count:
        st.info(f"Free/Guest chỉ probe {free_count} ngân hàng để tránh rate limit; phần còn lại dùng fallback.")
    else:
        st.warning("Live API không khả dụng hoặc circuit đã mở. App không tiếp tục gọi API trong rerun.")
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
    q1.metric("Nguồn",str(r["Source Mode"]))
    q2.metric("Vulnerability",f"{r.StressVulnerability:.1f}")
    q3.metric("Funding cost",f"+{r.FundingCostShock_ppt:.2f} ppt")
    q4.metric("Stressed NIM",f"{r.StressedNIM:.2%}")
    detail=pd.DataFrame({
        "Chỉ tiêu":["LDR","CASA","Interbank dependence","Credit-deposit gap","NIM","Coverage","Watch"],
        "Giá trị":[r.LDR,r.CASA,r.InterbankDep,r.CreditDepositGap,r.NIM,r.Coverage,r.Watch]
    })
    st.dataframe(safe_df(detail),hide_index=True)

with tabs[4]:
    st.dataframe(safe_df(macro),hide_index=True)
    st.metric("Funding gap",f"{gap:.2f} ppt")
    st.metric("System Pressure Proxy",f"{pressure:.2f}/3")

with tabs[5]:
    st.write({
        "Sponsor_available":sponsor_ok,
        "Bronze_state":bronze_state,
        "Free_state":free_state,
        "Bronze_circuit":st.session_state.bronze_circuit_open,
        "Free_circuit":st.session_state.free_circuit_open
    })
    st.dataframe(safe_df(status),hide_index=True)
    st.caption("Guest/Free không bao giờ tải toàn bộ 20 ngân hàng trong V6.5.1.")

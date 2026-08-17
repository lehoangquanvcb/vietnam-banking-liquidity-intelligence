
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import json,re,os,sys,subprocess,urllib.request,importlib
from concurrent.futures import ThreadPoolExecutor, wait

ROOT=Path(__file__).parent
DATA=ROOT/"data"
BANKS=json.loads((ROOT/"config"/"banks.json").read_text(encoding="utf-8"))

INSTALLER_URL="https://vnstocks.com/files/vnstock-cli-installer.run"
SPONSOR_VENV=Path("/tmp/vnstock_sponsor_venv")
INSTALLER_PATH=Path("/tmp/vnstock-cli-installer.run")

st.set_page_config(page_title="Vietnam Banking Liquidity Intelligence",layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem}
[data-testid="stMetricValue"]{font-size:1.45rem}
h1{font-size:1.9rem!important}
</style>
""",unsafe_allow_html=True)

st.title("TRUNG TÂM PHÂN TÍCH THANH KHOẢN HỆ THỐNG & NGÂN HÀNG")
st.caption("Vnstock Bronze Sponsor • Thanh khoản hệ thống • Stress Test • Xếp hạng ngân hàng")

# ---------------- Sponsor runtime ----------------
def add_sponsor_site():
    if SPONSOR_VENV.exists():
        for p in list(SPONSOR_VENV.glob("lib/python*/site-packages"))+list(SPONSOR_VENV.glob("Lib/site-packages")):
            s=str(p)
            if s not in sys.path:sys.path.insert(0,s)
    importlib.invalidate_caches()

def configure_key(key):
    if key:
        os.environ["VNSTOCK_API_KEY"]=key.strip()
        os.environ["VNSTOCK_INTERACTIVE"]="0"
        os.environ["VNSTOCK_LANGUAGE"]="2"
        os.environ["VNSTOCK_VENV_PATH"]=str(SPONSOR_VENV)

def sponsor_available():
    add_sponsor_site()
    try:
        import vnstock_data
        return True,getattr(vnstock_data,"__version__","available")
    except Exception as e:
        return False,str(e)

def ensure_installer_dependencies(timeout=90):
    """Ensure dependencies used by the official Vnstock CLI exist in THIS Streamlit Python runtime."""
    required=[
        ("requests","requests>=2.31,<3"),
        ("packaging","packaging>=23,<27"),
    ]
    installed=[]
    for module_name,pip_spec in required:
        try:
            importlib.import_module(module_name)
            continue
        except Exception:
            pass
        try:
            proc=subprocess.run(
                [sys.executable,"-m","pip","install","--disable-pip-version-check",pip_spec],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
            )
            importlib.invalidate_caches()
            importlib.import_module(module_name)
            installed.append(pip_spec)
        except Exception as e:
            return False,f"Không thể cài dependency {pip_spec} vào runtime {sys.executable}: {e}"
    return True,("Đã bổ sung: "+", ".join(installed)) if installed else "Dependencies đã sẵn sàng."

def install_sponsor(key,timeout=90):
    if not key or len(key.strip())<8:
        return False,"API Key chưa hợp lệ."
    configure_key(key)
    ok,detail=sponsor_available()
    if ok:return True,f"vnstock_data đã sẵn sàng ({detail})."

    dep_ok,dep_msg=ensure_installer_dependencies(timeout=90)
    if not dep_ok:
        return False,dep_msg

    try:
        urllib.request.urlretrieve(INSTALLER_URL,INSTALLER_PATH)
        INSTALLER_PATH.chmod(0o755)
    except Exception as e:
        return False,f"Không tải được CLI installer chính thức: {e}"
    cmd=[str(INSTALLER_PATH),"--","--non-interactive","--venv-path",str(SPONSOR_VENV),"--language","vi"]
    try:
        proc=subprocess.run(cmd,env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                            text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return False,"Installer vượt quá 90 giây và đã được dừng."
    except Exception as e:
        return False,f"Không chạy được installer: {e}"
    add_sponsor_site()
    ok,detail=sponsor_available()
    if ok:return True,f"Kết nối Bronze thành công ({detail})."
    tail=(proc.stdout or "")[-2200:]
    if key:tail=tail.replace(key.strip(),"***REDACTED***")
    return False,f"Installer exit={proc.returncode}; chưa import được vnstock_data.\n\n{tail}"

# ---------------- Generic helpers ----------------
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

def get_secret_key():
    try:return str(st.secrets.get("VNSTOCK_API_KEY","")).strip()
    except:return ""

if "session_key" not in st.session_state:st.session_state.session_key=""
if "connection_log" not in st.session_state:st.session_state.connection_log=""
if "bronze_circuit" not in st.session_state:st.session_state.bronze_circuit=False
if "free_circuit" not in st.session_state:st.session_state.free_circuit=False
if "connection_attempted" not in st.session_state:st.session_state.connection_attempted=False

secret_key=get_secret_key()
api_key=secret_key or st.session_state.session_key
configure_key(api_key)
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

def get_period(*dfs):
    for df in dfs:
        if df is None or len(df)==0:continue
        for c in ["period","report_period","report_time","year","quarter","time"]:
            if c in df.columns and len(df[c].dropna()):return str(df[c].dropna().iloc[0])
    return ""

def get_fundamental(mode):
    if mode=="BRONZE":
        from vnstock_data import Fundamental
    else:
        from vnstock import Fundamental
    return Fundamental()

def fetch_one(mode,symbol):
    fun=get_fundamental(mode)
    eq=fun.equity(symbol)
    try:bs=eq.balance_sheet(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try:bs=eq.balance_sheet(period="Q")
        except Exception:bs=eq.balance_sheet()
    try:ratio_df=eq.ratio(period="quarter",lang="en",format="long",com_type="bank")
    except Exception:
        try:ratio_df=eq.financial_ratio()
        except Exception:
            try:ratio_df=eq.ratio(period="Q")
            except Exception:ratio_df=pd.DataFrame()

    loans=find_metric(bs,["customer loans","loans to customers","cho vay khách hàng"])
    deposits=find_metric(bs,["customer deposits","deposits from customers","tiền gửi khách hàng"])
    assets=find_metric(bs,["total assets","tổng tài sản"])
    ib=find_metric(bs,["interbank borrowing","borrowings from other credit institutions","tiền gửi và vay các tổ chức tín dụng"])
    ldr=find_metric(ratio_df,["ldr","loan to deposit"])
    casa=find_metric(ratio_df,["casa","current account saving account"])
    nim=find_metric(ratio_df,["nim","net interest margin"])

    if ldr is None and loans is not None and deposits not in (None,0):ldr=loans/deposits
    ibdep=ib/assets if ib is not None and assets not in (None,0) else np.nan
    gap=(loans-deposits)/deposits if loans is not None and deposits not in (None,0) else np.nan

    return [symbol,get_period(bs,ratio_df),ldr,casa,ibdep,gap,nim,"ACTUAL",mode]

def parallel_fetch(mode,symbols,timeout,max_workers):
    executor=ThreadPoolExecutor(max_workers=max_workers)
    futures={executor.submit(fetch_one,mode,s):s for s in symbols}
    done,pending=wait(futures.keys(),timeout=timeout)
    rows=[];status=[]
    for f in done:
        s=futures[f]
        try:
            rows.append(f.result());status.append([s,"OK",""])
        except Exception as e:
            status.append([s,"ERROR",str(e)[:250]])
    for f in pending:
        f.cancel();status.append([futures[f],"TIMEOUT",f">{timeout}s"])
    executor.shutdown(wait=False,cancel_futures=True)
    return rows,status

def useful(rows):
    return [r for r in rows if sum(pd.notna(r[i]) for i in range(2,7))>=3]

@st.cache_data(ttl=6*3600,show_spinner=False)
def fetch_bronze_data():
    rows,status=parallel_fetch("BRONZE",BANKS[:3],12,3)
    good=useful(rows)
    if len(good)<2:
        return pd.DataFrame(),pd.DataFrame(status,columns=["Ticker","Status","Message"]),"CIRCUIT_OPEN"
    r2,s2=parallel_fetch("BRONZE",BANKS[3:],20,6)
    rows+=r2;status+=s2
    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode"]
    return pd.DataFrame(useful(rows),columns=cols),pd.DataFrame(status,columns=["Ticker","Status","Message"]),"OK"

@st.cache_data(ttl=6*3600,show_spinner=False)
def fetch_free_probe():
    rows,status=parallel_fetch("FREE",BANKS[:3],12,1)
    good=useful(rows)
    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM","Data Type","Source Mode"]
    state="OK_PROBE_ONLY" if len(good)>=1 else "CIRCUIT_OPEN"
    return pd.DataFrame(good,columns=cols),pd.DataFrame(status,columns=["Ticker","Status","Message"]),state

def as_ratio(x):
    x=pd.to_numeric(x,errors="coerce")
    return np.where(np.abs(x)>2,x/100,x)

def score(df,mult=1.35,pass_through=2.0):
    d=df.copy()
    for c in ["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]:d[c]=as_ratio(d[c])
    d["LiquidityBuffer"]=1-d["LDR"]
    fields=["LDR","CASA","InterbankDep","CreditDepositGap","NIM","LiquidityBuffer"]
    d["Coverage"]=d[fields].notna().mean(axis=1)
    raw=50+35*(d.LDR-.85)-25*(d.CASA-.20)+45*d.InterbankDep+30*d.CreditDepositGap-10*(d.NIM-.03)-20*(d.LiquidityBuffer-.15)
    d["BaseVulnerability"]=raw.clip(0,100)
    d.loc[d.Coverage<.5,"BaseVulnerability"]=np.nan
    d["StressVulnerability"]=(d.BaseVulnerability*mult).clip(0,100)
    d["FundingCostShock_ppt"]=pass_through*d.StressVulnerability/100
    d["StressedNIM"]=np.maximum(0,d.NIM-d.FundingCostShock_ppt/100)
    d["Watch"]=np.select([(d.StressVulnerability>=75)|(d.StressedNIM<.02),d.StressVulnerability>=60],["ĐỎ","VÀNG"],default="XANH")
    return d.sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

macro=load("macro_public_snapshot")
fallback=load("bank_fallback_assumptions")

# ---------------- Sidebar connection UX ----------------
with st.sidebar:
    st.subheader("KẾT NỐI VNSTOCK")

    if sponsor_ok and api_key:
        st.success("🟢 BRONZE CONNECTED")
        st.caption(f"vnstock_data: {sponsor_detail}")
    elif api_key:
        st.warning("🟠 API Key đã có, nhưng Bronze chưa kết nối")
    else:
        st.info("🔵 Chưa có API Key")

    if secret_key:
        st.success("API Key đã đọc từ Streamlit Secrets.")
    else:
        entered=st.text_input("Vnstock API Key",type="password",value=st.session_state.session_key)
        if entered != st.session_state.session_key:
            st.session_state.session_key=entered.strip()
            api_key=st.session_state.session_key
            configure_key(api_key)

    # IMPORTANT FIX: button is visible whenever there is a key and Sponsor is not connected.
    if api_key and not sponsor_ok:
        if st.button("🔌 Kết nối Vnstock Bronze",use_container_width=True):
            st.session_state.connection_attempted=True
            with st.status("Đang kết nối Vnstock Bronze...",expanded=True) as status_box:
                st.write("1/4 Kiểm tra API Key...")
                configure_key(api_key)
                st.write("2/4 Kiểm tra/cài dependencies của CLI (`requests`, `packaging`)...")
                dep_ok,dep_msg=ensure_installer_dependencies(90)
                st.write(dep_msg)
                if dep_ok:
                    st.write("3/4 Tải/chạy Vnstock CLI Installer...")
                    ok,msg=install_sponsor(api_key,90)
                else:
                    ok,msg=False,dep_msg
                st.session_state.connection_log=msg
                if ok:
                    st.write("4/4 Kiểm tra vnstock_data...")
                    status_box.update(label="Kết nối Bronze thành công",state="complete",expanded=False)
                    fetch_bronze_data.clear()
                    st.rerun()
                else:
                    status_box.update(label="Không kết nối được Bronze",state="error",expanded=True)

    if st.session_state.connection_log and not sponsor_ok:
        with st.expander("Chi tiết kết nối Bronze",expanded=st.session_state.connection_attempted):
            st.code(st.session_state.connection_log)

    st.divider()
    st.write("**Bảo vệ API**")
    st.caption("Bronze: probe 3 mã → đủ điều kiện mới tải 20 mã.")
    st.caption("Free/Guest: chỉ probe 3 mã, không full-load.")
    if st.button("Làm mới cache/API",use_container_width=True):
        fetch_bronze_data.clear()
        fetch_free_probe.clear()
        st.session_state.bronze_circuit=False
        st.session_state.free_circuit=False
        st.rerun()

# ---------------- Data backend ----------------
live=pd.DataFrame()
status_frames=[]
bronze_state="NOT_CONNECTED"
free_state="NOT_TRIED"

if sponsor_ok and api_key and not st.session_state.bronze_circuit:
    with st.spinner("Đang tải dữ liệu Bronze..."):
        live,bs,bronze_state=fetch_bronze_data()
    status_frames.append(bs)
    if bronze_state=="CIRCUIT_OPEN":st.session_state.bronze_circuit=True

if live.empty and not st.session_state.free_circuit:
    with st.spinner("Đang probe Vnstock Free/Guest tối đa 3 mã..."):
        free,fs,free_state=fetch_free_probe()
    status_frames.append(fs)
    if free_state=="CIRCUIT_OPEN":
        st.session_state.free_circuit=True
    else:
        live=free

status_df=pd.concat(status_frames,ignore_index=True) if status_frames else pd.DataFrame(columns=["Ticker","Status","Message"])
missing=fallback[~fallback.Ticker.isin(live.Ticker)] if len(live) else fallback.copy()
bank=pd.concat([live,missing],ignore_index=True) if len(live) else missing.copy()

bronze_count=int((bank["Source Mode"]=="BRONZE").sum())
free_count=int((bank["Source Mode"]=="FREE").sum())
fallback_count=int((bank["Data Type"]=="ASSUMPTION").sum())
bank_score=score(bank)

def macro_value(ind):
    q=macro[macro.Indicator==ind]
    return float(q.Value.iloc[0]) if len(q) else np.nan

credit=macro_value("Tăng trưởng tín dụng YTD")
deposit=macro_value("Tăng trưởng huy động YTD")
cpi=macro_value("CPI YoY")
trade=macro_value("Cán cân thương mại")
funding_gap=credit-deposit
pressure=float(np.clip(funding_gap/3+max(0,cpi-4)/2+max(0,-trade)/20,0,3))

tabs=st.tabs(["Trung tâm điều hành","Xếp hạng ngân hàng","Mô phỏng Stress","Chi tiết ngân hàng","Thanh khoản hệ thống","Chất lượng dữ liệu"])

with tabs[0]:
    a,b,c,d=st.columns(4)
    a.metric("Bronze ACTUAL",bronze_count)
    b.metric("Free ACTUAL",free_count)
    c.metric("Fallback",fallback_count)
    d.metric("System Pressure",f"{pressure:.2f}/3")
    if bronze_count:
        st.success(f"Đang sử dụng Bronze ACTUAL cho {bronze_count} ngân hàng.")
    elif api_key and not sponsor_ok:
        st.warning("API Key đã có nhưng Bronze chưa kết nối. Bấm “Kết nối Vnstock Bronze” ở sidebar.")
    elif free_count:
        st.info(f"Free/Guest chỉ probe {free_count} ngân hàng để bảo vệ rate limit.")
    else:
        st.warning("Live API không khả dụng; dashboard dùng fallback ASSUMPTION có nhãn.")
    top=bank_score.head(10)
    st.subheader("Top 10 nhạy cảm với stress thanh khoản")
    st.bar_chart(top.set_index("Ticker")[["StressVulnerability"]],height=320)
    st.dataframe(safe_df(top[["Ticker","Source Mode","Data Type","LDR","CASA","NIM","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]]),hide_index=True)

with tabs[1]:
    st.dataframe(safe_df(bank_score),hide_index=True)

with tabs[2]:
    x,y,z=st.columns(3)
    mult=x.slider("Hệ số stress",1.0,2.2,1.35,.05)
    passt=y.slider("Funding pass-through (ppt)",.5,4.0,2.0,.25)
    lpi=z.slider("Liquidity pressure",0.0,3.0,pressure,.1)
    stressed=score(bank,mult*(1+.12*lpi),passt)
    st.bar_chart(stressed.set_index("Ticker")[["BaseVulnerability","StressVulnerability"]],height=340)
    st.dataframe(safe_df(stressed[["Ticker","Source Mode","Data Type","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch"]]),hide_index=True)

with tabs[3]:
    tick=st.selectbox("Ngân hàng",bank_score.Ticker.tolist())
    r=bank_score[bank_score.Ticker==tick].iloc[0]
    q1,q2,q3,q4=st.columns(4)
    q1.metric("Nguồn",str(r["Source Mode"]))
    q2.metric("Vulnerability",f"{r.StressVulnerability:.1f}")
    q3.metric("Funding cost",f"+{r.FundingCostShock_ppt:.2f} ppt")
    q4.metric("Stressed NIM",f"{r.StressedNIM:.2%}")
    detail=pd.DataFrame({
        "Chỉ tiêu":["LDR","CASA","Phụ thuộc liên ngân hàng","Khoảng cách tín dụng-tiền gửi","NIM","Coverage","Watch"],
        "Giá trị":[r.LDR,r.CASA,r.InterbankDep,r.CreditDepositGap,r.NIM,r.Coverage,r.Watch]
    })
    st.dataframe(safe_df(detail),hide_index=True)

with tabs[4]:
    st.dataframe(safe_df(macro),hide_index=True)
    c1,c2=st.columns(2)
    c1.metric("Funding gap",f"{funding_gap:.2f} ppt")
    c2.metric("System Pressure Proxy",f"{pressure:.2f}/3")

with tabs[5]:
    st.subheader("Trạng thái backend")
    diag=pd.DataFrame([
        ["API Key","Có" if api_key else "Chưa có"],
        ["vnstock_data","Sẵn sàng" if sponsor_ok else "Chưa sẵn sàng"],
        ["Bronze state",bronze_state],
        ["Free state",free_state],
        ["Bronze circuit","Open" if st.session_state.bronze_circuit else "Closed"],
        ["Free circuit","Open" if st.session_state.free_circuit else "Closed"],
    ],columns=["Thành phần","Trạng thái"])
    st.dataframe(safe_df(diag),hide_index=True)
    if len(status_df):
        st.subheader("Chi tiết API")
        st.dataframe(safe_df(status_df),hide_index=True)
    st.caption("Khi Bronze chưa kết nối, app không tự chạy installer. Chỉ nút “Kết nối Vnstock Bronze” mới kích hoạt cài đặt.")

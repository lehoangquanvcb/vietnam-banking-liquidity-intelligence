
from pathlib import Path
from datetime import datetime
import sys, os, json, inspect, traceback, zipfile, platform, re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "diagnostics_r5"
OUT.mkdir(exist_ok=True)

REPORT = []
def log(msg=""):
    s = str(msg)
    print(s)
    REPORT.append(s)

def safe_sig(obj):
    try:
        return str(inspect.signature(obj))
    except Exception as e:
        return f"<signature unavailable: {e}>"

def module_version(name):
    try:
        import importlib.metadata as md
        return md.version(name)
    except Exception:
        try:
            mod = __import__(name)
            return getattr(mod, "__version__", "unknown")
        except Exception as e:
            return f"unavailable: {e}"

def save_df(df, name):
    if df is None:
        return
    try:
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
    except Exception as e:
        log(f"[WARN] Cannot save {name}.csv: {e}")

def summarize_df(df, label):
    log("")
    log("="*88)
    log(f"DATAFRAME: {label}")
    log("="*88)
    if df is None:
        log("None")
        return
    log(f"shape={getattr(df,'shape',None)}")
    log("columns:")
    for c in list(df.columns):
        log(f"  - {repr(c)} | dtype={df[c].dtype}")
    log("")
    log("head(5):")
    try:
        log(df.head(5).to_string())
    except Exception as e:
        log(f"<head failed: {e}>")
    log("")
    log("tail(5):")
    try:
        log(df.tail(5).to_string())
    except Exception as e:
        log(f"<tail failed: {e}>")

def normalize(x):
    return re.sub(r"\s+"," ",str(x).strip().lower())

def extract_candidates(df, source_label):
    if df is None or len(df)==0:
        return pd.DataFrame()
    x=df.copy()
    x.columns=[" | ".join(map(str,c)) if isinstance(c,tuple) else str(c) for c in x.columns]
    rows=[]
    terms=["ldr","loan to deposit","casa","nim","net interest margin","deposit","customer deposit",
           "loan","customer loan","interbank","credit institution","tổ chức tín dụng","tiền gửi","cho vay"]
    for idx,row in x.iterrows():
        text=" | ".join(str(v) for v in row.values[:min(len(row),8)])
        nt=normalize(text)
        if any(t in nt for t in terms):
            rec={"source":source_label,"row_index":idx,"row_text":text[:1000]}
            for c in x.columns[:min(len(x.columns),12)]:
                rec[str(c)]=row[c]
            rows.append(rec)
    for c in x.columns:
        nc=normalize(c)
        if any(t in nc for t in terms):
            rec={"source":source_label,"row_index":"<column>","row_text":f"COLUMN MATCH: {c}"}
            rows.append(rec)
    return pd.DataFrame(rows)

log("VNSTOCK DIAGNOSTIC R5")
log(f"Timestamp: {datetime.now().astimezone().isoformat()}")
log(f"Python executable: {sys.executable}")
log(f"Python version: {sys.version}")
log(f"Platform: {platform.platform()}")
log(f"Working directory: {os.getcwd()}")
log("")
for pkg in ["vnstock_data","vnstock","pandas","numpy","requests","unidecode"]:
    log(f"{pkg} version: {module_version(pkg)}")

try:
    import vnstock_data
    from vnstock_data import Fundamental, Macro
    log("")
    log("vnstock_data import: OK")
except Exception:
    log("")
    log("vnstock_data import: FAILED")
    log(traceback.format_exc())
    (OUT/"VNSTOCK_DIAGNOSTIC_R5_REPORT.txt").write_text("\n".join(REPORT),encoding="utf-8")
    raise SystemExit(2)

# ---- Class / API introspection ----
log("")
log("="*88)
log("API INTROSPECTION")
log("="*88)
for cls_name, cls in [("Fundamental",Fundamental),("Macro",Macro)]:
    log(f"{cls_name} constructor signature: {safe_sig(cls)}")
    try:
        inst=cls()
        public=[x for x in dir(inst) if not x.startswith("_")]
        log(f"{cls_name} public attrs ({len(public)}): {public}")
    except Exception as e:
        log(f"{cls_name} instantiation failed: {repr(e)}")

# ---- Fundamental banking schema probe ----
fun=Fundamental()
try:
    eq=fun.equity("TCB")
except Exception:
    try:
        eq=fun.equity(symbol="TCB")
    except Exception:
        eq=None
        log("Could not construct TCB equity object:")
        log(traceback.format_exc())

fundamental_outputs={}
if eq is not None:
    log("")
    log("="*88)
    log("TCB EQUITY OBJECT METHODS")
    log("="*88)
    for method_name in ["balance_sheet","ratio","financial_health","income_statement","cash_flow"]:
        if hasattr(eq,method_name):
            method=getattr(eq,method_name)
            log(f"{method_name} signature: {safe_sig(method)}")
        else:
            log(f"{method_name}: NOT PRESENT")

    calls = [
        ("TCB_balance_sheet_doc", lambda: eq.balance_sheet(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)),
        ("TCB_balance_sheet_min", lambda: eq.balance_sheet(period="quarter")),
        ("TCB_ratio_doc", lambda: eq.ratio(period="quarter",lang="en",format="long",com_type="Bank",drop_empty=False)),
        ("TCB_ratio_min", lambda: eq.ratio(period="quarter")),
        ("TCB_financial_health_bank", lambda: eq.financial_health(scorecard="bank",lang="en",limit=4)),
        ("TCB_financial_health_auto", lambda: eq.financial_health(scorecard="auto",lang="en",limit=4)),
    ]

    for label,fn in calls:
        log("")
        log("-"*88)
        log(f"CALL: {label}")
        log("-"*88)
        try:
            df=fn()
            fundamental_outputs[label]=df
            log("STATUS: OK")
            summarize_df(df,label)
            save_df(df,label)
        except Exception as e:
            log(f"STATUS: ERROR: {repr(e)}")
            log(traceback.format_exc())

candidate_frames=[]
for label,df in fundamental_outputs.items():
    c=extract_candidates(df,label)
    if len(c):
        candidate_frames.append(c)
if candidate_frames:
    candidates=pd.concat(candidate_frames,ignore_index=True,sort=False)
    save_df(candidates,"BANK_METRIC_CANDIDATES")
    log("")
    log(f"Bank metric candidate rows found: {len(candidates)}")
else:
    log("")
    log("Bank metric candidate rows found: 0")

# ---- Macro / interbank introspection ----
log("")
log("="*88)
log("MACRO / INTERBANK PROBE")
log("="*88)
try:
    macro=Macro()
    log(f"Macro public attrs: {[x for x in dir(macro) if not x.startswith('_')]}")
    currency=macro.currency()
    log(f"Macro.currency() type: {type(currency)}")
    log(f"Macro.currency() public attrs: {[x for x in dir(currency) if not x.startswith('_')]}")
except Exception as e:
    currency=None
    log(f"Macro.currency() failed: {repr(e)}")
    log(traceback.format_exc())

if currency is not None:
    for mn in ["interbank_rate","interest_rate","omo","exchange_rate","policy_rate"]:
        if hasattr(currency,mn):
            log(f"currency.{mn} signature: {safe_sig(getattr(currency,mn))}")
        else:
            log(f"currency.{mn}: NOT PRESENT")

    ib_calls=[]
    if hasattr(currency,"interbank_rate"):
        fn=currency.interbank_rate
        ib_calls=[
            ("interbank_no_args", lambda: fn()),
            ("interbank_length_30", lambda: fn(length=30)),
            ("interbank_period_day_length_30", lambda: fn(period="day",length=30)),
            ("interbank_start_end_day", lambda: fn(start="2026-07-01",end="2026-08-15",period="day")),
            ("interbank_start_day", lambda: fn(start="2026-07-01",period="day")),
            ("interbank_start_month", lambda: fn(start="2025-01-01",period="month")),
        ]
    else:
        log("No currency.interbank_rate method exists in installed runtime.")

    for label,fn in ib_calls:
        log("")
        log("-"*88)
        log(f"CALL: {label}")
        log("-"*88)
        try:
            df=fn()
            log("STATUS: OK")
            summarize_df(df,label)
            save_df(df,label)
            # Stop after first successful non-empty response to minimize requests.
            if df is not None and len(df):
                log("Interbank probe found a working signature; remaining calls skipped.")
                break
        except Exception as e:
            log(f"STATUS: ERROR: {repr(e)}")
            log(traceback.format_exc())

    # One proxy call only for schema comparison; clearly not interbank.
    if hasattr(currency,"interest_rate"):
        try:
            proxy=currency.interest_rate(length=30)
            log("")
            log("Funding-rate proxy call: OK (NOT INTERBANK)")
            summarize_df(proxy,"funding_rate_proxy_interest_rate")
            save_df(proxy,"funding_rate_proxy_interest_rate")
        except Exception as e:
            log("")
            log(f"Funding-rate proxy call failed: {repr(e)}")

# ---- Write report and zip ----
report_path=OUT/"VNSTOCK_DIAGNOSTIC_R5_REPORT.txt"
report_path.write_text("\n".join(REPORT),encoding="utf-8")

manifest={
    "created_at":datetime.now().astimezone().isoformat(),
    "python_executable":sys.executable,
    "python_version":sys.version,
    "vnstock_data_version":module_version("vnstock_data"),
    "note":"No API key or Streamlit secrets are intentionally written by this diagnostic."
}
(OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")

zip_path=ROOT/"VNSTOCK_DIAGNOSTIC_R5_RESULT.zip"
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob("*"):
        if p.is_file():
            z.write(p,p.relative_to(OUT))

log("")
log(f"Diagnostic ZIP created: {zip_path}")
log("Please upload VNSTOCK_DIAGNOSTIC_R5_RESULT.zip back to ChatGPT.")
print("")
print("="*88)
print("DONE")
print(f"Send this file back: {zip_path}")
print("="*88)

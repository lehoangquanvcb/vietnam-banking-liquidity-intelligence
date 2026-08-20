from pathlib import Path
from datetime import datetime, timedelta
import json
import re
import unicodedata
import time
import sys
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
BANKS = json.loads((ROOT / "config" / "banks.json").read_text(encoding="utf-8"))

try:
    from vnstock_data import Fundamental, Macro
except Exception as exc:
    print(f"ERROR: vnstock_data unavailable in this Python: {exc!r}")
    sys.exit(2)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def norm(value):
    s = str(value if value is not None else "")
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^A-Za-z0-9]+", " ", s).lower().strip()


def flatten(df):
    if df is None:
        return pd.DataFrame()
    x = df.copy()
    try:
        if isinstance(x.index, pd.MultiIndex) or x.index.name is not None:
            x = x.reset_index()
    except Exception:
        x.index = pd.RangeIndex(len(x))
    if isinstance(x.columns, pd.MultiIndex):
        cols = []
        seen = {}
        for c in x.columns:
            parts = [str(v).strip() for v in c if str(v).strip() not in {"", "None", "nan"}]
            name = " | ".join(parts) if parts else "column"
            n = seen.get(name, 0)
            seen[name] = n + 1
            cols.append(name if n == 0 else f"{name}__{n}")
        x.columns = cols
    else:
        x.columns = [str(c) for c in x.columns]
    return x


def find_col(df, aliases):
    wanted = [norm(a) for a in aliases]
    for c in df.columns:
        nc = norm(c)
        if any(nc == w or nc.endswith(" " + w) for w in wanted):
            return c
    for c in df.columns:
        nc = norm(c)
        if any(w in nc for w in wanted):
            return c
    return None


def metric(df, ids=(), names=()):
    x = flatten(df)
    if x.empty:
        return np.nan
    idc = find_col(x, ["id", "code", "metric_id"])
    namec = find_col(x, ["name", "metric", "indicator", "item", "label"])
    valc = find_col(x, ["value", "metric_value", "ratio_value"])
    periodc = find_col(x, ["period", "report_period", "quarter", "year"])

    candidates = []
    if idc:
        sid = x[idc].astype(str).str.upper()
        for item in ids:
            q = str(item).upper()
            candidates.append(sid.eq(q) | sid.str.contains(q, regex=False, na=False))
    if namec:
        sn = x[namec].astype(str).map(norm)
        for item in names:
            q = norm(item)
            candidates.append(sn.str.contains(q, regex=False, na=False))

    for mask in candidates:
        if not bool(mask.any()):
            continue
        z = x.loc[mask].copy()
        if periodc:
            z["_period"] = z[periodc].astype(str)
            z = z.sort_values("_period")
        if valc:
            vals = pd.to_numeric(z[valc], errors="coerce").dropna()
            if len(vals):
                return float(vals.iloc[-1])
        for _, row in z.iterrows():
            nums = []
            for c in z.columns:
                if c in {idc, namec, periodc, "_period"}:
                    continue
                v = pd.to_numeric(pd.Series([row[c]]), errors="coerce").dropna()
                if len(v):
                    nums.append(float(v.iloc[0]))
            if nums:
                return nums[-1]
    return np.nan


def call_safe(label, fn):
    try:
        return fn(), f"{label}:OK"
    except Exception as exc:
        return pd.DataFrame(), f"{label}:ERROR:{str(exc)[:180]}"


def fetch_bank(ticker):
    eq = Fundamental().equity(ticker)

    health, s_health = call_safe(
        "health", lambda: eq.financial_health(scorecard="bank", lang="en", limit=4)
    )
    ratio, s_ratio = call_safe(
        "ratio", lambda: eq.ratio(period="quarter", lang="en", format="long", com_type="Bank")
    )
    if ratio.empty:
        ratio, s_ratio2 = call_safe("ratio-min", lambda: eq.ratio(period="quarter"))
        s_ratio += " | " + s_ratio2
    bs, s_bs = call_safe(
        "balance-sheet", lambda: eq.balance_sheet(period="quarter", lang="en", format="long", com_type="Bank")
    )
    if bs.empty:
        bs, s_bs2 = call_safe("balance-sheet-min", lambda: eq.balance_sheet(period="quarter"))
        s_bs += " | " + s_bs2

    ldr = metric(health, ["RT_BANK_LDR"], ["loan to deposit ratio", "ldr"])
    if pd.isna(ldr):
        ldr = metric(ratio, ["RT_BANK_LDR"], ["loan to deposit ratio", "ldr"])
    # CASA: prefer a directly reported ratio. Vnstock bank scorecards/ratios do not
    # consistently expose CASA for every bank, so derive it from the balance sheet
    # only when the direct metric is absent. In Vietnamese banking practice the
    # comparable public-data proxy is non-term/demand customer deposits divided by
    # total customer deposits.
    casa = metric(health, ["RT_BANK_CASA"], ["casa", "current account saving", "current account and savings"])
    casa_source = "DIRECT_FINANCIAL_HEALTH" if pd.notna(casa) else ""
    if pd.isna(casa):
        casa = metric(ratio, ["RT_BANK_CASA"], ["casa", "current account saving", "current account and savings"])
        if pd.notna(casa):
            casa_source = "DIRECT_RATIO"
    nim = metric(health, ["RT_BANK_NIM"], ["net interest margin", "nim"])
    if pd.isna(nim):
        nim = metric(ratio, ["RT_BANK_NIM"], ["net interest margin", "nim"])

    loans = metric(
        bs,
        ["BS_CUSTOMER_LOANS", "BS_LOANS_TO_CUSTOMERS", "BS_LOANS_AND_ADVANCES_TO_CUSTOMERS"],
        ["loans to customers", "customer loans", "loans and advances to customers"],
    )
    deposits = metric(bs, ["BS_CUSTOMER_DEPOSITS"], ["customer deposits", "deposits from customers"])
    # Non-term/demand deposits are the defensible public-BS proxy for CASA when a
    # reported CASA ratio is unavailable. Keep the derivation explicit for audit.
    demand_deposits = metric(
        bs,
        [
            "BS_DEMAND_DEPOSITS",
            "BS_CUSTOMER_DEMAND_DEPOSITS",
            "BS_NON_TERM_DEPOSITS",
            "BS_DEPOSITS_WITHOUT_TERM",
            "BS_CURRENT_ACCOUNTS",
        ],
        [
            "demand deposits",
            "customer demand deposits",
            "non term deposits",
            "non-term deposits",
            "deposits without term",
            "current accounts",
            "current account deposits",
            "demand and current deposits",
        ],
    )
    assets = metric(bs, ["BS_TOTAL_ASSETS"], ["total assets"])
    ib_liab = metric(
        bs,
        [
            "BS_PLACEMENTS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
            "BS_DEPOSITS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
            "BS_BORROWINGS_FROM_CREDIT_INSTITUTIONS",
        ],
        [
            "placements and borrowings from credit institutions",
            "deposits and borrowings from credit institutions",
            "amounts due to credit institutions",
        ],
    )

    if pd.isna(ldr) and pd.notna(loans) and pd.notna(deposits) and deposits != 0:
        ldr = float(loans / deposits)
    if pd.isna(casa) and pd.notna(demand_deposits) and pd.notna(deposits) and deposits != 0:
        casa = float(demand_deposits / deposits)
        casa_source = "DERIVED_BALANCE_SHEET"
    # Normalize directly reported percentage-style values to ratios where needed.
    if pd.notna(casa) and casa > 1.5 and casa <= 100:
        casa = casa / 100.0
    if pd.notna(casa) and not (0 <= casa <= 1):
        casa = np.nan
        casa_source = "INVALID_RANGE"
    interbank_dep = float(ib_liab / assets) if pd.notna(ib_liab) and pd.notna(assets) and assets != 0 else np.nan
    gap = float((loans - deposits) / deposits) if pd.notna(loans) and pd.notna(deposits) and deposits != 0 else np.nan

    vals = [ldr, casa, interbank_dep, gap, nim]
    count = int(pd.Series(vals, dtype="float64").notna().sum())
    return {
        "Ticker": ticker,
        "LDR": ldr,
        "CASA": casa,
        "CASASource": casa_source or "NOT_AVAILABLE",
        "DemandDeposits": demand_deposits,
        "CustomerDeposits": deposits,
        "InterbankDep": interbank_dep,
        "CreditDepositGap": gap,
        "NIM": nim,
        "ActualMetricCount": count,
        "MetricCoverage": count / 5,
        "ParseStatus": "OK" if count >= 3 else "PARTIAL" if count else "NO_METRICS",
        "ParserLog": f"{s_health} || {s_ratio} || {s_bs}",
        "RetrievedAt": now(),
    }



def load_casa_actual():
    """Load CASA using priority: user actual file -> packaged public seed."""
    candidates = [
        DATA / "casa_actual.csv",
        ROOT / "config" / "casa_actual_public_seed.csv",
    ]
    x = pd.DataFrame()
    for path in candidates:
        if not path.exists():
            continue
        try:
            candidate = pd.read_csv(path)
            if len(candidate):
                x = candidate.copy()
                break
        except Exception:
            continue
    if x.empty:
        return pd.DataFrame()
    if x.empty or "Ticker" not in x.columns or "CASA" not in x.columns:
        return pd.DataFrame()
    x["Ticker"] = x["Ticker"].astype(str).str.upper().str.strip()
    x["CASA"] = pd.to_numeric(x["CASA"], errors="coerce")
    # Accept 0-1 ratios or 0-100 percentages.
    x.loc[(x["CASA"] > 1.5) & (x["CASA"] <= 100), "CASA"] = x.loc[(x["CASA"] > 1.5) & (x["CASA"] <= 100), "CASA"] / 100.0
    x = x[(x["CASA"] >= 0) & (x["CASA"] <= 1)].copy()
    if "AsOfDate" in x.columns:
        x["_date"] = pd.to_datetime(x["AsOfDate"], errors="coerce")
    elif "Period" in x.columns:
        x["_date"] = pd.to_datetime(x["Period"].astype(str).str.replace("Q1","-03-31").str.replace("Q2","-06-30").str.replace("Q3","-09-30").str.replace("Q4","-12-31"), errors="coerce")
    else:
        x["_date"] = pd.NaT
    x = x.sort_values(["Ticker","_date"], na_position="first").drop_duplicates("Ticker", keep="last")
    return x.set_index("Ticker")

def save_macro(df, filename):
    if df is None or len(df) == 0:
        return False
    flatten(df).to_csv(DATA / filename, index=False, encoding="utf-8-sig")
    return True


def extract_interbank(raw):
    x = flatten(raw)
    if x.empty:
        return pd.DataFrame()

    # Case 1: wide columns explicitly contain overnight / Qua đêm.
    date_col = None
    for alias in ["time", "date", "report_time", "datetime"]:
        c = find_col(x, [alias])
        if c and pd.to_datetime(x[c], errors="coerce").notna().sum() > 0:
            date_col = c
            break

    wide_candidates = []
    for c in x.columns:
        nc = norm(c)
        if "qua dem" in nc or "overnight" in nc:
            wide_candidates.append(c)
    if wide_candidates and date_col:
        for c in wide_candidates:
            vals = pd.to_numeric(x[c], errors="coerce")
            if vals.notna().sum() >= 5:
                out = pd.DataFrame({"date": pd.to_datetime(x[date_col], errors="coerce"), "overnight_rate": vals})
                out = out.dropna().sort_values("date").drop_duplicates("date", keep="last")
                if len(out):
                    return out

    # Case 2: long rows contain interbank + overnight labels.
    text_cols = [c for c in x.columns if x[c].dtype == "object" or "string" in str(x[c].dtype).lower()]
    text = x[text_cols].fillna("").astype(str).agg(" | ".join, axis=1).map(norm) if text_cols else pd.Series("", index=x.index)
    interbank = text.str.contains("lien ngan hang", regex=False, na=False) | text.str.contains("interbank", regex=False, na=False)
    overnight = text.str.contains("qua dem", regex=False, na=False) | text.str.contains("overnight", regex=False, na=False)
    z = x.loc[interbank & overnight].copy()
    if z.empty and bool(interbank.any()) and bool(overnight.any()):
        z = x.loc[overnight].copy()
    if z.empty:
        return pd.DataFrame()

    dc = None
    for alias in ["time", "date", "report_time", "datetime"]:
        c = find_col(z, [alias])
        if c and pd.to_datetime(z[c], errors="coerce").notna().sum() > 0:
            dc = c
            break
    vc = find_col(z, ["rate_value", "overnight_rate", "value", "rate"])
    if vc is None:
        best, best_n = None, 0
        for c in z.columns:
            n = pd.to_numeric(z[c], errors="coerce").notna().sum()
            if n > best_n:
                best, best_n = c, n
        vc = best
    if dc is None or vc is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(z[dc], errors="coerce"),
        "overnight_rate": pd.to_numeric(z[vc], errors="coerce"),
    })
    return out.dropna().sort_values("date").drop_duplicates("date", keep="last")


def fetch_interbank(macro):
    attempts = []
    currency = macro.currency()

    # 1) Dedicated interbank API in smaller yearly chunks to extend history
    # without sending one oversized request.
    today = pd.Timestamp.now().normalize()
    chunks = []
    chunk_start = pd.Timestamp("2021-01-01")
    while chunk_start <= today:
        chunk_end = min(chunk_start + pd.DateOffset(years=1) - pd.Timedelta(days=1), today)
        try:
            raw = currency.interbank_rate(
                start=chunk_start.strftime("%Y-%m-%d"),
                end=chunk_end.strftime("%Y-%m-%d"),
                period="day"
            )
            parsed = extract_interbank(raw)
            attempts.append(f"interbank_rate:{chunk_start.date()}->{chunk_end.date()}:raw={len(flatten(raw))},on={len(parsed)}")
            if len(parsed):
                chunks.append(parsed)
        except Exception as exc:
            attempts.append(f"interbank_rate:{chunk_start.date()}->{chunk_end.date()}:ERROR:{str(exc)[:120]}")
        chunk_start = chunk_end + pd.Timedelta(days=1)
        time.sleep(0.10)

    if chunks:
        hist = pd.concat(chunks, ignore_index=True)
        hist = hist.dropna().sort_values("date").drop_duplicates("date", keep="last")
        if len(hist):
            return hist, "INTERBANK_RATE_CHUNKED", " | ".join(attempts)

    # 2) Runtime-compatible interest_rate calls. These can be sparse but are real.
    for label, fn in [
        ("interest_rate_long", lambda: currency.interest_rate(period="day", length=365, format="long")),
        ("interest_rate_pivot", lambda: currency.interest_rate(period="day", length=365)),
        ("interest_rate_180", lambda: currency.interest_rate(period="day", length=180, format="long")),
    ]:
        try:
            raw = fn()
            parsed = extract_interbank(raw)
            attempts.append(f"{label}:rows={len(flatten(raw))},on={len(parsed)}")
            if len(parsed):
                return parsed, label, " | ".join(attempts)
        except Exception as exc:
            attempts.append(f"{label}:ERROR:{str(exc)[:160]}")
    return pd.DataFrame(), "NONE", " | ".join(attempts)


status = []
rows = []
for ticker in BANKS:
    try:
        row = fetch_bank(ticker)
        rows.append(row)
        status.append([f"bank:{ticker}", "OK", row["ParseStatus"], now()])
    except Exception as exc:
        rows.append({"Ticker": ticker, "ActualMetricCount": 0, "MetricCoverage": 0, "ParseStatus": "ERROR", "ParserLog": str(exc)[:300], "RetrievedAt": now()})
        status.append([f"bank:{ticker}", "ERROR", str(exc)[:300], now()])
    time.sleep(0.15)

bank_df = pd.DataFrame(rows)
for c in ["LDR", "CASA", "InterbankDep", "CreditDepositGap", "NIM"]:
    if c not in bank_df.columns:
        bank_df[c] = np.nan

# Merge ACTUAL public CASA only where Vnstock direct/derived CASA is missing.
casa_actual = load_casa_actual()
for c in ["CASADataType","CASAPeriod","CASASourceName","CASASourceURL"]:
    if c not in bank_df.columns:
        bank_df[c] = None

if len(casa_actual):
    for i in bank_df.index:
        ticker = str(bank_df.at[i, "Ticker"]).upper()
        if ticker in casa_actual.index and pd.isna(pd.to_numeric(pd.Series([bank_df.at[i, "CASA"]]), errors="coerce").iloc[0]):
            r = casa_actual.loc[ticker]
            bank_df.at[i, "CASA"] = float(r["CASA"])
            bank_df.at[i, "CASASource"] = "ACTUAL_PUBLIC_SOURCE"
            bank_df.at[i, "CASADataType"] = str(r.get("DataType", "ACTUAL_PUBLIC_SOURCE"))
            bank_df.at[i, "CASAPeriod"] = r.get("Period", "")
            bank_df.at[i, "CASASourceName"] = r.get("SourceName", "")
            bank_df.at[i, "CASASourceURL"] = r.get("SourceURL", "")

# Recalculate coverage after all CASA sources have been applied.
metric_fields = ["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]
for i in bank_df.index:
    vals = [pd.to_numeric(pd.Series([bank_df.at[i,c]]), errors="coerce").iloc[0] for c in metric_fields]
    count = int(pd.Series(vals, dtype="float64").notna().sum())
    bank_df.at[i, "ActualMetricCount"] = count
    bank_df.at[i, "MetricCoverage"] = count / 5
    bank_df.at[i, "ParseStatus"] = "OK" if count >= 3 else "PARTIAL" if count else "NO_METRICS"

bank_df.to_csv(DATA / "bank_metrics.csv", index=False, encoding="utf-8-sig")

macro = Macro()
for name, fn, file in [
    ("omo", lambda: macro.currency().omo(start="2018-01-01"), "omo.csv"),
    ("fx", lambda: macro.currency().exchange_rate(start="2018-01-01", period="day"), "fx.csv"),
    ("policy_rate", lambda: macro.currency().policy_rate(start="2018-01-01"), "policy_rate.csv"),
]:
    try:
        ok = save_macro(fn(), file)
        status.append([name, "OK" if ok else "EMPTY", "", now()])
    except Exception as exc:
        status.append([name, "ERROR", str(exc)[:300], now()])

def normalize_interbank_frame(df, source_mode, source_detail, priority):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    x = flatten(df)
    dc = find_col(x, ["date","time","report_time","datetime"])
    vc = find_col(x, ["overnight_rate","overnight","rate_value","value","rate"])
    if dc is None or vc is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(x[dc], errors="coerce"),
        "overnight_rate": pd.to_numeric(x[vc], errors="coerce"),
    })
    out = out.dropna(subset=["date","overnight_rate"])
    # Remove clearly impossible values but keep genuine spikes.
    out = out[(out["overnight_rate"] >= 0) & (out["overnight_rate"] <= 50)].copy()
    if out.empty:
        return out
    out["SourceMode"] = source_mode
    out["SourceDetail"] = source_detail
    out["RetrievedAt"] = now()
    out["_priority"] = priority
    return out


def merge_interbank_history(new_actual, new_source, fetch_log):
    """Append-only ACTUAL history with date de-duplication and source lineage."""
    pieces = []
    history_path = DATA / "interbank_history.csv"
    legacy_path = DATA / "interbank.csv"
    manual_path = DATA / "interbank_manual.csv"

    # Existing accumulated history is never discarded merely because a refresh fails.
    for path, label in [(history_path,"PERSISTED_HISTORY"),(legacy_path,"LEGACY_HISTORY")]:
        if path.exists():
            try:
                old = pd.read_csv(path)
                z = normalize_interbank_frame(old, "HISTORY", label, 1)
                if len(z): pieces.append(z)
            except Exception:
                pass

    # Fresh Vnstock ACTUAL supersedes stale history for the same date.
    znew = normalize_interbank_frame(new_actual, "BRONZE", new_source, 2)
    if len(znew): pieces.append(znew)

    # User-supplied/public manual ACTUAL has highest de-dup priority because it is source-cited.
    if manual_path.exists():
        try:
            man = pd.read_csv(manual_path)
            zman = normalize_interbank_frame(man, "MANUAL_ACTUAL", "MANUAL_PUBLIC_SOURCE", 3)
            if len(zman): pieces.append(zman)
        except Exception:
            pass

    if not pieces:
        return pd.DataFrame(), "NO_ACTUAL_HISTORY"

    hist = pd.concat(pieces, ignore_index=True, sort=False)
    hist["date"] = pd.to_datetime(hist["date"], errors="coerce").dt.normalize()
    hist["overnight_rate"] = pd.to_numeric(hist["overnight_rate"], errors="coerce")
    hist = hist.dropna(subset=["date","overnight_rate"])
    hist = hist.sort_values(["date","_priority","RetrievedAt"], na_position="first")
    hist = hist.drop_duplicates("date", keep="last").sort_values("date")
    hist["ObservationNo"] = range(1, len(hist)+1)
    hist = hist.drop(columns=["_priority"], errors="ignore")
    hist.to_csv(history_path, index=False, encoding="utf-8-sig")
    # interbank.csv remains the canonical file consumed by models/app.
    hist.to_csv(legacy_path, index=False, encoding="utf-8-sig")
    return hist, "ACCUMULATED_ACTUAL_HISTORY"


ib, ib_source, ib_log = fetch_interbank(macro)
hist, hist_mode = merge_interbank_history(ib, ib_source, ib_log)
if len(hist):
    start = pd.to_datetime(hist["date"], errors="coerce").min()
    end = pd.to_datetime(hist["date"], errors="coerce").max()
    new_obs = len(normalize_interbank_frame(ib, "BRONZE", ib_source, 2)) if len(ib) else 0
    status.append([
        "interbank", "OK_ACCUMULATED",
        f"history_obs={len(hist)}; new_fetch_obs={new_obs}; start={start.date() if pd.notna(start) else ''}; end={end.date() if pd.notna(end) else ''}; source={ib_source}; {ib_log}",
        now()
    ])
else:
    status.append(["interbank", "ERROR", f"No ACTUAL history after merge; {ib_log}", now()])

pd.DataFrame(status, columns=["dataset", "status", "message", "RetrievedAt"]).to_csv(DATA / "refresh_log.csv", index=False, encoding="utf-8-sig")
print(pd.DataFrame(status, columns=["dataset", "status", "message", "RetrievedAt"]).to_string(index=False))

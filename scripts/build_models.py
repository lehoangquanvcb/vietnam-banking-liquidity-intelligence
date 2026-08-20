from pathlib import Path
import json
import warnings
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "model_outputs"
OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads((ROOT / "config" / "model_config.json").read_text(encoding="utf-8"))


def load(name):
    try:
        return pd.read_csv(DATA / name)
    except Exception:
        return pd.DataFrame()


def find_date(df):
    for c in ["date", "time", "report_time", "period", "datetime"]:
        if c in df.columns:
            return c
    return None


def best_numeric(df, aliases):
    for a in aliases:
        for c in df.columns:
            if a.lower() == str(c).lower() or a.lower() in str(c).lower():
                if pd.to_numeric(df[c], errors="coerce").notna().sum() > 5:
                    return c
    best, n = None, 0
    for c in df.columns:
        k = pd.to_numeric(df[c], errors="coerce").notna().sum()
        if k > n:
            best, n = c, k
    return best if n > 5 else None


def series(name, label, aliases):
    df = load(name)
    if df.empty:
        return pd.DataFrame()
    dc = find_date(df)
    vc = best_numeric(df, aliases)
    if not dc or not vc:
        return pd.DataFrame()
    x = df[[dc, vc]].copy()
    x.columns = ["date", label]
    x["date"] = pd.to_datetime(x["date"], errors="coerce")
    x[label] = pd.to_numeric(x[label], errors="coerce")
    return x.dropna().sort_values("date").drop_duplicates("date", keep="last")


def zscore(s, window):
    mu = s.rolling(window, min_periods=max(15, window // 3)).mean()
    sd = s.rolling(window, min_periods=max(15, window // 3)).std()
    return (s - mu) / sd.replace(0, np.nan)


def daily_panel():
    parts = []
    omo = series("omo.csv", "omo", ["netflow_amount", "netflow", "net flow", "net", "value"])
    fx = series("fx.csv", "fx", ["USD", "USD_VND", "close", "sell", "value"])
    ib = series("interbank.csv", "interbank", ["overnight_rate", "overnight", "rate"])
    for p in [omo, fx, ib]:
        if len(p):
            parts.append(p)
    if not parts:
        return pd.DataFrame()
    d = parts[0]
    for p in parts[1:]:
        d = d.merge(p, on="date", how="outer")
    d = d.sort_values("date").set_index("date").asfreq("B")
    if "omo" in d:
        d["OMO_z"] = -zscore(d["omo"], CFG["z_window"])
    if "fx" in d:
        d["fx"] = d["fx"].ffill(limit=3)
        d["FX_z"] = zscore(np.log(d["fx"]).diff(5), CFG["z_window"])
    if "interbank" in d:
        d["interbank"] = d["interbank"].ffill(limit=3)
        d["ON_z"] = zscore(d["interbank"], CFG["z_window"])
    components = [c for c in ["ON_z", "FX_z", "OMO_z"] if c in d.columns]
    d["LPI_components"] = d[components].notna().sum(axis=1)
    d["LPI"] = d[components].mean(axis=1, skipna=True)
    d.loc[d["LPI_components"] < CFG["lpi_min_components"], "LPI"] = np.nan
    return d.reset_index()


def forecast(y, h=20, min_obs=None):
    values = pd.to_numeric(pd.Series(y), errors="coerce").dropna().values.astype(float)
    y = pd.Series(values, index=pd.RangeIndex(len(values)))
    required = int(min_obs if min_obs is not None else CFG["min_daily_observations"])
    if len(y) < required:
        return pd.DataFrame(), {"status": "INSUFFICIENT_HISTORY", "nobs": len(y), "required_obs": required}
    test_n = min(CFG["backtest_days"], max(10, len(y) // 5))
    tr, te = y.iloc[:-test_n].copy(), y.iloc[-test_n:].copy()
    tr.index = pd.RangeIndex(len(tr)); te.index = pd.RangeIndex(len(te))
    naive = np.repeat(float(tr.iloc[-1]), len(te))
    naive_rmse = float(mean_squared_error(te.values, naive) ** 0.5)
    candidates = []
    for name, order in [("ARIMA(1,0,0)",(1,0,0)), ("ARIMA(2,0,0)",(2,0,0)), ("ARIMA(1,1,0)",(1,1,0)), ("ARIMA(0,1,1)",(0,1,1))]:
        try:
            m = SARIMAX(tr, order=order, trend="c" if order[1] == 0 else "n", enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
            pred = np.asarray(m.get_forecast(len(te)).predicted_mean, dtype=float)
            rmse = float(mean_squared_error(te.values, pred) ** 0.5)
            candidates.append((rmse, name, order))
        except Exception:
            pass
    best = min(candidates, key=lambda x: x[0]) if candidates else None
    if best is None or best[0] >= naive_rmse:
        sigma = float(pd.Series(values).diff().dropna().std())
        hs = np.arange(1, h + 1)
        last = float(values[-1]); se = sigma * np.sqrt(hs)
        out = pd.DataFrame({"horizon": hs, "forecast": last, "p10": last-1.2816*se, "p90": last+1.2816*se, "p025": last-1.96*se, "p975": last+1.96*se})
        return out, {"status":"OK_BENCHMARK", "model":"NAIVE_RANDOM_WALK", "nobs":len(y), "rmse":naive_rmse, "naive_rmse":naive_rmse, "skill_vs_naive":0.0, "confidence":"LOW"}
    rmse, name, order = best
    final = SARIMAX(y, order=order, trend="c" if order[1] == 0 else "n", enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    fc = final.get_forecast(h); ci80 = fc.conf_int(alpha=.20); ci95 = fc.conf_int(alpha=.05)
    skill = 1 - rmse / naive_rmse if naive_rmse > 0 else None
    conf = "HIGH" if skill is not None and skill >= .20 else "MEDIUM" if skill is not None and skill >= .05 else "LOW"
    out = pd.DataFrame({"horizon": range(1,h+1), "forecast": np.asarray(fc.predicted_mean), "p10": np.asarray(ci80.iloc[:,0]), "p90": np.asarray(ci80.iloc[:,1]), "p025": np.asarray(ci95.iloc[:,0]), "p975": np.asarray(ci95.iloc[:,1])})
    return out, {"status":"OK", "model":name, "nobs":len(y), "rmse":rmse, "naive_rmse":naive_rmse, "skill_vs_naive":skill, "confidence":conf, "aic":float(final.aic), "bic":float(final.bic)}


def regime(panel):
    x = panel[["date","LPI"]].dropna().copy()
    if len(x) < CFG["min_markov_observations"]:
        return pd.DataFrame(), {"status":"INSUFFICIENT_HISTORY", "nobs":len(x)}
    try:
        dates = pd.to_datetime(x["date"], errors="coerce").reset_index(drop=True)
        y = pd.Series(pd.to_numeric(x["LPI"], errors="coerce").values, index=pd.RangeIndex(len(x)))
        fit = MarkovRegression(y, k_regimes=3, trend="c", switching_variance=True).fit(disp=False, maxiter=250)
        p = fit.smoothed_marginal_probabilities
        means = [(k, float(np.average(y, weights=p[k]))) for k in range(3)]
        order = [k for k,_ in sorted(means, key=lambda q:q[1])]
        out = pd.DataFrame({"date":dates.values, "P_Excess_raw":p[order[0]].values, "P_Neutral_raw":p[order[1]].values, "P_Stress_raw":p[order[2]].values})
        for src, dst in [("P_Excess_raw","P_Excess"),("P_Neutral_raw","P_Neutral"),("P_Stress_raw","P_Stress")]:
            out[dst] = out[src].rolling(20, min_periods=1).mean()
        den = out[["P_Excess","P_Neutral","P_Stress"]].sum(axis=1)
        for c in ["P_Excess","P_Neutral","P_Stress"]:
            out[c] = out[c] / den
        return out, {"status":"OK", "nobs":len(x), "aic":float(fit.aic)}
    except Exception as exc:
        return pd.DataFrame(), {"status":"ERROR", "message":str(exc), "nobs":len(x)}


def bank_stress(lpi_fc):
    actual = load("bank_metrics.csv")
    assumptions = pd.read_csv(ROOT / "config" / "bank_assumptions.csv")
    fields = ["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]
    if not actual.empty:
        actual = actual.drop_duplicates("Ticker", keep="last").set_index("Ticker")
    assumptions = assumptions.set_index("Ticker")
    rows = []
    for ticker, fb in assumptions.iterrows():
        row = {"Ticker":ticker}; count = 0
        act = actual.loc[ticker] if (not actual.empty and ticker in actual.index) else None
        for c in fields:
            va = pd.to_numeric(pd.Series([act[c] if act is not None and c in act.index else np.nan]), errors="coerce").iloc[0]
            if pd.notna(va):
                row[c] = float(va); count += 1
            else:
                row[c] = float(fb[c])
        row["ActualMetricCount"] = count
        row["MetricCoverage"] = count / 5
        casa_source = str(act.get("CASASource","")) if act is not None else ""
        if count == 5 and casa_source == "ACTUAL_PUBLIC_SOURCE":
            row["SourceMode"] = "ACTUAL_MIXED_SOURCE"
            row["DataType"] = "ACTUAL"
        elif count == 5:
            row["SourceMode"] = "BRONZE"
            row["DataType"] = "ACTUAL"
        elif count > 0:
            row["SourceMode"] = "HYBRID"
            row["DataType"] = "MIXED"
        else:
            row["SourceMode"] = "FALLBACK"
            row["DataType"] = "ASSUMPTION"
        row["CASASource"] = casa_source or "MODEL_ASSUMPTION"
        rows.append(row)
    bank = pd.DataFrame(rows)
    for c in fields:
        bank[c] = pd.to_numeric(bank[c], errors="coerce")
        bank[c] = np.where(np.abs(bank[c]) > 2, bank[c] / 100, bank[c])
    bank["LiquidityBuffer"] = 1 - bank["LDR"]
    bank["BaseVulnerability"] = (50 + 35*(bank.LDR-.85) - 25*(bank.CASA-.20) + 45*bank.InterbankDep + 30*bank.CreditDepositGap - 10*(bank.NIM-.03) - 20*(bank.LiquidityBuffer-.15)).clip(0,100)
    scenarios = [("Current",0.0)]
    if len(lpi_fc) >= 5: scenarios.append(("5D", float(lpi_fc.iloc[4].forecast)))
    if len(lpi_fc) >= 20: scenarios.append(("20D", float(lpi_fc.iloc[19].forecast)))
    out = []
    for horizon, lpi in scenarios:
        t = bank.copy(); t["Horizon"] = horizon; t["LPI"] = lpi
        t["StressVulnerability"] = (t.BaseVulnerability * (1 + CFG["bank_stress_beta_per_lpi"] * max(lpi,0))).clip(0,100)
        t["FundingCostShock_ppt"] = 2 * t.StressVulnerability / 100
        t["StressedNIM"] = np.maximum(0, t.NIM - t.FundingCostShock_ppt / 100)
        t["Watch"] = np.select([(t.StressVulnerability >= CFG["red_threshold"]) | (t.StressedNIM < CFG["nim_red_threshold"]), t.StressVulnerability >= CFG["amber_threshold"]], ["RED","AMBER"], default="GREEN")
        out.append(t)
    return pd.concat(out, ignore_index=True)


panel = daily_panel()
panel.to_csv(OUT / "daily_panel.csv", index=False, encoding="utf-8-sig")
lpi_fc, lpi_diag = forecast(panel["LPI"]) if "LPI" in panel else (pd.DataFrame(), {"status":"NO_LPI"})
if len(lpi_fc):
    last = pd.to_datetime(panel["date"]).max(); lpi_fc["date"] = pd.bdate_range(last + pd.offsets.BDay(1), periods=len(lpi_fc))
    lpi_fc.to_csv(OUT / "lpi_forecast.csv", index=False, encoding="utf-8-sig")
ib_actual = series("interbank.csv", "interbank", ["overnight_rate","overnight","rate"])
ib_n = len(ib_actual)
ib_exploratory_min = int(CFG.get("min_interbank_exploratory_observations", 40))
ib_production_min = int(CFG.get("min_interbank_production_observations", 80))
if ib_n == 0:
    ib_fc, ib_diag = pd.DataFrame(), {"status":"NO_INTERBANK_DATA", "nobs":0, "forecast_tier":"NONE"}
elif ib_n < ib_exploratory_min:
    ib_fc, ib_diag = pd.DataFrame(), {
        "status":"INSUFFICIENT_HISTORY", "nobs":ib_n,
        "required_obs":ib_exploratory_min, "forecast_tier":"ACTUAL_ONLY",
        "production_required_obs":ib_production_min
    }
else:
    ib_fc, ib_diag = forecast(ib_actual["interbank"], min_obs=ib_exploratory_min)
    if ib_n < ib_production_min:
        ib_diag["status"] = "EXPLORATORY_LOW_CONFIDENCE"
        ib_diag["forecast_tier"] = "EXPLORATORY"
        ib_diag["confidence"] = "LOW"
        ib_diag["production_required_obs"] = ib_production_min
        ib_diag["governance_note"] = "Exploratory only: fewer than production minimum observations."
    else:
        ib_diag["forecast_tier"] = "PRODUCTION"
        ib_diag["production_required_obs"] = ib_production_min
        ib_diag["governance_note"] = "Production-eligible history threshold met."
if len(ib_fc):
    last = pd.to_datetime(ib_actual["date"]).max()
    ib_fc["date"] = pd.bdate_range(last + pd.offsets.BDay(1), periods=len(ib_fc))
    ib_fc["ForecastTier"] = ib_diag.get("forecast_tier","UNKNOWN")
    ib_fc.to_csv(OUT / "interbank_forecast.csv", index=False, encoding="utf-8-sig")
reg, reg_diag = regime(panel) if "LPI" in panel else (pd.DataFrame(), {"status":"NO_LPI"})
if len(reg): reg.to_csv(OUT / "regime.csv", index=False, encoding="utf-8-sig")
stress = bank_stress(lpi_fc)
stress.to_csv(OUT / "bank_stress.csv", index=False, encoding="utf-8-sig")
summary = {
    "lpi": lpi_diag,
    "interbank": ib_diag,
    "regime": reg_diag,
    "bank_stress": {
        "valid_banks": int(stress[stress.Horizon == "Current"].BaseVulnerability.notna().sum()),
        "bronze": int((stress[stress.Horizon == "Current"].SourceMode == "BRONZE").sum()),
        "actual_mixed": int((stress[stress.Horizon == "Current"].SourceMode == "ACTUAL_MIXED_SOURCE").sum()),
        "hybrid": int((stress[stress.Horizon == "Current"].SourceMode == "HYBRID").sum()),
        "fallback": int((stress[stress.Horizon == "Current"].SourceMode == "FALLBACK").sum()),
    },
    "generated_at": pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat(),
}
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
pd.DataFrame([
    ["LPI", lpi_diag.get("status"), lpi_diag.get("model"), lpi_diag.get("nobs"), lpi_diag.get("rmse"), lpi_diag.get("naive_rmse"), lpi_diag.get("skill_vs_naive"), lpi_diag.get("confidence"), "PRODUCTION", None],
    ["Interbank ON", ib_diag.get("status"), ib_diag.get("model"), ib_diag.get("nobs"), ib_diag.get("rmse"), ib_diag.get("naive_rmse"), ib_diag.get("skill_vs_naive"), ib_diag.get("confidence"), ib_diag.get("forecast_tier"), ib_diag.get("production_required_obs")],
    ["Liquidity Regime", reg_diag.get("status"), None, reg_diag.get("nobs"), None, None, None, None, "PRODUCTION", None],
], columns=["Target","Status","Model","Observations","RMSE","NaiveRMSE","SkillVsNaive","Confidence","ForecastTier","ProductionMinObs"]).to_csv(OUT / "diagnostics.csv", index=False, encoding="utf-8-sig")
print(json.dumps(summary, ensure_ascii=False, indent=2))

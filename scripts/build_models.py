from pathlib import Path
import json
import warnings
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import SimpleExpSmoothing
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
    test_n = min(CFG["backtest_days"], max(5, len(y) // 4))
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



def _mean_reversion_params(train):
    a = np.asarray(train, dtype=float)
    if len(a) < 4:
        return float(np.mean(a)), 0.0, float(np.std(np.diff(a))) if len(a) > 1 else 0.0
    x, y = a[:-1], a[1:]
    X = np.column_stack([np.ones(len(x)), x])
    try:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        intercept, phi = float(beta[0]), float(np.clip(beta[1], -0.98, 0.98))
    except Exception:
        phi = 0.0; intercept = float(np.mean(a))
    residual = y - (intercept + phi * x)
    sigma = float(np.std(residual, ddof=1)) if len(residual) > 1 else float(np.std(np.diff(a)))
    long_mean = intercept / (1 - phi) if abs(phi) < .98 else float(np.mean(a))
    return float(long_mean), phi, max(sigma, 1e-6)


def _one_step_candidate(train, model_name):
    train = np.asarray(train, dtype=float)
    if model_name == "NAIVE_RANDOM_WALK":
        return float(train[-1])
    if model_name == "HISTORICAL_MEAN":
        return float(np.mean(train))
    if model_name == "MEAN_REVERSION_AR1":
        long_mean, phi, _ = _mean_reversion_params(train)
        return float(long_mean + phi * (train[-1] - long_mean))
    if model_name == "ETS_SIMPLE":
        fit = SimpleExpSmoothing(pd.Series(train, index=pd.RangeIndex(len(train))), initialization_method="estimated").fit(optimized=True)
        return float(np.asarray(fit.forecast(1))[0])
    if model_name.startswith("ARIMA"):
        order_map = {
            "ARIMA(1,0,0)": (1,0,0), "ARIMA(2,0,0)": (2,0,0),
            "ARIMA(1,1,0)": (1,1,0), "ARIMA(0,1,1)": (0,1,1),
        }
        order = order_map[model_name]
        s = pd.Series(train, index=pd.RangeIndex(len(train)))
        fit = SARIMAX(s, order=order, trend="c" if order[1] == 0 else "n", enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
        return float(np.asarray(fit.get_forecast(1).predicted_mean)[0])
    raise ValueError(model_name)


def _final_candidate_forecast(values, model_name, h):
    values = np.asarray(values, dtype=float)
    hs = np.arange(1, h + 1)
    if model_name == "NAIVE_RANDOM_WALK":
        fc = np.repeat(float(values[-1]), h)
        sigma = max(float(pd.Series(values).diff().dropna().std()), 1e-6)
        se = sigma * np.sqrt(hs)
        extra = {}
    elif model_name == "HISTORICAL_MEAN":
        mu = float(np.mean(values)); fc = np.repeat(mu, h)
        sigma = max(float(np.std(values - mu, ddof=1)), 1e-6)
        se = np.repeat(sigma * np.sqrt(1 + 1/len(values)), h)
        extra = {"long_run_mean": mu}
    elif model_name == "MEAN_REVERSION_AR1":
        long_mean, phi, sigma = _mean_reversion_params(values)
        f=[]; prev=float(values[-1])
        for _ in hs:
            prev = long_mean + phi * (prev - long_mean); f.append(prev)
        fc=np.asarray(f)
        if abs(phi) < .999:
            se=np.asarray([sigma*np.sqrt(sum(phi**(2*j) for j in range(k))) for k in hs])
        else:
            se=sigma*np.sqrt(hs)
        extra={"long_run_mean":long_mean,"mean_reversion_phi":phi}
    elif model_name == "ETS_SIMPLE":
        s=pd.Series(values,index=pd.RangeIndex(len(values)))
        fit=SimpleExpSmoothing(s, initialization_method="estimated").fit(optimized=True)
        fc=np.asarray(fit.forecast(h),dtype=float)
        residual=np.asarray(fit.resid,dtype=float)
        sigma=max(float(np.nanstd(residual,ddof=1)),1e-6)
        se=sigma*np.sqrt(hs)
        extra={"smoothing_level":float(fit.params.get("smoothing_level",np.nan))}
    else:
        order_map = {
            "ARIMA(1,0,0)": (1,0,0), "ARIMA(2,0,0)": (2,0,0),
            "ARIMA(1,1,0)": (1,1,0), "ARIMA(0,1,1)": (0,1,1),
        }
        order=order_map[model_name]
        s=pd.Series(values,index=pd.RangeIndex(len(values)))
        fit=SARIMAX(s,order=order,trend="c" if order[1]==0 else "n",enforce_stationarity=False,enforce_invertibility=False).fit(disp=False)
        pred=fit.get_forecast(h)
        fc=np.asarray(pred.predicted_mean,dtype=float)
        ci80=pred.conf_int(alpha=.20); ci95=pred.conf_int(alpha=.05)
        out=pd.DataFrame({"horizon":hs,"forecast":fc,"p10":np.asarray(ci80.iloc[:,0]),"p90":np.asarray(ci80.iloc[:,1]),"p025":np.asarray(ci95.iloc[:,0]),"p975":np.asarray(ci95.iloc[:,1])})
        return out,{"aic":float(fit.aic),"bic":float(fit.bic)}
    out=pd.DataFrame({"horizon":hs,"forecast":fc,"p10":fc-1.2816*se,"p90":fc+1.2816*se,"p025":fc-1.96*se,"p975":fc+1.96*se})
    return out,extra


def forecast_interbank_governed(y, h=20, min_obs=18):
    values = pd.to_numeric(pd.Series(y), errors="coerce").dropna().values.astype(float)
    n=len(values)
    if n < min_obs:
        return pd.DataFrame(), {"status":"INSUFFICIENT_HISTORY","nobs":n,"required_obs":min_obs}, pd.DataFrame()
    # Expanding-window rolling-origin 1-step evaluation; preserve enough observations for model fitting.
    test_n=min(max(5,n//4), 10)
    start=max(8,n-test_n)
    models=["NAIVE_RANDOM_WALK","HISTORICAL_MEAN","MEAN_REVERSION_AR1","ETS_SIMPLE","ARIMA(1,0,0)","ARIMA(2,0,0)","ARIMA(1,1,0)","ARIMA(0,1,1)"]
    errors={m:[] for m in models}
    abs_errors={m:[] for m in models}
    for i in range(start,n):
        train=values[:i]; actual=float(values[i])
        for m in models:
            try:
                pred=_one_step_candidate(train,m)
                errors[m].append((actual-pred)**2)
                abs_errors[m].append(abs(actual-pred))
            except Exception:
                pass
    rows=[]
    naive_rmse=None
    for m in models:
        k=len(errors[m])
        if not k: continue
        rmse=float(np.sqrt(np.mean(errors[m]))); mae=float(np.mean(abs_errors[m]))
        if m=="NAIVE_RANDOM_WALK": naive_rmse=rmse
        rows.append({"Model":m,"RollingPoints":k,"RMSE":rmse,"MAE":mae})
    comp=pd.DataFrame(rows)
    if comp.empty:
        return pd.DataFrame(),{"status":"MODEL_ERROR","nobs":n},comp
    if naive_rmse is None:
        naive_rmse=float(comp.RMSE.max())
    comp["SkillVsNaive"]=1-comp["RMSE"]/naive_rmse if naive_rmse>0 else np.nan
    best=comp.sort_values(["RMSE","MAE"]).iloc[0]
    winner=str(best.Model)
    # Governance: a complex model must beat naive; otherwise publish naive.
    if winner != "NAIVE_RANDOM_WALK" and float(best.RMSE) >= naive_rmse:
        winner="NAIVE_RANDOM_WALK"
        best=comp[comp.Model==winner].iloc[0]
    comp["Selected"]=comp.Model.eq(winner)
    fc,extra=_final_candidate_forecast(values,winner,h)
    skill=float(1-float(best.RMSE)/naive_rmse) if naive_rmse>0 else None
    confidence="HIGH" if skill is not None and skill>=.20 else "MEDIUM" if skill is not None and skill>=.05 else "LOW"
    diag={
        "status":"OK","model":winner,"nobs":n,"rmse":float(best.RMSE),"mae":float(best.MAE),
        "naive_rmse":float(naive_rmse),"skill_vs_naive":skill,"confidence":confidence,
        "selection_basis":"ROLLING_ORIGIN_1STEP_RMSE","rolling_test_points":int(best.RollingPoints),
        "candidate_count":int(len(comp)),
    }
    diag.update(extra)
    return fc,diag,comp


def _forecast_shape_metrics(values, model_name, h=20):
    """Economic-usefulness diagnostics without changing statistical champion."""
    try:
        fc, _ = _final_candidate_forecast(values, model_name, h)
        current = float(values[-1])
        f1 = float(fc.iloc[0]["forecast"])
        f5 = float(fc.iloc[min(4, len(fc)-1)]["forecast"])
        f20 = float(fc.iloc[min(19, len(fc)-1)]["forecast"])
        path = pd.to_numeric(fc["forecast"], errors="coerce").dropna()
        path_range = float(path.max() - path.min()) if len(path) else np.nan
        directional_move = float(f20 - current)
        return {
            "Forecast1D": f1, "Forecast5D": f5, "Forecast20D": f20,
            "DirectionalMove20D": directional_move,
            "ForecastPathRange": path_range,
            # Flatness here means "same forecast across horizons", which is what matters
            # for dashboard information content. A level shift from current to a constant
            # future mean is still a flat term structure.
            "IsFlat": bool(path_range < 0.10),
        }
    except Exception:
        return {
            "Forecast1D": np.nan, "Forecast5D": np.nan, "Forecast20D": np.nan,
            "DirectionalMove20D": np.nan, "ForecastPathRange": np.nan, "IsFlat": False,
        }


def select_directional_challenger(values, comp, champion, h=20, tolerance=1.15):
    """
    Challenger is NOT the production champion.
    It is shown only when:
    - it beats naive;
    - its RMSE is within tolerance of champion;
    - it produces a non-trivial directional path.
    """
    if comp is None or comp.empty:
        return pd.DataFrame(), pd.DataFrame(), {}
    c = comp.copy()
    champion_row = c[c["Model"] == champion]
    if champion_row.empty:
        return pd.DataFrame(), pd.DataFrame(), {}
    champion_rmse = float(champion_row.iloc[0]["RMSE"])
    naive_row = c[c["Model"] == "NAIVE_RANDOM_WALK"]
    naive_rmse = float(naive_row.iloc[0]["RMSE"]) if len(naive_row) else np.inf

    shape_rows = []
    for m in c["Model"].astype(str):
        sm = _forecast_shape_metrics(values, m, h)
        sm["Model"] = m
        shape_rows.append(sm)
    shape = pd.DataFrame(shape_rows)
    c = c.merge(shape, on="Model", how="left")

    eligible = c[
        (c["Model"] != champion)
        & (pd.to_numeric(c["RMSE"], errors="coerce") < naive_rmse)
        & (pd.to_numeric(c["RMSE"], errors="coerce") <= champion_rmse * tolerance)
        & (~c["IsFlat"].fillna(False))
        & (pd.to_numeric(c["DirectionalMove20D"], errors="coerce").abs() >= 0.15)
    ].copy()

    if eligible.empty:
        return pd.DataFrame(), c, {}
    eligible["DirectionalUtilityScore"] = (
        pd.to_numeric(eligible["SkillVsNaive"], errors="coerce").fillna(0)
        + 0.05 * pd.to_numeric(eligible["DirectionalMove20D"], errors="coerce").abs()
    )
    challenger = eligible.sort_values(["RMSE", "DirectionalUtilityScore"], ascending=[True, False]).iloc[0]
    m = str(challenger["Model"])
    fc, extra = _final_candidate_forecast(values, m, h)
    info = {
        "model": m,
        "rmse": float(challenger["RMSE"]),
        "mae": float(challenger["MAE"]),
        "skill_vs_naive": float(challenger["SkillVsNaive"]),
        "forecast_20d": float(challenger["Forecast20D"]),
        "directional_move_20d": float(challenger["DirectionalMove20D"]),
        "rmse_premium_vs_champion": float(challenger["RMSE"] / champion_rmse - 1),
        "role": "DIRECTIONAL_CHALLENGER",
    }
    info.update(extra)
    return fc, c, info


def interbank_market_state(values):
    """Descriptive market state from ACTUAL observations only."""
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    if len(x) == 0:
        return {}
    current = float(x.iloc[-1])
    mean = float(x.mean())
    median = float(x.median())
    vol = float(x.diff().dropna().std()) if len(x) > 2 else None
    level_vol = float(x.std()) if len(x) > 1 else None
    recent3 = float(x.tail(min(3,len(x))).mean())
    recent5 = float(x.tail(min(5,len(x))).mean())
    pct = float((x <= current).mean())
    q25 = float(x.quantile(.25)); q75 = float(x.quantile(.75))
    if current >= q75:
        regime = "TIGHT"
        regime_vi = "Căng"
    elif current <= q25:
        regime = "EASY"
        regime_vi = "Dễ chịu"
    else:
        regime = "NORMAL"
        regime_vi = "Trung tính"
    if recent3 > recent5 + 0.30:
        momentum = "RISING"
        momentum_vi = "Đang tăng"
    elif recent3 < recent5 - 0.30:
        momentum = "FALLING"
        momentum_vi = "Đang giảm"
    else:
        momentum = "STABLE"
        momentum_vi = "Đi ngang"
    return {
        "current": current, "mean": mean, "median": median,
        "recent3_mean": recent3, "recent5_mean": recent5,
        "change_volatility": vol, "level_volatility": level_vol,
        "current_percentile": pct, "q25": q25, "q75": q75,
        "market_regime": regime, "market_regime_vi": regime_vi,
        "momentum": momentum, "momentum_vi": momentum_vi,
    }



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
ib_exploratory_min = int(CFG.get("min_interbank_exploratory_observations", 18))
ib_production_min = int(CFG.get("min_interbank_production_observations", 60))
ib_comp = pd.DataFrame()
if ib_n == 0:
    ib_fc, ib_diag = pd.DataFrame(), {"status":"NO_INTERBANK_DATA", "nobs":0, "forecast_tier":"NONE"}
elif ib_n < ib_exploratory_min:
    ib_fc, ib_diag = pd.DataFrame(), {
        "status":"INSUFFICIENT_HISTORY", "nobs":ib_n,
        "required_obs":ib_exploratory_min, "forecast_tier":"ACTUAL_ONLY",
        "production_required_obs":ib_production_min
    }
else:
    ib_values = pd.to_numeric(ib_actual["interbank"], errors="coerce").dropna().values.astype(float)
    ib_fc, ib_diag, ib_comp = forecast_interbank_governed(
        ib_actual["interbank"],
        h=CFG.get("forecast_horizon_business_days",20),
        min_obs=ib_exploratory_min
    )

    # Statistical champion remains selected by rolling RMSE.
    champion = ib_diag.get("model")
    challenger_fc, enriched_comp, challenger_info = select_directional_challenger(
        ib_values, ib_comp, champion,
        h=CFG.get("forecast_horizon_business_days",20),
        tolerance=float(CFG.get("interbank_challenger_rmse_tolerance",1.15))
    )
    if len(enriched_comp):
        ib_comp = enriched_comp
        ib_comp["Role"] = np.select(
            [ib_comp["Model"].eq(champion), ib_comp["Model"].eq(challenger_info.get("model"))],
            ["STATISTICAL_CHAMPION","DIRECTIONAL_CHALLENGER"],
            default="CANDIDATE"
        )
    market_state = interbank_market_state(ib_values)
    ib_diag["market_state"] = market_state
    ib_diag["challenger"] = challenger_info
    ib_diag["champion_is_flat"] = bool(
        len(ib_comp)
        and ib_comp.loc[ib_comp["Model"].eq(champion), "IsFlat"].fillna(False).astype(bool).any()
    )

    if ib_n < ib_production_min:
        ib_diag["status"] = "EXPLORATORY_LOW_CONFIDENCE"
        ib_diag["forecast_tier"] = "EXPLORATORY"
        ib_diag["confidence"] = "LOW"
        ib_diag["production_required_obs"] = ib_production_min
        ib_diag["governance_note"] = (
            "Exploratory only: history is below production threshold. "
            "Statistical Champion is selected by rolling-origin RMSE. "
            "Directional Challenger is informational only and never replaces the champion."
        )
    else:
        ib_diag["forecast_tier"] = "PRODUCTION"
        ib_diag["production_required_obs"] = ib_production_min
        ib_diag["governance_note"] = (
            "Production history threshold met; Statistical Champion selected by rolling-origin RMSE versus naive. "
            "Directional Challenger remains secondary."
        )

    if len(challenger_fc):
        last = pd.to_datetime(ib_actual["date"]).max()
        challenger_fc["date"] = pd.bdate_range(last + pd.offsets.BDay(1), periods=len(challenger_fc))
        challenger_fc["ForecastTier"] = ib_diag.get("forecast_tier","UNKNOWN")
        challenger_fc["SelectedModel"] = challenger_info.get("model","UNKNOWN")
        challenger_fc.to_csv(OUT / "interbank_challenger_forecast.csv", index=False, encoding="utf-8-sig")

if len(ib_comp):
    ib_comp.to_csv(OUT / "interbank_model_comparison.csv", index=False, encoding="utf-8-sig")
if len(ib_fc):
    last = pd.to_datetime(ib_actual["date"]).max()
    ib_fc["date"] = pd.bdate_range(last + pd.offsets.BDay(1), periods=len(ib_fc))
    ib_fc["ForecastTier"] = ib_diag.get("forecast_tier","UNKNOWN")
    ib_fc["SelectedModel"] = ib_diag.get("model","UNKNOWN")
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
    ["LPI", lpi_diag.get("status"), lpi_diag.get("model"), lpi_diag.get("nobs"), lpi_diag.get("rmse"), lpi_diag.get("naive_rmse"), lpi_diag.get("skill_vs_naive"), lpi_diag.get("confidence"), "PRODUCTION", None, "HOLDOUT_RMSE", None],
    ["Interbank ON", ib_diag.get("status"), ib_diag.get("model"), ib_diag.get("nobs"), ib_diag.get("rmse"), ib_diag.get("naive_rmse"), ib_diag.get("skill_vs_naive"), ib_diag.get("confidence"), ib_diag.get("forecast_tier"), ib_diag.get("production_required_obs"), ib_diag.get("selection_basis"), ib_diag.get("rolling_test_points")],
    ["Liquidity Regime", reg_diag.get("status"), None, reg_diag.get("nobs"), None, None, None, None, "PRODUCTION", None, None, None],
], columns=["Target","Status","Model","Observations","RMSE","NaiveRMSE","SkillVsNaive","Confidence","ForecastTier","ProductionMinObs","SelectionBasis","RollingTestPoints"]).to_csv(OUT / "diagnostics.csv", index=False, encoding="utf-8-sig")
print(json.dumps(summary, ensure_ascii=False, indent=2))

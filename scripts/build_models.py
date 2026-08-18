
from pathlib import Path
import json, math, warnings, re
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from statsmodels.tsa.api import VAR
from sklearn.metrics import mean_squared_error, mean_absolute_error

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
OUT=DATA/"model_outputs"
OUT.mkdir(exist_ok=True)
CFG=json.loads((ROOT/"config"/"model_config.json").read_text(encoding="utf-8"))

def load(name):
    p=DATA/f"{name}.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()

def date_col(df):
    for c in ["date","time","period","report_time","report_period","datetime"]:
        if c in df.columns:
            return c
    return None

def best_numeric_col(df,candidates):
    if df.empty:
        return None
    lower={str(c).lower():c for c in df.columns}
    for cand in candidates:
        for k,c in lower.items():
            if cand.lower()==k:
                return c
    for cand in candidates:
        for k,c in lower.items():
            if cand.lower() in k:
                return c
    numeric=[]
    for c in df.columns:
        v=pd.to_numeric(df[c],errors="coerce")
        numeric.append((v.notna().sum(),c))
    numeric.sort(reverse=True)
    return numeric[0][1] if numeric and numeric[0][0]>5 else None

def series_from(name,candidates):
    df=load(name)
    if df.empty:
        return pd.DataFrame()
    dc=date_col(df)
    vc=best_numeric_col(df,candidates)
    if not dc or not vc:
        return pd.DataFrame()
    x=df[[dc,vc]].copy()
    x.columns=["date",name]
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    x[name]=pd.to_numeric(x[name],errors="coerce")
    x=x.dropna(subset=["date",name]).sort_values("date").drop_duplicates("date",keep="last")
    return x

def rolling_z(s,w=60):
    m=s.rolling(w,min_periods=max(15,w//3)).mean()
    sd=s.rolling(w,min_periods=max(15,w//3)).std()
    return (s-m)/sd.replace(0,np.nan)

def build_daily_panel():
    parts=[]
    omo=series_from("omo_bronze",["netflow_amount","netflow","net flow","net","value"])
    ib=series_from("interbank_bronze",["overnight","on","qua đêm","o/n","interbank","value","rate"])
    fx=series_from("fx_bronze",["usd","usd_vnd","close","sell","value","rate"])
    for x in [omo,ib,fx]:
        if len(x):
            parts.append(x)
    if not parts:
        return pd.DataFrame()
    d=parts[0]
    for p in parts[1:]:
        d=d.merge(p,on="date",how="outer")
    d=d.sort_values("date").set_index("date").asfreq("B")
    if "interbank_bronze" in d:
        d["interbank_bronze"]=d["interbank_bronze"].ffill(limit=3)
        d["ON_z"]=rolling_z(d["interbank_bronze"],CFG["z_window"])
    if "fx_bronze" in d:
        d["fx_bronze"]=d["fx_bronze"].ffill(limit=3)
        d["FX_ret5"]=np.log(d["fx_bronze"]).diff(5)
        d["FX_z"]=rolling_z(d["FX_ret5"],CFG["z_window"])
    if "omo_bronze" in d:
        # Missing OMO on a business day is left as NaN; no synthetic flow fill.
        d["OMO_z"]=-rolling_z(d["omo_bronze"],CFG["z_window"])
    comps=[c for c in ["ON_z","FX_z","OMO_z"] if c in d.columns]
    if comps:
        d["LPI"]=d[comps].mean(axis=1,skipna=True)
        d["LPI_components"]=d[comps].notna().sum(axis=1)
    return d.reset_index()

def fit_forecast(y,horizon=20,min_obs=80):
    y=pd.Series(y).dropna().astype(float)
    if len(y)<min_obs:
        return None,{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":int(len(y))}
    test_n=min(CFG["backtest_days"],max(10,len(y)//5))
    train=y.iloc[:-test_n]
    test=y.iloc[-test_n:]
    candidates=[
        ("ARIMA(1,0,0)",(1,0,0)),
        ("ARIMA(2,0,0)",(2,0,0)),
        ("ARIMA(1,1,0)",(1,1,0)),
        ("ARIMA(0,1,1)",(0,1,1)),
    ]
    rows=[]
    best=None
    for name,order in candidates:
        try:
            m=SARIMAX(train,order=order,trend="c" if order[1]==0 else "n",
                      enforce_stationarity=False,enforce_invertibility=False).fit(disp=False)
            p=m.get_forecast(len(test)).predicted_mean
            rmse=float(mean_squared_error(test,p)**.5)
            mae=float(mean_absolute_error(test,p))
            rows.append([name,order,rmse,mae])
            if best is None or rmse<best[2]:
                best=(name,order,rmse,mae)
        except Exception:
            continue
    naive=np.repeat(train.iloc[-1],len(test))
    naive_rmse=float(mean_squared_error(test,naive)**.5)
    if best is None:
        return None,{"status":"MODEL_FIT_FAILED","nobs":int(len(y))}
    name,order,rmse,mae=best
    final=SARIMAX(y,order=order,trend="c" if order[1]==0 else "n",
                  enforce_stationarity=False,enforce_invertibility=False).fit(disp=False)
    fc=final.get_forecast(horizon)
    mean=fc.predicted_mean
    ci80=fc.conf_int(alpha=.20)
    ci95=fc.conf_int(alpha=.05)
    frame=pd.DataFrame({
        "horizon":np.arange(1,horizon+1),
        "forecast":mean.values,
        "p10":ci80.iloc[:,0].values,
        "p90":ci80.iloc[:,1].values,
        "p025":ci95.iloc[:,0].values,
        "p975":ci95.iloc[:,1].values,
    })
    diag={
        "status":"OK","model":name,"order":list(order),"nobs":int(len(y)),
        "test_n":int(test_n),"rmse":rmse,"mae":mae,"naive_rmse":naive_rmse,
        "skill_vs_naive":float(1-rmse/naive_rmse) if naive_rmse>0 else None,
        "aic":float(final.aic),"bic":float(final.bic),
        "candidate_results":[{"model":r[0],"rmse":r[2],"mae":r[3]} for r in rows]
    }
    return frame,diag

def classify_lpi(x):
    if pd.isna(x): return "Không đủ dữ liệu"
    if x>=2: return "Căng thẳng cao"
    if x>=1: return "Căng thẳng vừa"
    if x>-1: return "Trung tính"
    return "Dư thừa thanh khoản"

def regime_model(d):
    x=d[["date","LPI"]].dropna()
    if len(x)<CFG["min_markov_observations"]:
        return pd.DataFrame(),{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":len(x)}
    try:
        m=MarkovRegression(x["LPI"],k_regimes=3,trend="c",switching_variance=True)
        r=m.fit(disp=False,maxiter=250)
        probs=r.smoothed_marginal_probabilities
        means=[]
        for k in range(3):
            w=probs[k].values
            means.append((k,float(np.nansum(w*x["LPI"].values)/max(np.nansum(w),1e-9))))
        order=[k for k,_ in sorted(means,key=lambda z:z[1])]
        out=pd.DataFrame({
            "date":x["date"].values,
            "P_Excess_raw":probs[order[0]].values,
            "P_Neutral_raw":probs[order[1]].values,
            "P_Stress_raw":probs[order[2]].values,
        })
        # 20-business-day smoothing makes regime visualization interpretable.
        for src,dst in [("P_Excess_raw","P_Excess"),("P_Neutral_raw","P_Neutral"),("P_Stress_raw","P_Stress")]:
            out[dst]=out[src].rolling(20,min_periods=1).mean()
        total=out[["P_Excess","P_Neutral","P_Stress"]].sum(axis=1).replace(0,np.nan)
        for c in ["P_Excess","P_Neutral","P_Stress"]:
            out[c]=out[c]/total
        out["Regime"]=out[["P_Excess","P_Neutral","P_Stress"]].idxmax(axis=1).str.replace("P_","")
        return out,{"status":"OK","nobs":len(x),"aic":float(r.aic)}
    except Exception as e:
        return pd.DataFrame(),{"status":"ERROR","message":str(e),"nobs":len(x)}

def driver_table(d):
    if d.empty:
        return pd.DataFrame()
    last=d.dropna(subset=["LPI"]).tail(1)
    if last.empty:
        return pd.DataFrame()
    r=last.iloc[0]
    labels={
        "ON_z":("Lãi suất liên ngân hàng","ON tăng so với lịch sử làm tăng áp lực thanh khoản."),
        "FX_z":("Áp lực tỷ giá","USD/VND tăng nhanh thường làm dư địa bơm thanh khoản thận trọng hơn."),
        "OMO_z":("OMO/NHNN","Bơm ròng OMO làm giảm áp lực; hút ròng làm tăng áp lực."),
    }
    rows=[]
    for c,(lab,desc) in labels.items():
        if c in d.columns and pd.notna(r.get(c,np.nan)):
            val=float(r[c])
            rows.append([lab,val,abs(val),"Tăng stress" if val>0 else "Giảm stress",desc])
    return pd.DataFrame(rows,columns=["Driver","Contribution z","Abs Contribution","Direction","Interpretation"]).sort_values("Abs Contribution",ascending=False)

def monthly_var():
    candidates={
        "M2":("m2_bronze",["value","m2","money"]),
        "Credit":("credit_bronze",["value","credit"]),
        "CPI":("cpi_bronze",["value","cpi"]),
        "FX":("fx_bronze",["usd","usd_vnd","close","value"]),
    }
    merged=None
    for label,(name,cols) in candidates.items():
        x=series_from(name,cols)
        if x.empty: continue
        x=x.rename(columns={name:label}).set_index("date").resample("ME").last().reset_index()
        merged=x if merged is None else merged.merge(x,on="date",how="outer")
    if merged is None:
        return pd.DataFrame(),{"status":"NO_DATA"}
    m=merged.sort_values("date").set_index("date")
    change=pd.DataFrame(index=m.index)
    for c in m.columns:
        s=pd.to_numeric(m[c],errors="coerce")
        if (s>0).mean()>.8:
            change[c]=np.log(s).diff()
        else:
            change[c]=s.diff()
    change=change.dropna()
    if len(change)<CFG["min_monthly_var_observations"] or change.shape[1]<2:
        return pd.DataFrame(),{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":len(change),"variables":list(change.columns)}
    try:
        model=VAR(change)
        lag=max(1,min(3,model.select_order(maxlags=min(6,len(change)//5)).aic or 1))
        fit=model.fit(lag)
        fc=fit.forecast(change.values[-lag:],steps=3)
        out=pd.DataFrame(fc,columns=change.columns)
        out.insert(0,"horizon_month",[1,2,3])
        return out,{"status":"OK","nobs":len(change),"variables":list(change.columns),"lag":lag,"aic":float(fit.aic)}
    except Exception as e:
        return pd.DataFrame(),{"status":"ERROR","message":str(e)}

def bank_stress(lpi_forecast):
    actual=load("bank_actuals_bronze")
    fallback=load("bank_fallback_assumptions")

    metric_cols=["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]
    if len(actual):
        a=actual.copy()
        for c in metric_cols:
            if c not in a.columns:
                a[c]=np.nan
            a[c]=pd.to_numeric(a[c],errors="coerce")
        a["MetricCoverage"]=a[metric_cols].notna().mean(axis=1)
        # Require at least 3/5 quantitative Bronze metrics.
        useful=a[a["MetricCoverage"]>=0.60].copy()
    else:
        useful=pd.DataFrame()

    # Fallback at ticker level whenever Bronze cannot actually support the stress model.
    missing=fallback[~fallback["Ticker"].isin(useful["Ticker"])] if len(useful) else fallback.copy()
    if len(missing):
        missing=missing.copy()
        missing["MetricCoverage"]=missing[metric_cols].notna().mean(axis=1)
    bank=pd.concat([useful,missing],ignore_index=True) if len(useful) else missing

    for c in metric_cols:
        bank[c]=pd.to_numeric(bank[c],errors="coerce")
        bank[c]=np.where(abs(bank[c])>2,bank[c]/100,bank[c])

    bank["LiquidityBuffer"]=1-bank["LDR"]
    bank["Coverage"]=bank[metric_cols].notna().mean(axis=1)
    raw=(50
         +35*(bank["LDR"]-.85)
         -25*(bank["CASA"]-.20)
         +45*bank["InterbankDep"]
         +30*bank["CreditDepositGap"]
         -10*(bank["NIM"]-.03)
         -20*(bank["LiquidityBuffer"]-.15))
    bank["BaseVulnerability"]=raw.clip(0,100)
    bank.loc[bank["Coverage"]<0.60,"BaseVulnerability"]=np.nan

    scenarios=[("Current",0.0)]
    if lpi_forecast is not None and len(lpi_forecast):
        for h in [5,20]:
            if h<=len(lpi_forecast):
                scenarios.append((f"{h}D",float(lpi_forecast.iloc[h-1]["forecast"])))

    out=[]
    beta=CFG["bank_stress_beta_per_lpi"]
    for label,lpi in scenarios:
        temp=bank.copy()
        temp["Horizon"]=label
        temp["LPI"]=lpi
        mult=1+beta*max(0,lpi)
        temp["StressVulnerability"]=(temp["BaseVulnerability"]*mult).clip(0,100)
        temp["FundingCostShock_ppt"]=2.0*temp["StressVulnerability"]/100
        temp["StressedNIM"]=np.maximum(0,temp["NIM"]-temp["FundingCostShock_ppt"]/100)
        temp["Watch"]=np.select(
            [(temp["StressVulnerability"]>=75)|(temp["StressedNIM"]<.02),temp["StressVulnerability"]>=60],
            ["RED","AMBER"],default="GREEN"
        )
        out.append(temp[[
            "Ticker","Horizon","LPI","BaseVulnerability","StressVulnerability",
            "FundingCostShock_ppt","StressedNIM","Watch","Coverage","Data Type","Source Mode"
        ]])
    return pd.concat(out,ignore_index=True)

def main():
    d=build_daily_panel()
    d.to_csv(OUT/"daily_liquidity_panel.csv",index=False,encoding="utf-8-sig")

    summary={"generated_at":pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat()}
    lpi_fc=None

    if "LPI" in d.columns:
        lpi_fc,lpi_diag=fit_forecast(d["LPI"],CFG["forecast_horizon_business_days"],CFG["min_daily_observations"])
    else:
        lpi_diag={"status":"NO_LPI"}
    summary["lpi"]=lpi_diag
    if lpi_fc is not None:
        last_date=pd.to_datetime(d["date"]).max()
        lpi_fc["date"]=pd.bdate_range(last_date+pd.offsets.BDay(1),periods=len(lpi_fc))
        lpi_fc["state"]=lpi_fc["forecast"].map(classify_lpi)
        lpi_fc.to_csv(OUT/"lpi_forecast.csv",index=False,encoding="utf-8-sig")

    ib_fc=None
    if "interbank_bronze" in d.columns:
        ib_fc,ib_diag=fit_forecast(d["interbank_bronze"],CFG["forecast_horizon_business_days"],CFG["min_daily_observations"])
    else:
        ib_diag={"status":"NO_INTERBANK_DATA"}
    summary["interbank"]=ib_diag
    if ib_fc is not None:
        last_date=pd.to_datetime(d["date"]).max()
        ib_fc["date"]=pd.bdate_range(last_date+pd.offsets.BDay(1),periods=len(ib_fc))
        ib_fc.to_csv(OUT/"interbank_forecast.csv",index=False,encoding="utf-8-sig")

    regimes,regime_diag=regime_model(d) if "LPI" in d.columns else (pd.DataFrame(),{"status":"NO_LPI"})
    summary["regime"]=regime_diag
    if len(regimes):
        regimes.to_csv(OUT/"regime_probabilities.csv",index=False,encoding="utf-8-sig")

    drivers=driver_table(d)
    drivers.to_csv(OUT/"drivers.csv",index=False,encoding="utf-8-sig")

    var_fc,var_diag=monthly_var()
    summary["var"]=var_diag
    if len(var_fc):
        var_fc.to_csv(OUT/"monthly_var_forecast.csv",index=False,encoding="utf-8-sig")

    banks=bank_stress(lpi_fc)
    banks.to_csv(OUT/"bank_stress_forecast.csv",index=False,encoding="utf-8-sig")

    # Diagnostics table
    diag_rows=[]
    for target,diag in [("LPI",lpi_diag),("Interbank ON",ib_diag),("Liquidity Regime",regime_diag),("Monthly VAR",var_diag)]:
        diag_rows.append([
            target,diag.get("status",""),diag.get("model",""),diag.get("nobs",""),
            diag.get("rmse",""),diag.get("naive_rmse",""),diag.get("skill_vs_naive",""),
            diag.get("aic",""),diag.get("bic","")
        ])
    pd.DataFrame(diag_rows,columns=["Target","Status","Model","Observations","RMSE","Naive RMSE","Skill vs Naive","AIC","BIC"]).to_csv(
        OUT/"model_diagnostics.csv",index=False,encoding="utf-8-sig")

    # Explanation object driven by actual model outputs.
    last_lpi=float(d["LPI"].dropna().iloc[-1]) if "LPI" in d and d["LPI"].notna().any() else None
    fc5=float(lpi_fc.iloc[4]["forecast"]) if lpi_fc is not None and len(lpi_fc)>=5 else None
    fc20=float(lpi_fc.iloc[19]["forecast"]) if lpi_fc is not None and len(lpi_fc)>=20 else None
    top_drivers=drivers.head(3).to_dict("records") if len(drivers) else []

    explanation={
        "current_lpi":last_lpi,
        "current_state":classify_lpi(last_lpi),
        "forecast_5d":fc5,
        "forecast_20d":fc20,
        "forecast_5d_state":classify_lpi(fc5),
        "forecast_20d_state":classify_lpi(fc20),
        "selected_model":lpi_diag.get("model"),
        "why_model":"Mô hình được chọn theo RMSE ngoài mẫu thấp nhất trong nhóm ARIMA ứng viên; benchmark là dự báo giữ nguyên giá trị gần nhất.",
        "top_drivers":top_drivers,
        "confidence":"Độ tin cậy được đánh giá bằng rolling holdout RMSE, skill so với naive benchmark và dải dự báo 80%/95%.",
        "so_what":"LPI tăng hàm ý funding pressure cao hơn, lãi suất liên ngân hàng và chi phí vốn ngân hàng có rủi ro tăng; ngân hàng LDR cao/CASA thấp nhạy cảm hơn.",
        "caveats":"Dự báo phụ thuộc độ đầy đủ của OMO, interbank và FX. Nếu interbank bị 404 hoặc chuỗi tháng thiếu, app sẽ hạ confidence và không tự tạo lịch sử giả."
    }
    (OUT/"explanation.json").write_text(json.dumps(explanation,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"model_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

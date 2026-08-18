
from pathlib import Path
import pandas as pd, numpy as np, json, warnings
warnings.filterwarnings("ignore")
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"; OUT=DATA/"model_outputs"; OUT.mkdir(parents=True,exist_ok=True)
CFG=json.loads((ROOT/"config/model_config.json").read_text(encoding="utf-8"))

def load(path):
    p=Path(path)
    try:return pd.read_csv(p)
    except:return pd.DataFrame()

def date_col(df):
    for c in ["date","time","period","datetime","report_time"]:
        if c in df.columns:return c
    return None

def numeric_col(df,cands):
    if df.empty:return None
    low={str(c).lower():c for c in df.columns}
    for cand in cands:
        for k,c in low.items():
            if cand.lower()==k or cand.lower() in k:return c
    best=None; n=-1
    for c in df.columns:
        z=pd.to_numeric(df[c],errors="coerce").notna().sum()
        if z>n:n=z;best=c
    return best if n>5 else None

def ts_from_file(path,label,cands):
    df=load(path)
    if df.empty:return pd.DataFrame()
    dc=date_col(df); vc=numeric_col(df,cands)
    if not dc or not vc:return pd.DataFrame()
    x=df[[dc,vc]].copy(); x.columns=["date",label]
    x["date"]=pd.to_datetime(x["date"],errors="coerce")
    x[label]=pd.to_numeric(x[label],errors="coerce")
    return x.dropna().sort_values("date").drop_duplicates("date",keep="last")

def interbank_series():
    # Priority: Bronze actual -> manual/public actual.
    x=ts_from_file(DATA/"interbank_bronze.csv","interbank",["overnight","o/n","on","qua đêm","rate","value"])
    if len(x): return x,"BRONZE"
    m=load(DATA/"interbank_manual.csv")
    if len(m):
        dc=date_col(m) or "date"
        vc=numeric_col(m,["overnight_rate","overnight","o/n","on"])
        if dc in m.columns and vc:
            x=m[[dc,vc]].copy(); x.columns=["date","interbank"]
            x["date"]=pd.to_datetime(x["date"],errors="coerce")
            x["interbank"]=pd.to_numeric(x["interbank"],errors="coerce")
            return x.dropna().sort_values("date").drop_duplicates("date",keep="last"),"MANUAL_ACTUAL"
    return pd.DataFrame(),"NONE"

def zscore(s,w):
    mu=s.rolling(w,min_periods=max(15,w//3)).mean()
    sd=s.rolling(w,min_periods=max(15,w//3)).std()
    return (s-mu)/sd.replace(0,np.nan)

def build_daily():
    parts=[]
    omo=ts_from_file(DATA/"omo_bronze.csv","omo",["netflow_amount","netflow","net flow","net","value"])
    fx=ts_from_file(DATA/"fx_bronze.csv","fx",["usd","usd_vnd","close","sell","value"])
    ib,ib_src=interbank_series()
    if len(omo):parts.append(omo)
    if len(fx):parts.append(fx)
    if len(ib):parts.append(ib)
    if not parts:return pd.DataFrame(),ib_src
    d=parts[0]
    for p in parts[1:]:d=d.merge(p,on="date",how="outer")
    d=d.sort_values("date").set_index("date").asfreq("B")
    if "omo" in d:d["OMO_z"]=-zscore(d["omo"],CFG["z_window"])
    if "fx" in d:
        d["fx"]=d["fx"].ffill(limit=3)
        d["FX_z"]=zscore(np.log(d["fx"]).diff(5),CFG["z_window"])
    if "interbank" in d:
        d["interbank"]=d["interbank"].ffill(limit=3)
        d["ON_z"]=zscore(d["interbank"],CFG["z_window"])
    comps=[c for c in ["ON_z","FX_z","OMO_z"] if c in d.columns]
    d["LPI_components"]=d[comps].notna().sum(axis=1)
    d["LPI"]=d[comps].mean(axis=1,skipna=True)
    d.loc[d["LPI_components"]<CFG["lpi_min_components"],"LPI"]=np.nan
    return d.reset_index(),ib_src

def fit(y,h=20):
    y=pd.Series(y).dropna().astype(float)
    if len(y)<CFG["min_daily_observations"]:
        return pd.DataFrame(),{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":len(y)}
    test_n=min(CFG["backtest_days"],max(10,len(y)//5))
    tr=y.iloc[:-test_n]; te=y.iloc[-test_n:]
    choices=[("ARIMA(1,0,0)",(1,0,0)),("ARIMA(2,0,0)",(2,0,0)),("ARIMA(1,1,0)",(1,1,0)),("ARIMA(0,1,1)",(0,1,1))]
    scored=[]
    for name,order in choices:
        try:
            m=SARIMAX(tr,order=order,trend="c" if order[1]==0 else "n",enforce_stationarity=False,enforce_invertibility=False).fit(disp=False)
            pred=m.get_forecast(len(te)).predicted_mean
            rmse=float(mean_squared_error(te,pred)**.5)
            scored.append((rmse,name,order,float(mean_absolute_error(te,pred))))
        except:pass
    if not scored:return pd.DataFrame(),{"status":"MODEL_FIT_FAILED","nobs":len(y)}
    scored.sort(); rmse,name,order,mae=scored[0]
    naive=float(mean_squared_error(te,np.repeat(tr.iloc[-1],len(te)))**.5)
    final=SARIMAX(y,order=order,trend="c" if order[1]==0 else "n",enforce_stationarity=False,enforce_invertibility=False).fit(disp=False)
    fc=final.get_forecast(h); ci80=fc.conf_int(alpha=.20); ci95=fc.conf_int(alpha=.05)
    out=pd.DataFrame({
        "horizon":range(1,h+1),"forecast":fc.predicted_mean.values,
        "p10":ci80.iloc[:,0].values,"p90":ci80.iloc[:,1].values,
        "p025":ci95.iloc[:,0].values,"p975":ci95.iloc[:,1].values})
    diag={"status":"OK","model":name,"nobs":len(y),"rmse":rmse,"mae":mae,"naive_rmse":naive,
          "skill_vs_naive":1-rmse/naive if naive>0 else None,"aic":float(final.aic),"bic":float(final.bic)}
    return out,diag

def regime(d):
    x=d[["date","LPI"]].dropna()
    if len(x)<CFG["min_markov_observations"]:return pd.DataFrame(),{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":len(x)}
    try:
        r=MarkovRegression(x["LPI"],k_regimes=3,trend="c",switching_variance=True).fit(disp=False,maxiter=250)
        p=r.smoothed_marginal_probabilities
        means=[(k,float(np.average(x["LPI"],weights=p[k]))) for k in range(3)]
        order=[k for k,_ in sorted(means,key=lambda z:z[1])]
        out=pd.DataFrame({"date":x["date"].values,
                          "P_Excess_raw":p[order[0]].values,"P_Neutral_raw":p[order[1]].values,"P_Stress_raw":p[order[2]].values})
        for src,dst in [("P_Excess_raw","P_Excess"),("P_Neutral_raw","P_Neutral"),("P_Stress_raw","P_Stress")]:
            out[dst]=out[src].rolling(20,min_periods=1).mean()
        den=out[["P_Excess","P_Neutral","P_Stress"]].sum(axis=1)
        for c in ["P_Excess","P_Neutral","P_Stress"]:out[c]=out[c]/den
        return out,{"status":"OK","nobs":len(x),"aic":float(r.aic)}
    except Exception as e:return pd.DataFrame(),{"status":"ERROR","message":str(e),"nobs":len(x)}

def bank_stress(lpi_fc):
    actual=load(DATA/"bank_actuals_bronze.csv")
    fallback=load(DATA/"bank_fallback_assumptions.csv"); fallback = fallback if len(fallback) else load(ROOT/"config/bank_fallback_assumptions.csv")
    metrics=["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]
    if len(actual):
        a=actual.copy()
        for c in metrics:a[c]=pd.to_numeric(a.get(c),errors="coerce")
        a["Coverage"]=a[metrics].notna().mean(axis=1)
        useful=a[a["Coverage"]>=CFG["bank_actual_min_coverage"]].copy()
    else: useful=pd.DataFrame()
    if fallback.empty:
        return pd.DataFrame()
    missing=fallback[~fallback["Ticker"].isin(useful["Ticker"])] if len(useful) else fallback.copy()
    bank=pd.concat([useful,missing],ignore_index=True) if len(useful) else missing
    for c in metrics:
        bank[c]=pd.to_numeric(bank[c],errors="coerce")
        bank[c]=np.where(abs(bank[c])>2,bank[c]/100,bank[c])
    bank["Coverage"]=bank[metrics].notna().mean(axis=1)
    bank["LiquidityBuffer"]=1-bank["LDR"]
    bank["BaseVulnerability"]=(50+35*(bank.LDR-.85)-25*(bank.CASA-.20)+45*bank.InterbankDep+
                               30*bank.CreditDepositGap-10*(bank.NIM-.03)-20*(bank.LiquidityBuffer-.15)).clip(0,100)
    bank.loc[bank["Coverage"]<.60,"BaseVulnerability"]=np.nan
    scenarios=[("Current",0.0)]
    if len(lpi_fc)>=5:scenarios.append(("5D",float(lpi_fc.iloc[4].forecast)))
    if len(lpi_fc)>=20:scenarios.append(("20D",float(lpi_fc.iloc[19].forecast)))
    out=[]
    for h,lpi in scenarios:
        t=bank.copy(); t["Horizon"]=h; t["LPI"]=lpi
        t["StressVulnerability"]=(t.BaseVulnerability*(1+CFG["bank_stress_beta_per_lpi"]*max(lpi,0))).clip(0,100)
        t["FundingCostShock_ppt"]=2*t.StressVulnerability/100
        t["StressedNIM"]=np.maximum(0,t.NIM-t.FundingCostShock_ppt/100)
        t["Watch"]=np.select([(t.StressVulnerability>=75)|(t.StressedNIM<.02),t.StressVulnerability>=60],["RED","AMBER"],default="GREEN")
        out.append(t[["Ticker","Horizon","LPI","BaseVulnerability","StressVulnerability","FundingCostShock_ppt","StressedNIM","Watch","Coverage","Data Type","Source Mode"]])
    return pd.concat(out,ignore_index=True)

def main():
    d,ib_src=build_daily(); d.to_csv(OUT/"daily_liquidity_panel.csv",index=False,encoding="utf-8-sig")
    lpi_fc,lpi_diag=fit(d["LPI"]) if "LPI" in d else (pd.DataFrame(),{"status":"NO_LPI"})
    if len(lpi_fc):
        last=pd.to_datetime(d.date).max()
        lpi_fc["date"]=pd.bdate_range(last+pd.offsets.BDay(1),periods=len(lpi_fc))
        lpi_fc.to_csv(OUT/"lpi_forecast.csv",index=False,encoding="utf-8-sig")
    ib_fc,ib_diag=fit(d["interbank"]) if "interbank" in d else (pd.DataFrame(),{"status":"NO_INTERBANK_DATA"})
    ib_diag["source"]=ib_src
    if len(ib_fc):
        last=pd.to_datetime(d.date).max()
        ib_fc["date"]=pd.bdate_range(last+pd.offsets.BDay(1),periods=len(ib_fc))
        ib_fc.to_csv(OUT/"interbank_forecast.csv",index=False,encoding="utf-8-sig")
    reg,reg_diag=regime(d) if "LPI" in d else (pd.DataFrame(),{"status":"NO_LPI"})
    if len(reg):reg.to_csv(OUT/"regime_probabilities.csv",index=False,encoding="utf-8-sig")
    b=bank_stress(lpi_fc); b.to_csv(OUT/"bank_stress_forecast.csv",index=False,encoding="utf-8-sig")
    diag=pd.DataFrame([
        ["LPI",lpi_diag.get("status"),lpi_diag.get("model"),lpi_diag.get("nobs"),lpi_diag.get("rmse"),lpi_diag.get("naive_rmse"),lpi_diag.get("skill_vs_naive"),lpi_diag.get("aic"),lpi_diag.get("bic")],
        ["Interbank ON",ib_diag.get("status"),ib_diag.get("model"),ib_diag.get("nobs"),ib_diag.get("rmse"),ib_diag.get("naive_rmse"),ib_diag.get("skill_vs_naive"),ib_diag.get("aic"),ib_diag.get("bic")],
        ["Liquidity Regime",reg_diag.get("status"),None,reg_diag.get("nobs"),None,None,None,reg_diag.get("aic"),None],
    ],columns=["Target","Status","Model","Observations","RMSE","Naive RMSE","Skill vs Naive","AIC","BIC"])
    diag.to_csv(OUT/"model_diagnostics.csv",index=False,encoding="utf-8-sig")
    summary={"lpi":lpi_diag,"interbank":ib_diag,"regime":reg_diag,"interbank_source":ib_src,
             "generated_at":pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat()}
    (OUT/"model_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":main()


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
    try:return pd.read_csv(path)
    except:return pd.DataFrame()

def date_col(df):
    for c in ["date","time","period","datetime","report_time"]:
        if c in df.columns:return c
    return None

def numeric_col(df,cands):
    if df.empty:return None
    for cand in cands:
        for c in df.columns:
            if cand.lower()==str(c).lower() or cand.lower() in str(c).lower():return c
    best=None;n=-1
    for c in df.columns:
        k=pd.to_numeric(df[c],errors="coerce").notna().sum()
        if k>n:best,n=c,k
    return best if n>5 else None

def ts(path,label,cands):
    df=load(path)
    if df.empty:return pd.DataFrame()
    dc=date_col(df);vc=numeric_col(df,cands)
    if not dc or not vc:return pd.DataFrame()
    x=df[[dc,vc]].copy();x.columns=["date",label]
    x["date"]=pd.to_datetime(x.date,errors="coerce")
    x[label]=pd.to_numeric(x[label],errors="coerce")
    return x.dropna().sort_values("date").drop_duplicates("date",keep="last")

def interbank_series():
    x=ts(DATA/"interbank_bronze.csv","interbank",["overnight_rate","overnight","qua đêm","o/n","on","rate","value"])
    if len(x):return x,"BRONZE"
    m=load(DATA/"interbank_manual.csv")
    if len(m):
        dc=date_col(m) or ("date" if "date" in m.columns else None)
        vc=numeric_col(m,["overnight_rate","overnight","o/n","on"])
        if dc and vc:
            x=m[[dc,vc]].copy();x.columns=["date","interbank"]
            x["date"]=pd.to_datetime(x.date,errors="coerce")
            x["interbank"]=pd.to_numeric(x.interbank,errors="coerce")
            x=x.dropna().sort_values("date").drop_duplicates("date",keep="last")
            if len(x):return x,"MANUAL_ACTUAL"
    return pd.DataFrame(),"NONE"

def z(s,w):
    mu=s.rolling(w,min_periods=max(15,w//3)).mean()
    sd=s.rolling(w,min_periods=max(15,w//3)).std()
    return (s-mu)/sd.replace(0,np.nan)

def daily_panel():
    parts=[]
    omo=ts(DATA/"omo_bronze.csv","omo",["netflow_amount","netflow","net flow","net","value"])
    fx=ts(DATA/"fx_bronze.csv","fx",["usd","usd_vnd","close","sell","value"])
    ib,ib_src=interbank_series()
    if len(omo):parts.append(omo)
    if len(fx):parts.append(fx)
    if len(ib):parts.append(ib)
    if not parts:return pd.DataFrame(),ib_src
    d=parts[0]
    for p in parts[1:]:d=d.merge(p,on="date",how="outer")
    d=d.sort_values("date").set_index("date").asfreq("B")
    if "omo" in d:d["OMO_z"]=-z(d.omo,CFG["z_window"])
    if "fx" in d:
        d["fx"]=d.fx.ffill(limit=3)
        d["FX_z"]=z(np.log(d.fx).diff(5),CFG["z_window"])
    if "interbank" in d:
        d["interbank"]=d.interbank.ffill(limit=3)
        d["ON_z"]=z(d.interbank,CFG["z_window"])
    comps=[c for c in ["ON_z","FX_z","OMO_z"] if c in d.columns]
    d["LPI_components"]=d[comps].notna().sum(axis=1)
    d["LPI"]=d[comps].mean(axis=1,skipna=True)
    d.loc[d.LPI_components<CFG["lpi_min_components"],"LPI"]=np.nan
    return d.reset_index(),ib_src

def forecast_select(y,h=20):
    raw=pd.to_numeric(pd.Series(y),errors="coerce").dropna().astype(float).values
    y=pd.Series(raw,index=pd.RangeIndex(len(raw)),dtype=float)
    if len(y)<CFG["min_daily_observations"]:
        return pd.DataFrame(),{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":len(y),"publishable":False}

    test_n=min(CFG["backtest_days"],max(10,len(y)//5))
    tr=y.iloc[:-test_n].copy()
    te=y.iloc[-test_n:].copy()
    tr.index=pd.RangeIndex(len(tr))
    te.index=pd.RangeIndex(len(te))

    naive=np.repeat(float(tr.iloc[-1]),len(te))
    naive_rmse=float(mean_squared_error(te.values,naive)**.5)
    naive_mae=float(mean_absolute_error(te.values,naive))
    scored=[]

    for name,order in [
        ("ARIMA(1,0,0)",(1,0,0)),
        ("ARIMA(2,0,0)",(2,0,0)),
        ("ARIMA(1,1,0)",(1,1,0)),
        ("ARIMA(0,1,1)",(0,1,1))
    ]:
        try:
            model=SARIMAX(
                tr,order=order,trend="c" if order[1]==0 else "n",
                enforce_stationarity=False,enforce_invertibility=False
            ).fit(disp=False)
            pred=np.asarray(model.get_forecast(len(te)).predicted_mean,dtype=float)
            scored.append((
                float(mean_squared_error(te.values,pred)**.5),
                float(mean_absolute_error(te.values,pred)),
                name,order
            ))
        except Exception:
            pass

    best=min(scored,key=lambda x:x[0]) if scored else None

    if best is None or best[0]>=naive_rmse:
        sigma=float(pd.Series(raw).diff().dropna().std())
        hs=np.arange(1,h+1)
        last=float(raw[-1])
        se=sigma*np.sqrt(hs)
        out=pd.DataFrame({
            "horizon":hs,"forecast":last,
            "p10":last-1.2816*se,"p90":last+1.2816*se,
            "p025":last-1.96*se,"p975":last+1.96*se
        })
        diag={
            "status":"OK_BENCHMARK","model":"NAIVE_RANDOM_WALK","nobs":len(y),
            "rmse":naive_rmse,"mae":naive_mae,"naive_rmse":naive_rmse,
            "skill_vs_naive":0.0,"confidence_grade":"LOW",
            "governance_note":"No ARIMA candidate beat naive holdout RMSE; benchmark selected."
        }
        if best:
            diag.update({"best_arima":best[2],"best_arima_rmse":best[0]})
        return out,diag

    rmse,mae,name,order=best
    final=SARIMAX(
        y,order=order,trend="c" if order[1]==0 else "n",
        enforce_stationarity=False,enforce_invertibility=False
    ).fit(disp=False)
    fc=final.get_forecast(h)
    ci80=fc.conf_int(alpha=.20); ci95=fc.conf_int(alpha=.05)
    out=pd.DataFrame({
        "horizon":range(1,h+1),
        "forecast":np.asarray(fc.predicted_mean,dtype=float),
        "p10":np.asarray(ci80.iloc[:,0],dtype=float),
        "p90":np.asarray(ci80.iloc[:,1],dtype=float),
        "p025":np.asarray(ci95.iloc[:,0],dtype=float),
        "p975":np.asarray(ci95.iloc[:,1],dtype=float)
    })
    skill=1-rmse/naive_rmse if naive_rmse>0 else None
    grade="HIGH" if skill is not None and skill>=.20 else "MEDIUM" if skill is not None and skill>=.05 else "LOW"
    return out,{
        "status":"OK","model":name,"nobs":len(y),
        "rmse":rmse,"mae":mae,"naive_rmse":naive_rmse,
        "skill_vs_naive":skill,"aic":float(final.aic),"bic":float(final.bic),
        "confidence_grade":grade,
        "governance_note":"ARIMA beat naive holdout RMSE."
    }

def regimes(d):
    x=d[["date","LPI"]].dropna().copy()
    if len(x)<CFG["min_markov_observations"]:
        return pd.DataFrame(),{"status":"INSUFFICIENT_ACTUAL_HISTORY","nobs":len(x)}
    try:
        dates=pd.to_datetime(x["date"],errors="coerce").reset_index(drop=True)
        y=pd.Series(pd.to_numeric(x["LPI"],errors="coerce").values,index=pd.RangeIndex(len(x)),dtype=float)
        fit=MarkovRegression(y,k_regimes=3,trend="c",switching_variance=True).fit(disp=False,maxiter=250)
        p=fit.smoothed_marginal_probabilities
        means=[(k,float(np.average(x.LPI,weights=p[k]))) for k in range(3)]
        order=[k for k,_ in sorted(means,key=lambda z:z[1])]
        out=pd.DataFrame({"date":dates.values,"P_Excess_raw":p[order[0]].values,
                          "P_Neutral_raw":p[order[1]].values,"P_Stress_raw":p[order[2]].values})
        for s,dst in [("P_Excess_raw","P_Excess"),("P_Neutral_raw","P_Neutral"),("P_Stress_raw","P_Stress")]:
            out[dst]=out[s].rolling(20,min_periods=1).mean()
        den=out[["P_Excess","P_Neutral","P_Stress"]].sum(axis=1)
        for c in ["P_Excess","P_Neutral","P_Stress"]:out[c]=out[c]/den
        return out,{"status":"OK","nobs":len(x),"aic":float(fit.aic)}
    except Exception as e:return pd.DataFrame(),{"status":"ERROR","message":str(e),"nobs":len(x)}

def compute_bank_base():
    actual=load(DATA/"bank_actuals_bronze.csv")
    fallback=load(ROOT/"config/bank_fallback_assumptions.csv")
    metrics=["LDR","CASA","InterbankDep","CreditDepositGap","NIM"]

    if fallback.empty:
        return pd.DataFrame()

    fb=fallback.copy()
    for c in metrics:
        fb[c]=pd.to_numeric(fb[c],errors="coerce")

    if actual.empty:
        bank=fb.copy()
        bank["ActualMetricCount"]=0
        bank["MetricCoverage"]=0.0
        bank["Data Type"]="ASSUMPTION"
        bank["Source Mode"]="FALLBACK"
    else:
        a=actual.copy()
        if "Ticker" not in a.columns:
            a=pd.DataFrame()
        for c in metrics:
            if c not in a.columns:
                a[c]=np.nan
            a[c]=pd.to_numeric(a[c],errors="coerce")

        if len(a):
            a=a.drop_duplicates("Ticker",keep="last").set_index("Ticker")
        fb2=fb.drop_duplicates("Ticker",keep="last").set_index("Ticker")
        out=[]

        for ticker,rowfb in fb2.iterrows():
            row={"Ticker":ticker}
            actual_count=0
            if len(a) and ticker in a.index:
                ra=a.loc[ticker]
            else:
                ra=None

            for c in metrics:
                va=ra[c] if ra is not None and c in ra.index else np.nan
                if pd.notna(va):
                    row[c]=float(va); actual_count+=1
                else:
                    row[c]=float(rowfb[c])

            row["ActualMetricCount"]=actual_count
            row["MetricCoverage"]=actual_count/len(metrics)
            if actual_count==len(metrics):
                row["Data Type"]="ACTUAL"; row["Source Mode"]="BRONZE"
            elif actual_count>0:
                row["Data Type"]="MIXED"; row["Source Mode"]="HYBRID"
            else:
                row["Data Type"]="ASSUMPTION"; row["Source Mode"]="FALLBACK"
            out.append(row)

        bank=pd.DataFrame(out)

    # Normalize ratios if API reports percentages 0-100.
    for c in metrics:
        bank[c]=pd.to_numeric(bank[c],errors="coerce")
        bank[c]=np.where(abs(bank[c])>2,bank[c]/100,bank[c])

    bank["Coverage"]=pd.to_numeric(bank["MetricCoverage"],errors="coerce").fillna(0)
    bank["LiquidityBuffer"]=1-bank["LDR"]
    bank["BaseVulnerability"]=(
        50
        +35*(bank["LDR"]-.85)
        -25*(bank["CASA"]-.20)
        +45*bank["InterbankDep"]
        +30*bank["CreditDepositGap"]
        -10*(bank["NIM"]-.03)
        -20*(bank["LiquidityBuffer"]-.15)
    ).clip(0,100)

    return bank

def bank_stress(lpi_fc):
    bank=compute_bank_base()
    scenarios=[("Current",0.0)]
    if len(lpi_fc)>=5:scenarios.append(("5D",float(lpi_fc.iloc[4].forecast)))
    if len(lpi_fc)>=20:scenarios.append(("20D",float(lpi_fc.iloc[19].forecast)))
    out=[]
    for h,lpi in scenarios:
        t=bank.copy();t["Horizon"]=h;t["LPI"]=lpi
        t["StressVulnerability"]=(t.BaseVulnerability*(1+CFG["bank_stress_beta_per_lpi"]*max(lpi,0))).clip(0,100)
        t["FundingCostShock_ppt"]=2*t.StressVulnerability/100
        t["StressedNIM"]=np.maximum(0,t.NIM-t.FundingCostShock_ppt/100)
        t["Watch"]=np.select([(t.StressVulnerability>=CFG["red_threshold"])|(t.StressedNIM<CFG["nim_red_threshold"]),
                              t.StressVulnerability>=CFG["amber_threshold"]],["RED","AMBER"],default="GREEN")
        out.append(t[[
            "Ticker","Horizon","LPI","LDR","CASA","InterbankDep","CreditDepositGap","NIM",
            "ActualMetricCount","MetricCoverage","BaseVulnerability","StressVulnerability",
            "FundingCostShock_ppt","StressedNIM","Watch","Coverage","Data Type","Source Mode"
        ]])
    return pd.concat(out,ignore_index=True)

def main():
    d,ib_src=daily_panel();d.to_csv(OUT/"daily_liquidity_panel.csv",index=False,encoding="utf-8-sig")
    lpi_fc,lpi_diag=forecast_select(d.LPI) if "LPI" in d else (pd.DataFrame(),{"status":"NO_LPI"})
    if len(lpi_fc):
        last=pd.to_datetime(d.date).max();lpi_fc["date"]=pd.bdate_range(last+pd.offsets.BDay(1),periods=len(lpi_fc))
        lpi_fc.to_csv(OUT/"lpi_forecast.csv",index=False,encoding="utf-8-sig")

    ib_fc,ib_diag=forecast_select(d.interbank) if "interbank" in d else (pd.DataFrame(),{"status":"NO_INTERBANK_DATA"})
    ib_diag["source"]=ib_src
    if len(ib_fc):
        last=pd.to_datetime(d.date).max();ib_fc["date"]=pd.bdate_range(last+pd.offsets.BDay(1),periods=len(ib_fc))
        ib_fc.to_csv(OUT/"interbank_forecast.csv",index=False,encoding="utf-8-sig")

    reg,reg_diag=regimes(d) if "LPI" in d else (pd.DataFrame(),{"status":"NO_LPI"})
    if len(reg):reg.to_csv(OUT/"regime_probabilities.csv",index=False,encoding="utf-8-sig")

    bank=bank_stress(lpi_fc);bank.to_csv(OUT/"bank_stress_forecast.csv",index=False,encoding="utf-8-sig")

    current_bank=bank[bank.Horizon=="Current"].copy()
    bank_diag=pd.DataFrame([{
        "bank_universe":bank.Ticker.nunique(),
        "bronze_full_tickers":int((current_bank["Source Mode"]=="BRONZE").sum()),
        "hybrid_tickers":int((current_bank["Source Mode"]=="HYBRID").sum()),
        "fallback_tickers":int((current_bank["Source Mode"]=="FALLBACK").sum()),
        "actual_metric_fields":int(
            pd.to_numeric(
                current_bank["ActualMetricCount"] if "ActualMetricCount" in current_bank.columns else pd.Series(0,index=current_bank.index),
                errors="coerce"
            ).fillna(0).sum()
        ),
        "valid_base":int(current_bank.BaseVulnerability.notna().sum())
    }])
    bank_diag.to_csv(OUT/"bank_stress_diagnostics.csv",index=False,encoding="utf-8-sig")

    diag=pd.DataFrame([
        ["LPI",lpi_diag.get("status"),lpi_diag.get("model"),lpi_diag.get("nobs"),lpi_diag.get("rmse"),lpi_diag.get("naive_rmse"),lpi_diag.get("skill_vs_naive"),lpi_diag.get("confidence_grade"),lpi_diag.get("governance_note")],
        ["Interbank ON",ib_diag.get("status"),ib_diag.get("model"),ib_diag.get("nobs"),ib_diag.get("rmse"),ib_diag.get("naive_rmse"),ib_diag.get("skill_vs_naive"),ib_diag.get("confidence_grade"),ib_diag.get("governance_note")],
        ["Liquidity Regime",reg_diag.get("status"),None,reg_diag.get("nobs"),None,None,None,None,None],
    ],columns=["Target","Status","Model","Observations","RMSE","Naive RMSE","Skill vs Naive","Confidence","Governance Note"])
    diag.to_csv(OUT/"model_diagnostics.csv",index=False,encoding="utf-8-sig")
    summary={"lpi":lpi_diag,"interbank":ib_diag,"regime":reg_diag,"interbank_source":ib_src,
             "bank_stress":{
            "valid_base":int(bank[bank.Horizon=="Current"].BaseVulnerability.notna().sum()),
            "bronze_full_tickers":int((bank[bank.Horizon=="Current"]["Source Mode"]=="BRONZE").sum()),
            "hybrid_tickers":int((bank[bank.Horizon=="Current"]["Source Mode"]=="HYBRID").sum()),
            "fallback_tickers":int((bank[bank.Horizon=="Current"]["Source Mode"]=="FALLBACK").sum())
        },
             "generated_at":pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").isoformat()}
    (OUT/"model_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":main()

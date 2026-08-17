
from pathlib import Path
import numpy as np, pandas as pd

ROOT=Path(__file__).parent; DATA=ROOT/"data"

def read_actuals():
    p=DATA/"bank_actuals.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def frac(x):
    x=pd.to_numeric(x,errors="coerce")
    # Some ratio APIs may expose percentages as 85 rather than .85
    return np.where(np.abs(x)>2,x/100.0,x)

def score(df, stress_multiplier=1.35, max_funding_pass=2.0):
    if df.empty: return df
    d=df.copy()
    for c in ["LDR Proxy","CASA Proxy","NIM","Total Assets","Interbank Borrowing","Customer Loans","Customer Deposits"]:
        if c in d: d[c]=pd.to_numeric(d[c],errors="coerce")
    d["LDR"]=frac(d["LDR Proxy"])
    d["CASA"]=frac(d["CASA Proxy"])
    d["NIM_f"]=frac(d["NIM"])
    d["InterbankDep"]=d["Interbank Borrowing"]/d["Total Assets"]
    d["CreditDepositGap"]=(d["Customer Loans"]-d["Customer Deposits"])/d["Customer Deposits"]
    d["LiquidityBuffer"]=1-d["LDR"]
    metrics=["LDR","CASA","InterbankDep","CreditDepositGap","NIM_f","LiquidityBuffer"]
    d["DataCoverage"]=d[metrics].notna().mean(axis=1)
    raw=(50
         +35*(d["LDR"]-.85)
         -25*(d["CASA"]-.20)
         +45*d["InterbankDep"]
         +30*d["CreditDepositGap"]
         -10*(d["NIM_f"]-.03)
         -20*(d["LiquidityBuffer"]-.15))
    d["BaseVulnerability"]=raw.clip(0,100)
    d.loc[d["DataCoverage"]<.5,"BaseVulnerability"]=np.nan
    d["StressVulnerability"]=(d["BaseVulnerability"]*stress_multiplier).clip(0,100)
    d["FundingCostShock_ppt"]=max_funding_pass*d["StressVulnerability"]/100
    d["StressedNIM"]=np.maximum(0,d["NIM_f"]-d["FundingCostShock_ppt"]/100)
    d["WatchFlag"]=np.select(
        [(d["StressVulnerability"]>=75)|(d["StressedNIM"]<.02),d["StressVulnerability"]>=60],
        ["RED","AMBER"],default="GREEN")
    d["Rank"]=d["StressVulnerability"].rank(ascending=False,method="min")
    cols=["Ticker","Period","LDR","CASA","InterbankDep","CreditDepositGap","NIM_f","LiquidityBuffer",
          "DataCoverage","BaseVulnerability","StressVulnerability","FundingCostShock_ppt","StressedNIM","WatchFlag","Rank"]
    return d[cols].sort_values(["StressVulnerability","Ticker"],ascending=[False,True])

if __name__=="__main__":
    out=score(read_actuals())
    out.to_csv(DATA/"bank_stress.csv",index=False,encoding="utf-8-sig")
    print(out)


from pathlib import Path
from datetime import datetime
import pandas as pd,time

DATA=Path(__file__).parent/"data"; DATA.mkdir(exist_ok=True)

def save(df,name):
    if df is None or len(df)==0:return
    x=df.copy()
    x["data_type"]="ACTUAL"
    x["retrieved_at"]=datetime.now().astimezone().isoformat(timespec="seconds")
    x.to_csv(DATA/f"{name}.csv",index=False,encoding="utf-8-sig")

def main():
    from vnstock_data import Macro
    m=Macro()
    jobs={
      "omo":lambda:m.currency().omo(start="2018-01-01"),
      "interbank":lambda:m.currency().interbank_rate(start="2018-01-01",period="day"),
      "fx":lambda:m.currency().exchange_rate(start="2018-01-01",period="day"),
      "policy_rate":lambda:m.currency().policy_rate(start="2018-01-01"),
      "m2":lambda:m.economy().money_supply(start="2012-01",period="month"),
      "credit":lambda:m.economy().credit(start="2012-01",period="month"),
      "cpi":lambda:m.economy().cpi(start="2012-01",period="month"),
      "budget":lambda:m.economy().state_budget(start="2012-01",period="month"),
    }
    status=[]
    for n,f in jobs.items():
        try:save(f(),n);status.append([n,"OK",""])
        except Exception as e:status.append([n,"ERROR",repr(e)])
        time.sleep(.15)
    pd.DataFrame(status,columns=["dataset","status","message"]).to_csv(DATA/"macro_refresh_status.csv",index=False,encoding="utf-8-sig")

if __name__=="__main__":main()

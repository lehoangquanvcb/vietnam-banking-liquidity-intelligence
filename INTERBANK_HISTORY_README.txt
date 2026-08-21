INTERBANK ON - GOVERNANCE

1. data/interbank.csv and data/interbank_history.csv contain ACTUAL observations only.
2. The system never fabricates daily ACTUAL observations by interpolation.
3. Vnstock Bronze may return sparse ON observations. With >=18 ACTUAL observations the model may publish an EXPLORATORY / LOW CONFIDENCE forecast.
4. Production threshold is 60 ACTUAL observations.
5. Every RUN_UPDATE_AND_PUSH.bat refresh appends and deduplicates ACTUAL history before rebuilding models.
6. Streamlit Cloud only reads repository data/model outputs; it does not call Vnstock at runtime.

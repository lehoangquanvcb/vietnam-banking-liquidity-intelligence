# V6.5 Stable Sponsor

## Fixes
- Sponsor installer is NEVER auto-run at startup.
- Explicit install/connect button only.
- API probe: maximum 3 banks / 12 seconds.
- Circuit breaker opens unless at least 2/3 probes return useful data.
- Full batch max wait 20 seconds.
- If Bronze and Free both fail, no more API calls during normal Streamlit reruns.
- Bronze counts only rows whose `Source Mode == BRONZE`.
- Arrow-safe dataframe rendering avoids mixed-object `pyarrow.ArrowInvalid`.
- Fallback remains clearly labelled ASSUMPTION.

## Streamlit Secret
Manage app -> Settings -> Secrets:
VNSTOCK_API_KEY = "YOUR_KEY"

## Deployment
Use app.py. Python 3.12 recommended.

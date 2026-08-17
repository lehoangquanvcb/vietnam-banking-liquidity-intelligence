# V6.5.1 Sponsor Hotfix

## Fix the current deployment error
V6.5.1 removes the cross-file `from sponsor_bootstrap import configure_key` dependency.
Sponsor bootstrap code is embedded directly in `app.py`, so stale `sponsor_bootstrap.py` cannot break deployment.

## Guest rate-limit safety
The Streamlit log showed Guest quota 20/20 requests/min.
Therefore FREE/GUEST mode now probes only the first 3 banks and NEVER calls the full 20-bank universe.
Only BRONZE mode may load the full 20-bank universe.

## Circuits
- Bronze probe: 3 banks / 12 seconds. Need 2 useful successes before full batch.
- Free probe: max 3 banks / 12 seconds, probe only.
- Failures open session circuit to prevent repeated API calls on every Streamlit rerun.
- Use the sidebar refresh button to explicitly retry.

## Secret
Streamlit Settings -> Secrets:
VNSTOCK_API_KEY = "YOUR_KEY"

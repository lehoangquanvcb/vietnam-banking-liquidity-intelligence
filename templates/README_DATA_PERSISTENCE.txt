PRODUCTION R3 IS CODE-ONLY.

KEEP your existing repository/data/ folder.

Copy/replace:
app.py
scripts/
config/
.github/
requirements.txt
requirements_local.txt
REFRESH_BRONZE*.bat
Vietnam_Banking_Liquidity_Master.xlsx
README.md
templates/

Then run REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat.

R3 guarantees Funding Stress / Stress Lab through:
1) model-build ticker fallback;
2) Streamlit runtime fallback.
All fallback rows remain labelled ASSUMPTION / FALLBACK.

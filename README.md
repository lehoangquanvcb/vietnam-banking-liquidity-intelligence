# Vietnam Banking Liquidity Intelligence — Production R2

## Upgrade safety
This package intentionally contains **NO `data/` directory**.

When upgrading, KEEP the repository's existing `data/` folder and replace only code/config/master files.

## Proven Bronze architecture
Persistent PC/self-hosted runner → `vnstock_data` Bronze → ACTUAL CSV → governed model outputs → GitHub → Streamlit Cloud.

Streamlit never installs/calls Sponsor.

## Fixes in R2
- No Streamlit `DeltaGenerator` objects are printed: all UI branches use explicit `if/else`.
- Bank stress always has a ticker-level fallback from `config/bank_fallback_assumptions.csv` when Bronze coverage <60%.
- Stress Lab uses valid `BaseVulnerability` rows only.
- ARIMA must beat naive benchmark on holdout RMSE. Otherwise production automatically publishes `NAIVE_RANDOM_WALK`, Confidence=LOW.
- True interbank only: never substitute deposit/lending rate proxy.
- Optional ACTUAL interbank input can be entered in the Master workbook. At least 10 valid rows with source URLs are required before `data/interbank_manual.csv` is overwritten.
- Bank parser prioritizes current `scorecard="banking"` Fundamental calls and stores raw financial tables for audit.

## Commands
After copying the code-only package (without deleting `data/`):
```
git add -A
git commit -m "Upgrade liquidity intelligence Production R2"
git push origin main
```

Then run:
`REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat`

## Interbank manual/public actual
Use the `INTERBANK_INPUT` sheet in the Master workbook:
- Date
- Overnight Rate (% p.a.)
- Source URL
- Source Name
- Data Type = ACTUAL

The BAT exports it only when at least 10 valid observations exist. It never overwrites an existing actual file with an empty template.

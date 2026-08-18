R8 IS CODE-ONLY. KEEP EXISTING data/.

R8 fixes:
- MultiIndex-safe Fundamental parsing.
- financial_health primary; balance_sheet/ratio failures isolated.
- MultiIndex-safe true interbank ON extraction, including Vietnamese đ normalization.
- MarkovRegression RangeIndex.
- Field-level HYBRID stress lineage retained.

After copying code, run REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat.

# Vietnam Banking Liquidity Intelligence — R8 MultiIndex-Safe Data Fix

R8 targets the exact errors observed in R7:

## 1. Bank Fundamental `isna is not defined for MultiIndex`
- `financial_health(scorecard="bank")` is now the primary bank-metric source.
- balance_sheet and ratio are isolated: one source failing cannot fail the whole ticker.
- All returned DataFrames are normalized through a MultiIndex-safe flattener.
- `drop_empty=False` was removed from production calls to avoid triggering problematic internal transformations.
- Bank stress remains field-level BRONZE / HYBRID / FALLBACK.

## 2. Interbank returned rows but parser found no ON
- R8 flattens MultiIndex index and columns before parsing.
- It scans text across all columns for `liên ngân hàng/interbank` + `Qua đêm/overnight`.
- It detects date and numeric rate columns dynamically.
- Request ladder remains 365 → 180 → 90 days.
- Deposit/lending rates are never renamed as ON.

## 3. Statsmodels warning
- SARIMAX already uses RangeIndex.
- R8 also gives MarkovRegression a clean RangeIndex, eliminating the remaining unsupported-index warning.

## Architecture
Local/self-hosted Vnstock Bronze → ACTUAL CSV/model outputs → GitHub → Streamlit read-only.

This package is CODE ONLY. Keep the existing `data/` folder.

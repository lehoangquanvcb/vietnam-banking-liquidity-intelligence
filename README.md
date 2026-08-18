# Vietnam Banking Liquidity Intelligence — Production R3

## Kiến trúc Bronze giữ nguyên
Persistent PC/self-hosted runner → `vnstock_data` Bronze → ACTUAL CSV → model outputs → GitHub → Streamlit Cloud.

Streamlit không cài hoặc gọi Sponsor.

## CODE ONLY
Package này không có `data/`. Khi nâng cấp, giữ nguyên thư mục `data/` hiện có.

## Sửa dứt điểm Stress
R3 có hai lớp bảo vệ:
1. `build_models.py` luôn tạo đủ universe từ `config/bank_fallback_assumptions.csv` nếu Bronze coverage <60%.
2. `app.py` tự tạo runtime fallback nếu `bank_stress_forecast.csv` cũ/rỗng/null.

Do đó Funding Stress và Stress Lab không còn được phép trống. Mọi fallback đều gắn nhãn `ASSUMPTION / FALLBACK`.

## Forecast governance
ARIMA chỉ được dùng nếu thắng naive benchmark trên holdout RMSE. Nếu không, dùng `NAIVE_RANDOM_WALK`, Confidence=LOW.

## Interbank
True interbank:
1. Bronze `interbank_rate()`;
2. `data/interbank_manual.csv` ACTUAL/public.

Funding-rate proxy được hiển thị riêng khi interbank thiếu, nhưng không dùng để forecast ON.

## Cách nâng cấp
GIỮ `data/`, copy code package, rồi:
```
git add -A
git commit -m "Upgrade liquidity intelligence Production R3"
git push origin main
```
Sau đó chạy:
`REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat`

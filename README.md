# Trung tâm Dự báo & Phân tích Thanh khoản Hệ thống Ngân hàng

Kiến trúc triển khai: Vnstock Bronze chạy trên máy local/self-hosted runner -> ghi dữ liệu ACTUAL và model outputs -> push GitHub -> Streamlit Cloud chỉ đọc repository.

## Chạy cập nhật
Chạy `RUN_UPDATE_AND_PUSH.bat` tại thư mục gốc dự án.

Pipeline sẽ:
1. đọc CASA public input nếu có;
2. đọc manual interbank input nếu có;
3. lấy dữ liệu ACTUAL từ Vnstock Bronze;
4. append + deduplicate lịch sử Interbank ON;
5. xây LPI, regime, bank funding stress và forecast;
6. commit/push outputs mới lên GitHub.

## Interbank ON
`data/interbank.csv` chỉ chứa quan sát ACTUAL, không nội suy giả. Vì endpoint Bronze hiện có thể trả chuỗi ON thưa, forecast được mở ở mức EXPLORATORY từ 18 quan sát và luôn gắn LOW CONFIDENCE nếu chưa đạt 60 quan sát ACTUAL. Từ 60 quan sát trở lên mới đủ điều kiện production theo governance hiện tại.

## Streamlit
Khuyến nghị Python 3.12. Streamlit Cloud không cần cài hoặc gọi Vnstock Sponsor/Bronze tại runtime.


## Governed Interbank Model Selection
Interbank ON no longer relies on a single ARIMA family. Candidate models:
- Naive random walk
- Historical mean
- Mean-reversion AR(1)
- Simple ETS
- ARIMA(1,0,0), ARIMA(2,0,0), ARIMA(1,1,0), ARIMA(0,1,1)

Selection uses expanding-window rolling-origin one-step RMSE. A complex candidate is not published unless it beats the naive benchmark. Output `data/model_outputs/interbank_model_comparison.csv` preserves candidate RMSE/MAE/Skill vs Naive and selection flag.

The Streamlit Interbank tab shows 1D/5D/10D/20D forecasts, 80%/95% intervals, selected model, diagnostics, Vietnamese interpretation and model-comparison table. Exploratory forecasts remain LOW CONFIDENCE below the production history threshold.


## Interbank Intelligence Dashboard — Champion / Challenger

Dashboard distinguishes two different questions:

- **Statistical Champion**: lowest rolling-origin one-step RMSE. This remains the governed primary forecast.
- **Directional Challenger**: a non-flat term-structure candidate that still beats Naive and has RMSE within a controlled tolerance of the Champion. It is informational only.

This prevents the system from replacing a statistically superior flat forecast merely because another model draws a more interesting line.

The dashboard now shows:
- ON current level;
- 1D / 5D / 10D / 20D Champion term structure;
- Directional Challenger path;
- 80% / 95% Champion intervals;
- rolling RMSE / MAE / Skill vs Naive;
- market regime, momentum, percentile and actual-rate volatility;
- Vietnamese liquidity interpretation;
- explicit model-risk warning when Champion and Challenger disagree.

Current governance with 23 ACTUAL observations remains EXPLORATORY / LOW CONFIDENCE.

# Vietnam Banking Liquidity Intelligence — Forecast & Explainable Edition

## Kiến trúc Bronze được giữ nguyên
**Không cài hoặc gọi Vnstock Sponsor trên Streamlit Cloud.**

```text
Persistent PC / self-hosted runner
        ↓
vnstock_data Bronze
        ↓
refresh_bronze.py
        ↓
ACTUAL CSV
        ↓
build_models.py
        ↓
Forecast / regime / drivers / diagnostics
        ↓
git push
        ↓
Streamlit Cloud
```

Đây là kiến trúc chuẩn nên tái sử dụng cho các dự án Vnstock Bronze khác.

## Một lần bấm để cập nhật
Chạy:
`REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat`

File BAT:
1. tự tìm `C:\Users\<username>\.venv\Scripts\python.exe`;
2. kiểm tra `vnstock_data`;
3. cài model dependencies nếu thiếu;
4. refresh Bronze ACTUAL;
5. build forecasts;
6. git commit + push.

## Model stack
### LPI
- ON/interbank z-score
- FX 5-day return z-score
- OMO z-score với dấu đảo: bơm ròng làm giảm stress
- LPI = trung bình các component có ACTUAL

### Forecast selection
Ứng viên:
- ARIMA(1,0,0)
- ARIMA(2,0,0)
- ARIMA(1,1,0)
- ARIMA(0,1,1)

Model được chọn bằng RMSE holdout thấp nhất. Naive benchmark = giữ giá trị gần nhất.

Outputs:
- 20 business-day forecast
- 80% confidence interval
- 95% confidence interval
- RMSE / MAE / naive RMSE / skill vs naive / AIC / BIC

### Liquidity regime
Markov Switching 3 trạng thái:
- Excess
- Neutral
- Stress

### Monthly VAR
Chỉ chạy nếu có >=36 quan sát tháng thực và >=2 biến hợp lệ.
Không synthetic-fill dữ liệu thiếu.

### Bank stress transmission
LPI forecast → bank funding vulnerability → funding cost shock → stressed NIM → GREEN/AMBER/RED.

## Important data rules
- BRONZE + ACTUAL luôn ưu tiên.
- PUBLIC + ACTUAL là fallback vĩ mô.
- ASSUMPTION chỉ dùng khi dữ liệu ngân hàng actual thiếu.
- Không đổi nhãn ASSUMPTION thành ACTUAL.
- Không tạo lịch sử giả để model chạy.

## Interbank endpoint
Bronze backend đã từng trả 404. Refresh script thử nhiều signature; nếu vẫn lỗi nhưng có file cũ, trạng thái là DEGRADED và giữ file ACTUAL trước đó.

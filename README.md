# Vietnam Banking Liquidity Intelligence — R7 Data Pipeline Hardening

## Kiến trúc giữ nguyên
Persistent PC/self-hosted runner → `vnstock_data` Bronze → ACTUAL CSV → governed model outputs → GitHub → Streamlit Cloud.

Streamlit Cloud chỉ đọc repository; không gọi Vnstock Sponsor.

## R7 sửa 3 vấn đề của R6

### 1. Interbank backend 500
R6 gọi `interest_rate(length=3650)` và backend trả HTTP 500.

R7 không gọi lịch sử quá dài. Nó thử:
1. `period="day", length=365`
2. `length=365`
3. 180 ngày
4. 90 ngày

Dừng ngay khi lấy được true interbank Overnight.

Điều này bám theo ví dụ chính thức Vnstock 3.2.8 dùng `interest_rate(period="day", length=365)`.

### 2. Bank parser và HYBRID field-level fallback
R6 bỏ toàn bộ dòng ngân hàng xuống FALLBACK nếu chưa đạt 3/5 metrics.

R7 thay bằng field-level fallback:
- Metric nào Bronze có → giữ ACTUAL.
- Metric nào Bronze thiếu → chỉ bù đúng metric đó bằng assumption.
- 5/5 actual → `BRONZE`
- 1–4/5 actual → `HYBRID`
- 0/5 actual → `FALLBACK`

Nhờ vậy LDR/CASA/NIM lấy được từ Bronze không còn bị vứt bỏ chỉ vì một metric khác thiếu.

Parser dùng tidy-data Semantic IDs và name aliases:
- `RT_BANK_LDR`
- `RT_BANK_CASA`
- `RT_BANK_NIM`
- customer loans/deposits
- total assets
- borrowings/deposits from credit institutions

### 3. Statsmodels index warnings
R7 chuẩn hóa dữ liệu forecast thành `RangeIndex` trước khi fit SARIMAX.
Output forecast vẫn được gắn business-date sau khi dự báo.
Mục tiêu: hết cảnh báo `unsupported index`.

## Forecast governance
ARIMA chỉ được dùng nếu RMSE holdout thấp hơn naive.
Nếu không, production dùng `NAIVE_RANDOM_WALK`, Confidence=LOW.

## Upgrade safety
Package R7 là CODE ONLY và không chứa `data/`.
GIỮ nguyên data/ hiện tại khi copy code mới.

Sau đó chạy:
`REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat`

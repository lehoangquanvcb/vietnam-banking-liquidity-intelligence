# Vietnam Banking Liquidity Intelligence — R6 Schema-Locked Production Fix

## Kiến trúc giữ nguyên
Persistent PC/self-hosted runner → `vnstock_data` Bronze → ACTUAL CSV → governed model outputs → GitHub → Streamlit Cloud.

Streamlit Cloud chỉ đọc repository; không cài/gọi Vnstock Sponsor.

## R6 sửa theo runtime thật từ Diagnostic R5

### 1. Interbank ON
R5 xác nhận `Macro().currency().interest_rate()` trả bảng có:
- `group_name = Lãi suất bình quân liên ngân hàng (%/năm)`
- `name = Qua đêm`
- `value`
- `time`
- `source = Ngân hàng Nhà nước Việt Nam`

R6 vì vậy:
1. gọi `interest_rate(length=3650)`;
2. lưu raw audit vào `data/interest_rate_raw_bronze.csv`;
3. lọc đúng group liên ngân hàng;
4. lọc tenor Qua đêm;
5. ghi `data/interbank_bronze.csv` với `date` + `overnight_rate`.

Không dùng các nhóm lãi suất tiền gửi/cho vay khác để thay thế ON.

### 2. Bank stress metrics
R5 xác nhận schema long-format:
`period, id, name, ..., value`.

R6 đọc trực tiếp Semantic ID:
- `RT_BANK_LDR`
- `RT_BANK_CASA`
- `RT_BANK_NIM` nếu có, sau đó mới dùng name fallback
- `BS_CUSTOMER_DEPOSITS`
- `BS_TOTAL_ASSETS`
- customer loans aliases
- `BS_PLACEMENTS_AND_BORROWINGS_FROM_CREDIT_INSTITUTIONS`

Derived:
- `InterbankDep = interbank liabilities / total assets`
- `CreditDepositGap = (customer loans - customer deposits) / customer deposits`

Bronze ACTUAL chỉ vào stress model khi coverage >=60%; thiếu mới fallback ticker-level có nhãn `ASSUMPTION/FALLBACK`.

### 3. Forecast governance
Giữ nguyên governance:
- >=80 observations
- holdout RMSE
- ARIMA chỉ dùng nếu thắng naive benchmark
- nếu không: `NAIVE_RANDOM_WALK`, Confidence=LOW

## Upgrade safety
Package R6 **không chứa `data/`**.

Giữ nguyên thư mục repository `data/`, copy đè code/config/Master rồi chạy:
`REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat`

## Kỳ vọng sau refresh
Sidebar nên chuyển từ:
- `Bronze đủ stress metrics: 0`
- `Interbank model: NO_INTERBANK_DATA`
- `Interbank source: NONE`

sang trạng thái có ACTUAL coverage và interbank source `BRONZE`, nếu lịch sử lọc được đủ dài cho forecast.

# Vietnam Banking Liquidity Intelligence — Production Plus

## KIẾN TRÚC BẮT BUỘC GIỮ
Persistent PC / self-hosted runner -> `vnstock_data` Bronze -> ACTUAL CSV -> model outputs -> GitHub -> Streamlit.

**Streamlit Cloud không cài và không gọi Vnstock Sponsor.**

## Quan trọng: package này KHÔNG có thư mục data/
Mục đích là bảo vệ dữ liệu production. Khi nâng cấp:
- GIỮ nguyên `data/` trong repo.
- Chép đè `app.py`, `scripts/`, `config/`, `.github/`, `requirements*.txt`, các file `.bat`, Master.
- Không xóa `data/`.

## Nâng cấp chính

### 1) Bank parser theo vnstock_data v3.2.8+
- Gọi `balance_sheet(... format="long", com_type="Bank")`
- Gọi `ratio(... format="long", com_type="Bank")`
- Gọi `financial_health(scorecard="bank")`
- Ưu tiên Semantic ID (`id`) trước tên hiển thị.
- Lưu raw source tables vào `data/raw_bank/` để audit/debug.
- Tính MetricCoverage cho 5 biến: LDR, CASA, InterbankDep, CreditDepositGap, NIM.
- Chỉ dùng Bronze trong bank stress nếu coverage >=60%; thiếu thì fallback ticker-level có nhãn ASSUMPTION.

### 2) Interbank multi-source
Nguồn true interbank:
1. `data/interbank_bronze.csv` từ `Macro().currency().interbank_rate(...)`.
2. `data/interbank_manual.csv` nếu người dùng nhập/import ACTUAL từ nguồn công khai.

`Macro().currency().interest_rate()` được lưu thành `funding_rate_proxy_bronze.csv`; KHÔNG được gắn nhãn interbank.

Template:
`templates/interbank_manual_template.csv`

### 3) LPI
- ON/interbank z-score nếu có.
- FX 5-day pressure z-score.
- OMO pressure z-score.
- Cần tối thiểu 2 thành phần ACTUAL để LPI tồn tại.
- Không tạo history giả.

### 4) Upgrade-safe
Code package không chứa `data/`, do đó copy bản mới không làm mất Bronze ACTUAL/model outputs cũ.

## Chạy
`REFRESH_BRONZE_BUILD_MODELS_AND_PUSH.bat`

## Nếu interbank Vnstock vẫn 404
Tạo file:
`data/interbank_manual.csv`

Schema:
`date,overnight_rate,source_url,source_name,data_type`

Chỉ nhập dữ liệu thực và giữ URL nguồn.

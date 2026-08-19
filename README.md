# Vietnam Banking Liquidity Intelligence

## Kiến trúc

Máy local / self-hosted runner có Vnstock Sponsor → `vnstock_data` → CSV ACTUAL + model outputs → GitHub → Streamlit Cloud chỉ đọc repository.

Streamlit Cloud **không cài và không gọi Vnstock Sponsor**.

## Package đã được làm sạch

Chỉ giữ các file production cần thiết. Đã loại bỏ `.git`, diagnostics R5, raw-bank snapshots, probe scripts, placeholder GITHUB/STREAMLIT, AGENTS.md, các BAT cũ, duplicate assumption files và model outputs cũ.

## Cấu trúc

- `app.py`: giao diện Streamlit.
- `scripts/refresh_data.py`: lấy dữ liệu Bronze thực.
- `scripts/build_models.py`: LPI, forecast, regime, bank stress.
- `scripts/export_manual_interbank.py`: fallback ACTUAL từ Excel Master.
- `config/`: universe, assumptions, model config.
- `data/`: được tạo/cập nhật khi chạy local; GitHub lưu output để Streamlit đọc.
- `RUN_UPDATE_AND_PUSH.bat`: pipeline duy nhất cần chạy.
- `Vietnam_Banking_Liquidity_Master.xlsx`: cấu hình, governance và interbank manual input.

## Dữ liệu ngân hàng

Fundamental v3.2.8 trả tidy data và dùng `id` làm primary key. Script ưu tiên:

- `financial_health(scorecard="bank")` cho LDR/CASA/NIM;
- `ratio(..., com_type="Bank")` làm nguồn bổ sung;
- `balance_sheet(..., com_type="Bank")` để tính customer loans/deposits và interbank dependence.

Mỗi nguồn được gọi độc lập. Một nguồn lỗi không làm hỏng cả ticker.

Stress lineage:

- `BRONZE`: 5/5 metric thực;
- `HYBRID`: 1–4/5 metric thực, phần thiếu mới dùng assumption;
- `FALLBACK`: 0/5 metric thực.

## Interbank ON

Thứ tự:

1. `Macro().currency().interbank_rate(start, end, period="day")`;
2. `Macro().currency().interest_rate(period="day", length=365, format="long")` và lọc Overnight/Qua đêm;
3. pivot `interest_rate()`;
4. `data/interbank_manual.csv` nếu có ACTUAL nhập từ Master.

Không dùng lãi suất tiền gửi/cho vay để giả làm interbank.

## Cài / cập nhật

Nếu muốn giữ nguyên GitHub remote cũ, **chỉ giữ thư mục `.git`** của project hiện tại. Xóa toàn bộ file/thư mục project cũ khác, giải nén package mới vào root repo, rồi chạy duy nhất:

```bat
RUN_UPDATE_AND_PUSH.bat
```

BAT sẽ lấy lại dữ liệu ACTUAL, build model, `git add -A`, commit và push cả code sạch + data/model outputs mới. Streamlit Cloud sẽ tự đọc commit mới.


## CASA governance
- Priority 1: reported CASA from `financial_health(scorecard="bank")`.
- Priority 2: reported CASA from `ratio()`.
- Priority 3: derived public-BS proxy = non-term/demand customer deposits / total customer deposits.
- `CASASource` records lineage; invalid values outside 0-100% are rejected.


## Nâng cấp ACTUAL CASA

Nếu Vnstock không trả CASA trực tiếp và balance sheet không có demand deposits, hệ thống không giả định đó là ACTUAL.

Thứ tự CASA:
1. Vnstock `financial_health`;
2. Vnstock `ratio`;
3. Derived demand/non-term deposits ÷ customer deposits nếu Vnstock thực sự có tử số;
4. `CASA_INPUT` trong Excel Master / `data/casa_actual.csv`, chỉ nhận `DataType=ACTUAL` và SourceURL hợp lệ;
5. nếu vẫn thiếu: bank stress dùng assumption cho riêng CASA và gắn `HYBRID`.

Nếu 4 metric Vnstock + CASA public đều là ACTUAL, lineage là `ACTUAL_MIXED_SOURCE`, không gọi nhầm là `BRONZE`.

## Mở rộng Interbank ON

Pipeline thử `interbank_rate()` theo từng năm từ 2021 đến nay để tránh request quá lớn. Nếu dedicated endpoint không usable, vẫn dùng `interest_rate()` đã hoạt động.

Forecast Interbank giờ dùng **chính số quan sát ACTUAL trong interbank.csv**, không dùng các giá trị được forward-fill trong daily panel. Vì vậy Diagnostics phản ánh đúng sample thực.


## CASA 30/06/2026 đã được nạp sẵn
Package có `config/casa_actual_public_seed.csv` cho đủ 20 ngân hàng, ngày 30/06/2026.

Nguồn: VietNamNet, bảng CASA tổng hợp từ BCTC bán niên 2026 của các ngân hàng.

Ưu tiên dữ liệu:
1. CASA trực tiếp từ Vnstock;
2. `data/casa_actual.csv` do người dùng cập nhật;
3. `config/casa_actual_public_seed.csv`;
4. assumption chỉ khi cả ba nguồn trên đều không có.

CASA từ public seed được gắn `ACTUAL_PUBLIC_SOURCE`; nếu 4 metric còn lại là Bronze ACTUAL thì stress lineage trở thành `ACTUAL_MIXED_SOURCE`, không gọi nhầm là BRONZE.

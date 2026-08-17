# Vietnam Banking Liquidity Intelligence V6.1 — Streamlit Cloud Ready

## Điểm khác V6
- Không còn yêu cầu chạy `bank_data.py` và `bank_stress.py` bằng tay trước khi mở app.
- `app.py` tự tải dữ liệu ngân hàng từ Vnstock Fundamental.
- Có `st.cache_data` 12 giờ để giảm số lượt API.
- Có nút **Cập nhật dữ liệu Vnstock** trên sidebar.
- Tự tính stress score trong app.
- Toàn bộ giao diện chính đã Việt hóa.
- Không synthetic-fill BCTC ngân hàng.

## Deploy Streamlit Cloud
Repo tối thiểu:
```text
app.py
requirements.txt
README.md
config/
  banks.json
  vnstock_bronze.json
data/
```

Main file path:
```text
app.py
```

## Python
Khuyến nghị Python 3.12 cho production ổn định hơn.

## Sponsor
Không hard-code token/API key. Cấu hình Vnstock Sponsor theo cơ chế chính thức của Vnstock/Streamlit Secrets nếu tài khoản của bạn yêu cầu.

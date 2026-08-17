# Vietnam Banking Liquidity Intelligence V6.2 — Cloud Stable

## Lỗi V6.1 đã sửa
Streamlit Cloud **không còn import `vnstock_data`**. Vì vậy app không bị `ModuleNotFoundError: No module named 'vnstock_data'`.

Kiến trúc:
```text
Máy local + Vnstock Bronze Sponsor
          ↓
bank_data_local.py / update_macro_local.py
          ↓
data/*.csv
          ↓
GitHub
          ↓
Streamlit Community Cloud
          ↓
app.py đọc CSV + chạy dashboard/stress
```

## Deploy Streamlit Cloud
`requirements.txt` chỉ gồm thư viện tiêu chuẩn cloud. Main file:
```text
app.py
```

Khuyến nghị Python **3.12**.

## Cài trên máy local lần đầu
Double-click:
```text
SETUP_LOCAL.bat
```
Hoặc:
```bash
pip install -r requirements_local.txt
```

Sau đó bảo đảm Vnstock Sponsor đã được kích hoạt/cấu hình trên máy theo cơ chế chính thức của Vnstock.

## Refresh dữ liệu
Double-click:
```text
REFRESH_AND_PUSH.bat
```

Script sẽ:
1. tải BCTC ngân hàng từ Vnstock;
2. tải dữ liệu vĩ mô;
3. dựng `daily_features.csv`;
4. `git add data`;
5. `git commit`;
6. `git push`.

Streamlit Cloud sẽ tự redeploy khi GitHub có commit mới.

## Quan trọng
Không thêm `data/*.csv` vào `.gitignore`, vì Cloud cần đọc các CSV này.

Không commit token/API key vào GitHub.

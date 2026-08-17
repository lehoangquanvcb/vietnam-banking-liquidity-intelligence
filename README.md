# Vietnam Banking Liquidity Intelligence — Sponsor Connect Edition

## Thay đổi chính
- Bỏ số phiên bản khỏi tiêu đề giao diện.
- Nếu Streamlit Secrets đã có API Key nhưng `vnstock_data` chưa sẵn sàng, nút **Kết nối Vnstock Bronze** luôn xuất hiện.
- Sponsor installer chỉ chạy sau khi người dùng bấm nút.
- Hiển thị tiến trình 3 bước và log lỗi cụ thể.
- Bronze chỉ full-load 20 ngân hàng sau khi probe 3 mã đạt yêu cầu.
- Free/Guest chỉ probe 3 mã để không chạm quota.
- Circuit breaker + cache 6 giờ.
- Không còn file `sponsor_bootstrap.py`; toàn bộ kết nối nằm trong `app.py`.

## Streamlit Secret
Manage app → Settings → Secrets:
```toml
VNSTOCK_API_KEY = "YOUR_KEY"
```

## Git
Khi thay package cũ, giữ thư mục `.git`, xóa code cũ, copy toàn bộ package mới rồi:
```bash
git add -A
git commit -m "Upgrade sponsor connection"
git push origin main
```

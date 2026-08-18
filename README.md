# Vietnam Banking Liquidity Intelligence — Production Bronze Pipeline

## Vì sao đổi kiến trúc?
`vnstock_data` Sponsor không phải package pip công khai. Vnstock yêu cầu cài bằng installer riêng và có chính sách giới hạn thiết bị. Streamlit Community Cloud dùng container có thể tái tạo, nên cài/kích hoạt Sponsor ngay trong app runtime là không ổn định.

Bản này tách:
- **Bronze data acquisition**: chạy trên máy PC/server ổn định đã kích hoạt Sponsor.
- **Streamlit production**: chỉ đọc CSV ACTUAL đã push lên GitHub và chạy mô hình.

## 1. Streamlit Cloud
Không cần API key, không cần `vnstock_data`, không chạy installer.

Deploy:
- Repository: repo hiện tại
- Main file: `app.py`
- `requirements.txt`: chỉ package chuẩn.

## 2. Bronze trên máy local
Cài Vnstock Sponsor trên máy ổn định bằng installer chính thức của Vnstock.

Khi `python -c "import vnstock_data"` chạy được, refresh bằng:
`REFRESH_BRONZE_AND_PUSH.bat`

Batch sẽ:
1. chạy `scripts/refresh_bronze.py`;
2. lấy 20 ngân hàng + macro bằng `vnstock_data`;
3. lưu ACTUAL CSV trong `data/`;
4. git add/commit/push;
5. Streamlit tự redeploy.

## 3. Tự động hóa không cần bấm .bat
Package có:
`.github/workflows/refresh_vnstock_self_hosted.yml`

Đăng ký PC/server của bạn làm **GitHub self-hosted runner**, rồi workflow có thể chạy lịch từ thứ Hai đến thứ Sáu.

Không đổi workflow sang `ubuntu-latest` nếu chưa cân nhắc giới hạn thiết bị Sponsor; self-hosted runner giữ cùng một máy ổn định.

## 4. Linux server ổn định
Có `scripts/bootstrap_bronze_linux.sh` theo CLI non-interactive của Vnstock. Đặt `VNSTOCK_API_KEY` trong environment của server rồi chạy script một lần.

## Data lineage
- `BRONZE + ACTUAL`: dữ liệu lấy từ `vnstock_data`.
- `PUBLIC + ACTUAL`: snapshot công khai.
- `FALLBACK + ASSUMPTION`: chỉ dùng cho mã thiếu actual.

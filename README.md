# Vietnam Banking Liquidity Intelligence V6.4 — Sponsor-Aware

## V6.4 sửa gì?
V6.4 không còn ghi "Bronze" nhưng thực tế chạy Free một cách mập mờ.

App hiển thị rõ 3 trạng thái:
- **BRONZE CONNECTED**: `vnstock_data` Sponsor đang hoạt động.
- **FREE MODE**: dùng `vnstock` Community.
- **FALLBACK**: dùng snapshot ACTUAL + assumptions được gắn nhãn.

## Cách nhập Vnstock API Key

### Cách khuyến nghị — Streamlit Secrets
Vào:
`Manage app → Settings → Secrets`

Thêm:
```toml
VNSTOCK_API_KEY = "API_KEY_CUA_BAN"
```

Không commit `secrets.toml`.

### Cách thử nhanh — giao diện app
Nếu chưa có Secret, sidebar hiện ô password `Vnstock API Key`.
Key chỉ được lưu trong `st.session_state` của phiên hiện tại.

## Sponsor runtime installer
Nếu `vnstock_data` chưa có, app dùng CLI installer chính thức:
`https://vnstocks.com/files/vnstock-cli-installer.run`

Installer chạy non-interactive và nhận key qua biến môi trường `VNSTOCK_API_KEY`, không đưa key vào command line.

Sponsor được cài vào:
`/tmp/vnstock_sponsor_venv`

App thêm site-packages của venv này vào `sys.path`.

## Deploy
Khuyến nghị Python 3.12.
Main file: `app.py`.

## Data priority
1. Vnstock Bronze Sponsor (`vnstock_data`)
2. Vnstock Community (`vnstock`)
3. Public ACTUAL macro snapshot
4. Explicit `ASSUMPTION` fallback

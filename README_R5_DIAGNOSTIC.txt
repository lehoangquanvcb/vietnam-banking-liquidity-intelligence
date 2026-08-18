R5 DIAGNOSTIC-FIRST

Mục tiêu: đọc đúng runtime/schema Vnstock Bronze trên máy của bạn trước khi sửa production model.

Cách dùng:
1. Giữ nguyên project production hiện tại.
2. Copy 2 mục sau từ package R5 vào project:
   - RUN_VNSTOCK_DIAGNOSTIC_R5.bat
   - scripts/probe_vnstock_r5.py
3. Double-click RUN_VNSTOCK_DIAGNOSTIC_R5.bat
4. Chờ DONE.
5. Gửi lại file:
   VNSTOCK_DIAGNOSTIC_R5_RESULT.zip

R5 diagnostic KHÔNG:
- sửa data/
- sửa model outputs
- chạy git push
- gọi Streamlit
- ghi API key/secrets vào report theo chủ đích

Probe chỉ thực hiện một số request nhỏ cần thiết để xác định schema/API thực tế.

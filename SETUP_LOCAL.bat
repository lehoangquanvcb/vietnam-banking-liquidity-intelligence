@echo off
cd /d "%~dp0"
python -m pip install --upgrade pip
pip install -r requirements_local.txt
echo.
echo Da cai thu vien local. Neu Vnstock Sponsor can kich hoat/dang nhap, hay lam theo huong dan cua Vnstock tren may nay.
pause

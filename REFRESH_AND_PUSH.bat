@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo REFRESH VNSTOCK BRONZE + PUSH DATA TO GITHUB
echo ================================================

python bank_data_local.py
if errorlevel 1 goto :error

python update_macro_local.py
if errorlevel 1 goto :error

python build_daily_local.py
if errorlevel 1 goto :error

git add data
git diff --cached --quiet
if %errorlevel%==0 (
    echo Khong co thay doi du lieu de commit.
    goto :done
)

git commit -m "Refresh Vnstock data"
if errorlevel 1 goto :error

git push
if errorlevel 1 goto :error

:done
echo.
echo Hoan tat. Streamlit Cloud se tu dong cap nhat sau khi GitHub nhan commit.
pause
exit /b 0

:error
echo.
echo CO LOI. Kiem tra thong bao phia tren.
pause
exit /b 1

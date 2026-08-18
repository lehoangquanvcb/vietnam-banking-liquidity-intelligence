@echo off
setlocal
cd /d "%~dp0"

echo =====================================================
echo VNSTOCK BRONZE REFRESH -> GITHUB -> STREAMLIT
echo =====================================================

python scripts\refresh_bronze.py
if errorlevel 1 goto :error

git add data
git diff --cached --quiet
if %errorlevel%==0 (
  echo Khong co thay doi du lieu.
  goto :done
)

git commit -m "Refresh Bronze banking liquidity data"
if errorlevel 1 goto :error

git push origin main
if errorlevel 1 goto :error

:done
echo.
echo Hoan tat. Streamlit Cloud se tu dong doc du lieu moi tu GitHub.
pause
exit /b 0

:error
echo.
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1

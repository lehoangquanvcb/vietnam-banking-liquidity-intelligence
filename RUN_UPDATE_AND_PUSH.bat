@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo VIETNAM BANKING LIQUIDITY INTELLIGENCE
echo LOCAL BRONZE -> MODELS -> GITHUB -> STREAMLIT
echo ============================================================

set "PYBRONZE="
if not "%VNSTOCK_PYTHON%"=="" if exist "%VNSTOCK_PYTHON%" set "PYBRONZE=%VNSTOCK_PYTHON%"
if "%PYBRONZE%"=="" if exist "C:\Users\%USERNAME%\.venv\Scripts\python.exe" set "PYBRONZE=C:\Users\%USERNAME%\.venv\Scripts\python.exe"
if "%PYBRONZE%"=="" where python >nul 2>nul && set "PYBRONZE=python"
if "%PYBRONZE%"=="" goto :error

echo Python: %PYBRONZE%
"%PYBRONZE%" -c "from vnstock_data import Fundamental, Macro; print('VNSTOCK DATA READY')"
if errorlevel 1 goto :error

"%PYBRONZE%" -c "import pandas,numpy,statsmodels,sklearn,openpyxl; print('MODEL DEPS READY')"
if errorlevel 1 (
  "%PYBRONZE%" -m ensurepip --upgrade >nul 2>nul
  "%PYBRONZE%" -m pip install -r requirements_local.txt
  if errorlevel 1 goto :error
)

echo [1/5] Export optional CASA ACTUAL input...
"%PYBRONZE%" scripts\export_casa_actual.py

echo [2/5] Optional manual interbank input...
"%PYBRONZE%" scripts\export_manual_interbank.py

echo [3/5] Refresh actual data...
"%PYBRONZE%" scripts\refresh_data.py
if errorlevel 1 goto :error

echo [4/5] Build models...
"%PYBRONZE%" scripts\build_models.py
if errorlevel 1 goto :error

echo [5/5] Commit data and model outputs...
git add -A
git diff --cached --quiet
if %errorlevel%==0 goto :done
git commit -m "Upgrade CASA actual sources and interbank history"
if errorlevel 1 goto :error
git push origin main
if errorlevel 1 goto :error

:done
echo.
echo HOAN TAT. Streamlit Cloud se doc du lieu moi tu GitHub.
pause
exit /b 0

:error
echo.
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1

@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo PRODUCTION R7: BRONZE -> GOVERNED MODELS -> GITHUB
echo DATA/ IS PERSISTENT. DO NOT DELETE IT.
echo ============================================================

set "PYBRONZE="
if not "%VNSTOCK_PYTHON%"=="" if exist "%VNSTOCK_PYTHON%" set "PYBRONZE=%VNSTOCK_PYTHON%"
if "%PYBRONZE%"=="" if exist "C:\Users\%USERNAME%\.venv\Scripts\python.exe" set "PYBRONZE=C:\Users\%USERNAME%\.venv\Scripts\python.exe"
if "%PYBRONZE%"=="" where python >nul 2>nul && set "PYBRONZE=python"
if "%PYBRONZE%"=="" goto :error

echo Python Bronze: %PYBRONZE%
"%PYBRONZE%" -c "from vnstock_data import Fundamental, Macro; print('BRONZE READY')"
if errorlevel 1 goto :error

"%PYBRONZE%" -c "import pandas,numpy,statsmodels,sklearn,openpyxl; print('MODEL DEPS READY')"
if errorlevel 1 (
  "%PYBRONZE%" -m ensurepip --upgrade >nul 2>nul
  "%PYBRONZE%" -m pip install -r requirements_local.txt
  if errorlevel 1 goto :error
)

echo [0/3] Export optional manual/public interbank ACTUAL...
"%PYBRONZE%" scripts\export_interbank_from_master.py

echo [1/3] Refresh Bronze ACTUAL...
"%PYBRONZE%" scripts\refresh_bronze.py
if errorlevel 1 goto :error

echo [2/3] Build forecasts + guaranteed bank stress fallback...
"%PYBRONZE%" scripts\build_models.py
if errorlevel 1 goto :error

echo [3/3] Commit persistent data + model outputs...
git add data
git diff --cached --quiet
if %errorlevel%==0 goto :done
git commit -m "Refresh Bronze data and Production R7 hardened models"
if errorlevel 1 goto :error
git push origin main
if errorlevel 1 goto :error

:done
echo.
echo HOAN TAT. Streamlit se tu dong doc outputs moi tu GitHub.
pause
exit /b 0

:error
echo.
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1

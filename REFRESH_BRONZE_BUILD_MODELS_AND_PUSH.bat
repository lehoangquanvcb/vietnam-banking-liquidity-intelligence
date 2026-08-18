@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo BRONZE ACTUAL -> MODELS -> GITHUB -> STREAMLIT
echo DATA/ IS PERSISTENT AND IS NEVER INITIALIZED/OVERWRITTEN HERE
echo ============================================================

set "PYBRONZE="
if not "%VNSTOCK_PYTHON%"=="" if exist "%VNSTOCK_PYTHON%" set "PYBRONZE=%VNSTOCK_PYTHON%"
if "%PYBRONZE%"=="" if exist "C:\Users\%USERNAME%\.venv\Scripts\python.exe" set "PYBRONZE=C:\Users\%USERNAME%\.venv\Scripts\python.exe"
if "%PYBRONZE%"=="" where python >nul 2>nul && set "PYBRONZE=python"
if "%PYBRONZE%"=="" goto :error

echo Python Bronze: %PYBRONZE%
"%PYBRONZE%" -c "from vnstock_data import Fundamental, Macro; print('BRONZE READY')"
if errorlevel 1 goto :error

"%PYBRONZE%" -c "import pandas,numpy,statsmodels,sklearn; print('MODEL DEPS READY')"
if errorlevel 1 (
  "%PYBRONZE%" -m ensurepip --upgrade >nul 2>nul
  "%PYBRONZE%" -m pip install -r requirements_local.txt
  if errorlevel 1 goto :error
)

echo [1/3] Refresh Bronze ACTUAL...
"%PYBRONZE%" scripts\refresh_bronze.py
if errorlevel 1 goto :error

echo [2/3] Build forecasts and bank stress...
"%PYBRONZE%" scripts\build_models.py
if errorlevel 1 goto :error

echo [3/3] Commit persistent data + model outputs...
git add data
git diff --cached --quiet
if %errorlevel%==0 goto :done
git commit -m "Refresh Bronze actual data and liquidity models"
if errorlevel 1 goto :error
git push origin main
if errorlevel 1 goto :error

:done
echo.
echo HOAN TAT. Streamlit se doc data/model outputs moi tu GitHub.
pause
exit /b 0

:error
echo.
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1

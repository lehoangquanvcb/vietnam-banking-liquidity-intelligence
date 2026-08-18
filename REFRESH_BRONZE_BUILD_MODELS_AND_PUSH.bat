@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo VNSTOCK BRONZE -> BUILD MODELS -> GITHUB -> STREAMLIT
echo ============================================================

set "PYBRONZE="

if not "%VNSTOCK_PYTHON%"=="" (
    if exist "%VNSTOCK_PYTHON%" set "PYBRONZE=%VNSTOCK_PYTHON%"
)

if "%PYBRONZE%"=="" (
    if exist "C:\Users\%USERNAME%\.venv\Scripts\python.exe" (
        set "PYBRONZE=C:\Users\%USERNAME%\.venv\Scripts\python.exe"
    )
)

if "%PYBRONZE%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 set "PYBRONZE=python"
)

if "%PYBRONZE%"=="" (
    echo ERROR: Khong tim thay Python.
    goto :error
)

echo Python Bronze: %PYBRONZE%

"%PYBRONZE%" -c "from vnstock_data import Fundamental, Macro; print('BRONZE DATA READY')"
if errorlevel 1 (
    echo ERROR: Python tren khong co vnstock_data.
    echo Dat VNSTOCK_PYTHON tro toi python.exe cua venv Sponsor neu can.
    goto :error
)

"%PYBRONZE%" -c "import pandas, numpy, statsmodels, sklearn; print('MODEL DEPENDENCIES READY')"
if errorlevel 1 (
    echo Dang cai model dependencies vao dung Bronze venv...
    "%PYBRONZE%" -m ensurepip --upgrade >nul 2>nul
    "%PYBRONZE%" -m pip install -r requirements_local.txt
    if errorlevel 1 goto :error
)

echo.
echo [1/3] Refresh Bronze ACTUAL...
"%PYBRONZE%" scripts\refresh_bronze.py
if errorlevel 1 goto :error

echo.
echo [2/3] Build forecasts, regimes, diagnostics and explanations...
"%PYBRONZE%" scripts\build_models.py
if errorlevel 1 goto :error

echo.
echo [3/3] Commit data + model outputs...
git add data
git diff --cached --quiet
if %errorlevel%==0 (
    echo Khong co thay doi du lieu/model de commit.
    goto :done
)

git commit -m "Refresh Bronze data and liquidity forecasts"
if errorlevel 1 goto :error

git push origin main
if errorlevel 1 goto :error

:done
echo.
echo HOAN TAT.
echo Streamlit Cloud se tu dong doc Bronze ACTUAL + forecast moi tu GitHub.
pause
exit /b 0

:error
echo.
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1

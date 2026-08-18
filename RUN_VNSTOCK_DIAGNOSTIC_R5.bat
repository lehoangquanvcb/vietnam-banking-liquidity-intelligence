@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo VNSTOCK R5 DIAGNOSTIC-FIRST
echo This DOES NOT refresh production data and DOES NOT git push.
echo ============================================================
echo.

set "PYBRONZE="
if not "%VNSTOCK_PYTHON%"=="" if exist "%VNSTOCK_PYTHON%" set "PYBRONZE=%VNSTOCK_PYTHON%"
if "%PYBRONZE%"=="" if exist "C:\Users\%USERNAME%\.venv\Scripts\python.exe" set "PYBRONZE=C:\Users\%USERNAME%\.venv\Scripts\python.exe"

if "%PYBRONZE%"=="" (
  echo ERROR: Khong tim thay Python Bronze.
  echo Expected: C:\Users\%USERNAME%\.venv\Scripts\python.exe
  pause
  exit /b 1
)

echo Python Bronze: %PYBRONZE%
"%PYBRONZE%" -c "import vnstock_data; print('vnstock_data import OK')"
if errorlevel 1 (
  echo ERROR: Python nay khong import duoc vnstock_data.
  pause
  exit /b 2
)

echo.
echo Running diagnostic probe...
"%PYBRONZE%" scripts\probe_vnstock_r5.py
if errorlevel 1 (
  echo.
  echo DIAGNOSTIC CO LOI. Gui file diagnostics_r5\VNSTOCK_DIAGNOSTIC_R5_REPORT.txt neu da duoc tao.
  pause
  exit /b 3
)

echo.
echo ============================================================
echo HOAN TAT.
echo Gui file VNSTOCK_DIAGNOSTIC_R5_RESULT.zip cho ChatGPT.
echo KHONG can git add / commit / push.
echo ============================================================
pause

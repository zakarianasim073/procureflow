@echo off
setlocal

cd /d "%~dp0"

echo [1/2] Exporting canonical intelligence JSON...
python tools\export_canonical_exports.py
if errorlevel 1 (
  echo Canonical export failed.
  exit /b 1
)

echo.
echo Export complete.
echo Output folder:
echo   D:\A1\procurementflow_final_v3\procurementflow\runtime\canonical_exports
echo.
pause

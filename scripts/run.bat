@echo off
cd /d %~dp0\..
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m src.main --lookback-hours 24
  if errorlevel 1 goto :err
  .venv\Scripts\python.exe tools\build_cache.py
) else (
  python -m src.main --lookback-hours 24
  if errorlevel 1 goto :err
  python tools\build_cache.py
)
pause
goto :eof
:err
echo Engine run failed.
pause
exit /b 1

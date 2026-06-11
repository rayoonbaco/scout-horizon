@echo off
setlocal
cd /d %~dp0\..

REM 1) Run engine to generate outputs JSON
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m src.main --lookback-hours 24
  if errorlevel 1 goto :err
  .venv\Scripts\python.exe tools\build_cache.py
  if errorlevel 1 goto :err
) else (
  python -m src.main --lookback-hours 24
  if errorlevel 1 goto :err
  python tools\build_cache.py
  if errorlevel 1 goto :err
)

REM 2) Start local server and open dashboard
start "" http://localhost:8000/viewer/index.html
python -m http.server 8000
goto :eof

:err
echo.
echo ERROR: Something failed. Scroll up for the message.
pause
exit /b 1

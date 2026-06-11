@echo off
setlocal
cd /d "%~dp0"
set "APP_URL=http://127.0.0.1:8787/viewer/index.html?fix=pass18f"
echo Starting Scout Horizon...
echo.
echo This window is the local server. Leave it open while viewing the dashboard.
echo Close this window or press CTRL+C to stop the server.
echo Dashboard URL: %APP_URL%
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating local Python environment...
  python -m venv .venv
  if errorlevel 1 goto :err
)

.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :err

.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :err

echo.
echo Opening browser...
start "" "%APP_URL%"
echo.
echo Scout Horizon is starting now. If the browser loads early, wait a few seconds and press Refresh.
echo.

.venv\Scripts\python.exe -m uvicorn viewer_server:app --host 127.0.0.1 --port 8787

echo.
echo Scout Horizon server stopped.
pause
exit /b 0

:err
echo.
echo Scout Horizon could not start. Scroll up for the exact error.
pause
exit /b 1

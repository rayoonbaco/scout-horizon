@echo off
cd /d %~dp0\..
start "" http://localhost:8000/viewer/index.html
python -m http.server 8000

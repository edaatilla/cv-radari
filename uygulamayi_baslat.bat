@echo off
cd /d "%~dp0"
echo CV Radari baslatiliyor...
start "CV Radari Sunucu" cmd /k venv\Scripts\python.exe app.py
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:7860

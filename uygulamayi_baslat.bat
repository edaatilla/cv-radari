@echo off
cd /d "%~dp0"
echo CV Radari baslatiliyor, lutfen bekleyin...
start "" http://127.0.0.1:7860
venv\Scripts\python.exe app.py
echo.
echo Sunucu durdu. Bu pencereyi kapatabilirsin.
pause

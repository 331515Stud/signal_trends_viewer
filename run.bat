@echo off
cd /d "%~dp0"

REM Запуск venv
call venv\Scripts\activate.bat

echo Запускаю программу...
python main.py

pause

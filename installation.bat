@echo off
cd /d "%~dp0"

echo === Проверка виртуального окружения ===

REM Если venv нет — создаём
if not exist "venv\" (
    echo Создаю виртуальное окружение...
    python -m venv venv
) else (
    echo Виртуальное окружение уже существует.
)

call venv\Scripts\activate.bat

echo === Проверка установки зависимостей ===

REM Файл-флаг, что зависимости уже установлены
set FLAG_FILE=venv\installed.ok

if exist "%FLAG_FILE%" (
    echo Зависимости уже установлены. Пропускаю установку.
    goto FINISH
)

echo Устанавливаю PyQt6...
pip install PyQt6

IF EXIST requirements.txt (
    echo Устанавливаю зависимости из requirements.txt...
    pip install -r requirements.txt
)

echo. > "%FLAG_FILE%"
echo Установка зависимостей завершена.

:FINISH
echo Готово!
pause

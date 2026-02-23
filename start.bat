@echo off
REM Emby Bot Launcher voor Windows
REM Start ALTIJD beide services (Bot + Web)

echo ================================================
echo           EMBY BOT - WINDOWS LAUNCHER
echo ================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python niet gevonden!
    echo Installeer Python 3.11+ van https://python.org
    pause
    exit /b 1
)

REM Check config
if not exist "config.yaml" (
    echo [ERROR] config.yaml niet gevonden!
    echo Kopieer config.yaml.example en vul je gegevens in
    pause
    exit /b 1
)

echo [*] Starting beide services...
echo [*] Web Interface: http://localhost:5000
echo [*] Telegram Bot: Running
echo [*] Druk Ctrl+C om te stoppen
echo.
echo ================================================
echo.

REM Start main.py which handles both services
python main.py

echo.
echo Tot ziens!
pause

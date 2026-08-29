@echo off
REM Eurocode Reader - one-click launcher (Windows)
REM Uses the local .venv if present, otherwise the system Python.

cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py %*
) else (
    where pythonw >nul 2>nul
    if errorlevel 1 (
        echo Python was not found on PATH.
        echo Install Python 3.10+ and run:  pip install -r requirements.txt
        pause
        exit /b 1
    )
    start "" pythonw app.py %*
)

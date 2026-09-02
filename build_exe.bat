@echo off
REM EuroCode Compass - one-click build of the standalone Windows executable.
REM Double-click this file. The result lands in dist\EuroCodeCompass.exe

setlocal
cd /d "%~dp0"

echo ======================================================================
echo   Building EuroCode Compass
echo ======================================================================
echo.

REM Prefer the launcher; fall back to whatever python is on PATH.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    set "PY=python"
)

%PY% --version >nul 2>&1
if not %ERRORLEVEL%==0 (
    echo Python was not found on this machine.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo and tick "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

REM PyInstaller is only needed to build, never to run the result.
%PY% -c "import PyInstaller" >nul 2>&1
if not %ERRORLEVEL%==0 (
    echo PyInstaller is not installed. Installing it now...
    %PY% -m pip install pyinstaller
    if not %ERRORLEVEL%==0 (
        echo.
        echo Could not install PyInstaller. Check the messages above.
        pause
        exit /b 1
    )
    echo.
)

%PY% build_exe.py %*
set "RESULT=%ERRORLEVEL%"

echo.
if %RESULT%==0 (
    echo Build finished. The executable is in the dist folder.
) else (
    echo Build failed - see the messages above.
)
echo.
pause
exit /b %RESULT%

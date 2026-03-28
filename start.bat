@echo off
title Screen Recorder Setup
echo ============================================
echo   Screen Recorder - Setup ^& Start
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.9+
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check and install ffmpeg
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] ffmpeg not found. Installing via winget...
    echo.
    winget install ffmpeg --accept-source-agreements --accept-package-agreements
    echo.

    :: Refresh PATH for this session
    for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
    set "PATH=%SYS_PATH%;%USR_PATH%"

    ffmpeg -version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] ffmpeg installation failed or PATH not updated.
        echo         Please restart your PC and run this script again,
        echo         or install manually: https://ffmpeg.org/download.html
        echo.
        pause
        exit /b 1
    )
)

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
echo.

:: Launch
echo Starting Screen Recorder...
python screen_recorder.py

pause

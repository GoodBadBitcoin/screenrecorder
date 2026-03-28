@echo off
title Screen Recorder - Install Dependencies
echo ============================================
echo   Screen Recorder - Install Dependencies
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.9+
    echo         https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version
echo.

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

echo [OK] ffmpeg found
echo.

:: Install Python dependencies
echo Installing Python dependencies...
echo.
pip install -r requirements.txt
echo.

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    echo         Try running this script as administrator.
) else (
    echo ============================================
    echo   All dependencies installed successfully!
    echo   Run start.bat to launch the recorder.
    echo ============================================
)

echo.
pause

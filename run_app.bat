@echo off
title Client PDF Unlocker
cd /d "%~dp0"

echo ================================================================
echo                CLIENT PDF UNLOCKER - LAUNCHER
echo ================================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not found in system PATH.
    echo Please install Python 3.11 or newer from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Create virtual environment if not present
if not exist ".venv" (
    echo [*] Setting up local environment for first-time use...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment. Running with global python...
        python run.py
        pause
        exit /b
    )
)

:: Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: Run launcher script
python run.py

if %errorlevel% neq 0 (
    echo.
    echo [!] Server exited with an error.
    pause
)

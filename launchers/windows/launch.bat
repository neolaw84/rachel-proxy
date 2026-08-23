@echo off
setlocal enabledelayedexpansion

:: Resolve project root directory whether launched from root or launchers\windows\
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%pyproject.toml" (
    cd /d "%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%..\..\pyproject.toml" (
    cd /d "%SCRIPT_DIR%..\.."
) else (
    cd /d "%SCRIPT_DIR%"
)

:: Find available Python 3
set "PYTHON_EXE="
where py.exe >nul 2>&1
if %errorlevel% equ 0 (
    py -3.12 -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=py -3.12"
    ) else (
        py -3 -c "import sys" >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=py -3"
        )
    )
)
if "%PYTHON_EXE%"=="" (
    where python.exe >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo Error: Python is not installed or not added to PATH.
    echo Please install Python 3.12 or newer: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check if venv exists and is bootstrapped
if not exist "venv\Scripts\python.exe" (
    echo First-time setup: Creating virtual environment in .\venv...
    %PYTHON_EXE% -m venv venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Installing RACHEL proxy and dependencies...
    venv\Scripts\pip.exe install --upgrade pip
    venv\Scripts\pip.exe install -e .
    if %errorlevel% neq 0 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=src;%PYTHONPATH%"

echo Starting RACHEL Proxy...
powershell -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -Command "Start-Process venv\Scripts\python.exe -ArgumentList '-m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000' -WindowStyle Hidden"

timeout /t 2 /nobreak >nul
start http://localhost:8000


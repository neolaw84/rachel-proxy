@echo off
setlocal enabledelayedexpansion
title RACHEL Proxy (http://localhost:8000)

:: Resolve project root directory whether launched from root or launchers\windows\
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%pyproject.toml" (
    cd /d "%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%..\..\pyproject.toml" (
    cd /d "%SCRIPT_DIR%..\.."
) else (
    cd /d "%SCRIPT_DIR%"
)

:: Find standalone executable
set "EXEC_PATH="
if exist "bin\rachel-proxy\rachel-proxy.exe" (
    set "EXEC_PATH=bin\rachel-proxy\rachel-proxy.exe"
) else if exist "bin\rachel-proxy.exe" (
    set "EXEC_PATH=bin\rachel-proxy.exe"
) else if exist "rachel-proxy.exe" (
    set "EXEC_PATH=rachel-proxy.exe"
) else if exist "python\python.exe" (
    set "EXEC_PATH=python\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "EXEC_PATH=venv\Scripts\python.exe"
)

if "%EXEC_PATH%"=="" (
    echo [ERROR] RACHEL standalone executable not found.
    echo Please ensure the release package was extracted completely.
    pause
    exit /b 1
)

echo ================================================================
echo   RACHEL Proxy (Single-Tenant Desktop)
echo   Local URL : http://localhost:8000
echo ================================================================
echo.
echo   * Keep this window open while using RACHEL.
echo   * To stop the proxy, press Ctrl+C or simply close this window.
echo.

:: Launch browser in parallel
start "" http://localhost:8000

:: Run proxy attached in foreground
if "%EXEC_PATH%"=="venv\Scripts\python.exe" (
    "%EXEC_PATH%" -m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000
) else if "%EXEC_PATH%"=="python\python.exe" (
    "%EXEC_PATH%" -m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000
) else (
    "%EXEC_PATH%"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] RACHEL Proxy stopped with exit code %ERRORLEVEL%.
    pause
)

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
    echo Error: RACHEL standalone executable not found.
    echo Please ensure the release package was extracted completely.
    pause
    exit /b 1
)

echo Starting RACHEL Proxy...
if "%EXEC_PATH%"=="venv\Scripts\python.exe" (
    powershell -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -Command "Start-Process '%EXEC_PATH%' -ArgumentList '-m uvicorn rachel.proxy:app --host 0.0.0.0 --port 8000' -WindowStyle Hidden"
) else (
    powershell -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -Command "Start-Process '%EXEC_PATH%' -WindowStyle Hidden"
)

timeout /t 2 /nobreak >nul
start http://localhost:8000



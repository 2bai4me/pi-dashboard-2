@echo off
REM ===============================================================
REM  PI Dashboard 2.0 - Starter
REM  Prueft ob Frontend/Backend laufen, startet sie ggf. und oeffnet Browser
REM  Stand: 17.06.2026
REM  Wichtig:
REM   1. Reine ASCII-Datei (kein UTF-8 Box-Drawing, sonst
REM      interpretiert cmd die Sonderzeichen als Befehle).
REM   2. Funktionen (Labels) stehen IMMER am Dateiende,
REM      sonst entsteht eine Endlos-Rekursion, wenn der
REM      Parser ueber das Label im Hauptfluss laeuft.
REM ===============================================================

setlocal enabledelayedexpansion
chcp 65001 >nul
title PI Dashboard 2.0 - Starter

REM -- Konfiguration ------------------------------------------------
set "PROJECT_DIR=D:\Entwicklung\PI-Dashboard 2"
set "FRONTEND_PORT=5181"
set "BACKEND_PORT_1=9220"
set "BACKEND_PORT_2=9221"
set "FRONTEND_URL=http://127.0.0.1:5181/"

REM -- Header -------------------------------------------------------
echo.
echo =============================================================
echo              PI Dashboard 2.0 - Starter
echo              Stand: 17.06.2026
echo =============================================================
echo.

REM -- 1) FRONTEND pruefen -----------------------------------------
echo [1/3] Pruefe Frontend (Port %FRONTEND_PORT%)...
call :check_health "http://127.0.0.1:%FRONTEND_PORT%/"
if %ERRORLEVEL%==0 (
    echo       [OK] Frontend laeuft bereits auf %FRONTEND_URL%
) else (
    echo       [!] Frontend laeuft nicht. Starte Vite Dev-Server...
    cd /d "%PROJECT_DIR%\frontend"
    if not exist "node_modules" (
        echo       [X] node_modules fehlt! Bitte erst "npm install" ausfuehren.
        pause
        exit /b 1
    )
    start "PI Dashboard Frontend" /MIN cmd /c "npm run dev"
    echo       ... warte 5s auf Vite-Start ...
    timeout /t 5 /nobreak >nul
    call :check_health "http://127.0.0.1:%FRONTEND_PORT%/"
    if !ERRORLEVEL!==0 (
        echo       [OK] Frontend gestartet
    ) else (
        echo       [X] Frontend konnte nicht gestartet werden. Pruefe Logs.
        pause
        exit /b 1
    )
)
echo.

REM -- 2) BACKEND pruefen ------------------------------------------
echo [2/3] Pruefe Backend (Port %BACKEND_PORT_1%)...
call :check_health "http://127.0.0.1:%BACKEND_PORT_1%/api/health"
if %ERRORLEVEL%==0 (
    echo       [OK] Backend laeuft bereits auf Port %BACKEND_PORT_1%
) else (
    echo       [!] Backend laeuft nicht. Pruefe Python-Umgebung...
    if not exist "%PROJECT_DIR%\backend\.venv" (
        echo       [X] Virtuelle Umgebung fehlt: %PROJECT_DIR%\backend\.venv
        echo          Bitte erst einrichten: cd backend ^&^& python -m venv .venv
        pause
        exit /b 1
    )
    start "PI Dashboard Backend" /MIN cmd /c "cd /d %PROJECT_DIR%\backend ^&^& .venv\Scripts\activate ^&^& uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT_1%"
    echo       ... warte 8s auf Uvicorn-Start ...
    timeout /t 8 /nobreak >nul
    call :check_health "http://127.0.0.1:%BACKEND_PORT_1%/api/health"
    if !ERRORLEVEL!==0 (
        echo       [OK] Backend gestartet
    ) else (
        echo       [X] Backend konnte nicht gestartet werden. Pruefe Logs.
        pause
        exit /b 1
    )
)
echo.

REM -- 3) BROWSER oeffnen ------------------------------------------
echo [3/3] Oeffne Browser...
echo       URL: %FRONTEND_URL%
start "" "%FRONTEND_URL%"
echo.
echo =============================================================
echo   PI Dashboard 2.0 laeuft!
echo.
echo   Frontend:  %FRONTEND_URL%
echo   API-Docs:  http://127.0.0.1:%BACKEND_PORT_1%/docs
echo.
echo   Zum Beenden der Services: Task-Manager ^> alle 'node.exe'
echo   und 'python.exe' (uvicorn) beenden.
echo =============================================================
echo.
timeout /t 3 /nobreak >nul
exit /b 0

REM =================================================================
REM  FUNKTIONEN (muss am Dateiende stehen, sonst Selbst-Rekursion!)
REM =================================================================

:check_health
REM Prueft HTTP-URL. Gibt 0 zurueck bei HTTP 200, sonst 1.
set "URL=%~1"
curl -s -o nul -w "%%{http_code}" --max-time 2 "%URL%" 2>nul > "%TEMP%\httpcode.txt"
set /p HTTP_CODE=<"%TEMP%\httpcode.txt"
del "%TEMP%\httpcode.txt" 2>nul
if "%HTTP_CODE%"=="200" exit /b 0
exit /b 1

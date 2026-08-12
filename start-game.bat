@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Steel Front LAN Server

cd /d "%~dp0"
if errorlevel 1 (
  echo [ERROR] Cannot open the game folder:
  echo         %~dp0
  echo.
  pause
  exit /b 1
)

rem 端口可在命令行覆盖，例如：start-game.bat 8090
rem 8080 在装了 WSL2 / Hyper-V / Docker 的机器上常被系统预留（bind 报 WinError
rem 10013），所以默认改用高位端口。换端口后记得同步防火墙规则和其他玩家的地址。
set "GAME_PORT=18081"
if not "%~1"=="" set "GAME_PORT=%~1"
set "PORT=%GAME_PORT%"
set "PYTHONIOENCODING=utf-8"
set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python36\python.exe"

echo.
echo ==========================================================
echo   STEEL FRONT - LAN GAME SERVER
echo   Local address: http://127.0.0.1:%GAME_PORT%
echo   Keep this window open while playing.
echo   Press Ctrl+C or close this window to stop the server.
echo   Change port:   start-game.bat 8090
echo ==========================================================
echo.

if exist "%PYTHON_EXE%" goto run_known_python

where py.exe >nul 2>nul
if not errorlevel 1 goto run_python_launcher

where python.exe >nul 2>nul
if not errorlevel 1 goto run_path_python

echo [ERROR] Python 3 was not found.
echo Install Python 3 and enable "Add Python to PATH", then retry.
goto failed

:run_known_python
echo [INFO] Python: %PYTHON_EXE%
"%PYTHON_EXE%" "%~dp0server.py"
goto finished

:run_python_launcher
echo [INFO] Python: Windows Python Launcher
py.exe -3 "%~dp0server.py"
goto finished

:run_path_python
echo [INFO] Python: system PATH
python.exe "%~dp0server.py"
goto finished

:finished
set "SERVER_EXIT=%ERRORLEVEL%"
echo.
if not "%SERVER_EXIT%"=="0" (
  echo [ERROR] Server exited with code %SERVER_EXIT%.
  echo Check the error message above.
) else (
  echo [INFO] Server stopped normally.
)
echo.
pause
exit /b %SERVER_EXIT%

:failed
echo.
pause
exit /b 1

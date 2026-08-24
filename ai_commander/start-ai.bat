@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Steel Front LAN Server (AI Commander)

rem 进仓库根目录：本脚本在 ai_commander\ 下，服务器代码在上一层
cd /d "%~dp0.."
if errorlevel 1 (
  echo [ERROR] Cannot open the game folder:
  echo         %~dp0..
  echo.
  pause
  exit /b 1
)

rem 端口可在命令行覆盖，例如：start-ai.bat 8090
set "GAME_PORT=18081"
if not "%~1"=="" set "GAME_PORT=%~1"
set "PORT=%GAME_PORT%"
set "PYTHONIOENCODING=utf-8"

echo.
echo ==========================================================
echo   STEEL FRONT - LAN SERVER + AI COMMANDER
echo   Local address: http://127.0.0.1:%GAME_PORT%
echo   The AI will ask for an LLM API key at startup.
echo   Just press Enter to skip - it plays fine on templates.
echo ==========================================================
echo.

where py.exe >nul 2>nul
if not errorlevel 1 goto run_python_launcher

where python.exe >nul 2>nul
if not errorlevel 1 goto run_path_python

set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python36\python.exe"
if exist "%PYTHON_EXE%" goto run_known_python

echo [ERROR] Python 3 was not found.
echo Install Python 3 and enable "Add Python to PATH", then retry.
goto failed

:run_known_python
echo [INFO] Python: %PYTHON_EXE%
"%PYTHON_EXE%" "ai_commander\start.py"
goto finished

:run_python_launcher
echo [INFO] Python: Windows Python Launcher
py.exe -3 "ai_commander\start.py"
goto finished

:run_path_python
echo [INFO] Python: system PATH
python.exe "ai_commander\start.py"
goto finished

:finished
set "SERVER_EXIT=%ERRORLEVEL%"
echo.
if not "%SERVER_EXIT%"=="0" (
  echo [ERROR] Server exited with code %SERVER_EXIT%.
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

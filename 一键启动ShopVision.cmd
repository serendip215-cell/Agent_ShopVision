@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Agent ShopVision 一键启动
cd /d "%~dp0"

set "ROOT=%~dp0"
set "START_SCRIPT=%ROOT%scripts\start_all.py"
set "VENV_PY=%ROOT%webapp\backend\.venv\Scripts\python.exe"
set "PY_EXE="
set "USE_PY_LAUNCHER=0"
set "EXIT_CODE=0"

if not exist "%START_SCRIPT%" goto :missing_script

rem 1) 优先使用项目自带后端虚拟环境（无需配置系统 PATH，彻底绕开微软商店空壳别名）
if exist "%VENV_PY%" (
    set "PY_EXE=%VENV_PY%"
    goto :run_exe
)

rem 2) 若尚未创建 .venv，则尝试 Windows Python 启动器 py -3
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "USE_PY_LAUNCHER=1"
        goto :run_launcher
    )
)

rem 3) 再从 PATH 中查找真实 python.exe（自动过滤 Microsoft\WindowsApps 空壳）
for /f "delims=" %%i in ('where python 2^>nul') do call :try_python "%%~i"
if defined PY_EXE goto :run_exe

echo.
echo [错误] 未找到可用的 Python 3 环境。
echo        请先安装 Python 3.11 或 3.12（勾选 Add python.exe to PATH）：
echo        https://www.python.org/downloads/
echo.
set "EXIT_CODE=1"
goto :finish

:try_python
if defined PY_EXE goto :eof
echo %~1 | find /i "WindowsApps" >nul
if not errorlevel 1 goto :eof
"%~1" -c "import sys" >nul 2>nul
if errorlevel 1 goto :eof
set "PY_EXE=%~1"
goto :eof

:missing_script
echo [错误] 找不到启动脚本：%START_SCRIPT%
set "EXIT_CODE=1"
goto :finish

:run_exe
"%PY_EXE%" "%START_SCRIPT%" %*
set "EXIT_CODE=%errorlevel%"
goto :finish

:run_launcher
py -3 "%START_SCRIPT%" %*
set "EXIT_CODE=%errorlevel%"
goto :finish

:finish
if "%SHOPVISION_NO_PAUSE%"=="1" goto :exit_now
if not "%EXIT_CODE%"=="0" goto :do_pause

rem 判断是否为资源管理器双击启动（无参数且 CMDCMDLINE 含 /c）
if not "%~1"=="" goto :exit_now
set "IS_DOUBLE_CLICK=0"
setlocal EnableDelayedExpansion
set "CMD_TMP=!CMDCMDLINE!"
if /i not "!CMD_TMP:/c=!"=="!CMD_TMP!" (
    endlocal
    set "IS_DOUBLE_CLICK=1"
) else (
    endlocal
)
if "%IS_DOUBLE_CLICK%"=="1" goto :do_pause
goto :exit_now

:do_pause
echo.
pause

:exit_now
endlocal & exit /b %EXIT_CODE%

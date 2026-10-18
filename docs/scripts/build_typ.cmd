@echo off
rem Windows 入口：转调 build_typ.sh（需要 Git Bash，随 Git for Windows 附带）。
rem 用法: 双击本文件，或在 cmd/PowerShell 中: build_typ.cmd [编号或文件名]
setlocal
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "BASH_EXE="

rem 1) 常见安装位置
set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if exist "%BASH_EXE%" goto :run
set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
if exist "%BASH_EXE%" goto :run
set "BASH_EXE=%LocalAppData%\Programs\Git\bin\bash.exe"
if exist "%BASH_EXE%" goto :run

rem 2) 从 PATH 里的 git.exe 推导 Git for Windows 的 bash.exe 位置
set "GIT_EXE="
for /f "delims=" %%i in ('where git 2^>nul') do (
  set "GIT_EXE=%%i"
  goto :gotgit
)
if not defined GIT_EXE goto :lastresort

:gotgit
set "BASH_EXE=%GIT_EXE:\cmd\git.exe=\bin\bash.exe%"
if /i not "%BASH_EXE%"=="%GIT_EXE%" if exist "%BASH_EXE%" goto :run
set "BASH_EXE=%GIT_EXE:\mingw64\bin\git.exe=\bin\bash.exe%"
if /i not "%BASH_EXE%"=="%GIT_EXE%" if exist "%BASH_EXE%" goto :run

:lastresort
rem 3) 最后才用 PATH 里的 bash（注意：可能是 WSL 的 bash，会报 No such file）
where bash >nul 2>nul
if not errorlevel 1 set "BASH_EXE=bash"
if defined BASH_EXE goto :run

echo 未找到 Git Bash，请先安装 Git for Windows: https://git-scm.com/download/win
exit /b 1

:run
rem bash 会把反斜杠当转义符，路径转成正斜杠再传
set "SCRIPT_SH=%SCRIPT_DIR:\=/%build_typ.sh"
"%BASH_EXE%" "%SCRIPT_SH%" %*
if "%~1"=="" pause
endlocal

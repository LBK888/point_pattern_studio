@echo off
rem ============================================================
rem  Point Pattern Studio launcher (Windows)
rem  NOTE: this file must keep Windows CRLF line endings.
rem  With LF endings + "chcp 65001" + Chinese text, cmd.exe
rem  mis-splits the lines and never reaches "app.py" (v1.0 bug).
rem ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem Prefer the py launcher: a bare "python" may be the Microsoft Store stub.
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] 找不到 Python。請到 https://www.python.org/downloads/ 安裝 Python 3.10 以上版本，
  echo         安裝時請勾選 "Add python.exe to PATH"，然後重新執行本檔。
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo 使用 %%v

rem Install packages only when something is missing (faster start; works offline afterwards).
%PY% -c "import numpy, scipy, PIL, cv2, skimage, matplotlib, PyQt6" >nul 2>&1
if errorlevel 1 (
  echo 正在安裝必要套件（第一次約需數分鐘）...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Python 套件安裝失敗，請檢查 Python 3.10+ 與網路連線。
    pause
    exit /b 1
  )
)

echo 啟動 Point Pattern Studio ...
%PY% app.py
if errorlevel 1 (
  echo.
  echo [ERROR] 程式異常結束，錯誤訊息如上。
  pause
  exit /b 1
)
endlocal

@echo off
chcp 65001 >nul
title HE THONG GIAM SAT CHAT LUONG NUOC - DE TAI 51
color 0b

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

cd /d "%~dp0"

set "PY_EXE=C:\Users\Admin\python311\python.exe"
if not exist "%PY_EXE%" (
    if exist "C:\laragon\bin\python\python-3.13\python.exe" (
        set "PY_EXE=C:\laragon\bin\python\python-3.13\python.exe"
    ) else (
        set "PY_EXE=python"
    )
)

echo =====================================================================
echo    HE THONG GIAM SAT CHAT LUONG NUOC SONG, HO - DE TAI 51
echo    Mon hoc: Internet of Things (IoT) - GVHD: Dinh Huy Hoang
echo    Tieu chuan: QCVN 08:2023/BTNMT
echo =====================================================================
echo.
echo [*] Dang su dung Python tai: %PY_EXE%
echo [*] Dang khoi dong Web Server tai: http://localhost:5000
echo [*] Vui long mo trinh duyet truy cap: http://localhost:5000
echo [*] Nhan Ctrl+C de dung server.
echo =====================================================================
echo.

"%PY_EXE%" app.py

if errorlevel 1 (
    echo.
    echo [!] Server da dung lai.
    pause
)

@echo off
chcp 65001 >nul
title EIGHT - Hệ Thống Giám Sát Chất Lượng Nước (Đề tài 51 - Nhóm 08)
cls
echo.
echo  ============================================================
echo   EIGHT - HE THONG GIAM SAT CHAT LUONG NUOC SONG, HO
echo   De tai 51 - Nhom 08  --  QCVN 08:2023/BTNMT
echo  ============================================================
echo.
echo  [*] Dang kiem tra Python...

where python >nul 2>&1
if %errorlevel% == 0 (
    echo  [OK] Tim thay Python: 
    python --version
    echo.
    echo  [*] Dang khoi dong server...
    echo  [*] Mo trinh duyet va truy cap: http://localhost:5000
    echo.
    cd /d "%~dp0"
    python app.py
) else (
    echo  [LOI] Khong tim thay Python trong PATH!
    echo  Vui long cai Python 3.x va thu lai.
    pause
)

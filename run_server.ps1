# =====================================================================
# Script khởi chạy Server IoT Đề tài 51 (Nhóm 08)
# =====================================================================
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   HỆ THỐNG GIÁM SÁT CHẤT LƯỢNG NƯỚC SÔNG, HỒ - ĐỀ TÀI 51" -ForegroundColor Green
Write-Host "   Môn học: Internet of Things (IoT) - GVHD: Đinh Huy Hoàng" -ForegroundColor White
Write-Host "   Tiêu chuẩn: QCVN 08:2023/BTNMT" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Cyan

$pyPath = "python"
$pyCheck = Start-Process -FilePath "python" -ArgumentList "--version" -NoNewWindow -PassThru -Wait -ErrorAction SilentlyContinue

if ($null -eq $pyCheck -or $pyCheck.ExitCode -ne 0) {
    if (Test-Path "C:\Users\Admin\python311\python.exe") {
        $pyPath = "C:\Users\Admin\python311\python.exe"
    } elseif (Test-Path "C:\laragon\bin\python\python-3.13\python.exe") {
        $pyPath = "C:\laragon\bin\python\python-3.13\python.exe"
    } else {
        Write-Host "[!] Không tìm thấy Python khả dụng!" -ForegroundColor Red
        Read-Host "Nhấn Enter để thoát..."
        exit 1
    }
}

Write-Host "[*] Python thực thi: $pyPath" -ForegroundColor DarkCyan
Write-Host "[*] Đang khởi động Web Server: http://localhost:5000" -ForegroundColor Green
Write-Host "[*] Nhấn Ctrl+C để dừng server.`n" -ForegroundColor Gray

& $pyPath app.py

# 🌊 EIGHT — Hệ Thống Giám Sát Chất Lượng Nước Sông, Hồ

**Đề tài 51 – Nhóm 08 | GVHD: ThS. Đinh Huy Hoàng | Môn: Internet of Things**

Hệ thống IoT giám sát chất lượng nước sông, hồ theo thời gian thực, so sánh tự động với **QCVN 08:2023/BTNMT** và tính toán chỉ số **WQI (Water Quality Index)** bằng phương pháp nội suy tuyến tính + q_min Gate.

**Stack:** `ESP32 Wokwi` → `MQTT HiveMQ` → `Python Flask` → `SSE` → `SQLite WAL` → `Chart.js`

---

## 📁 Cấu trúc dự án

```
demo/
├── app.py               # Backend Flask: MQTT, WQI, cảnh báo, API, SSE, CSV export
├── sketch.ino           # Firmware C++ ESP32 Wokwi (5 cảm biến ảo, MQTT failover)
├── diagram.json         # Sơ đồ kết nối phần cứng Wokwi
├── libraries.txt        # Thư viện Arduino cần cài
├── test_system.py       # Bộ kiểm thử tự động 9 bài — chạy: python test_system.py
├── run_server.bat       # Script 1-click khởi chạy server Windows
├── water_monitoring.db  # SQLite WAL: bảng tram, do_luong, canh_bao
├── templates/
│   └── index.html       # Web Dashboard EIGHT (SSE realtime, Chart.js, WQI Breakdown)
└── README.md
```

---

## 🚀 Khởi chạy hệ thống

### Cách 1: 1-Click (Khuyên dùng khi demo)
Double-click file **`run_server.bat`** → chờ console hiện `http://localhost:5000` → mở trình duyệt.

### Cách 2: Terminal
```powershell
cd "d:\Năm 4\IoT\demo"
python app.py
```
Mở trình duyệt: **http://localhost:5000**

### Kiểm thử nhanh trước demo
```powershell
python test_system.py   # Phải đạt 9/9 PASS
```

---

## 🔌 Mô phỏng ESP32 trên Wokwi

1. Truy cập **https://wokwi.com** → Đăng nhập → New Project → ESP32 (Arduino)
2. Dán nội dung `sketch.ino` vào tab **sketch.ino**
3. Dán nội dung `diagram.json` vào tab **diagram.json**
4. Thêm thư viện (tab **libraries.txt**):
   ```
   PubSubClient
   DHT sensor library
   Adafruit Unified Sensor
   ArduinoJson
   ```
5. Nhấn **▶ Play** → Mở Serial Monitor xem dữ liệu gửi mỗi 5 giây

### Phím tắt Serial Monitor Wokwi (kịch bản nhanh)
| Phím | Kịch bản |
|---|---|
| `1` | Nước đạt chuẩn QCVN 08 (WQI ~100) |
| `2` | Ô nhiễm axit (pH = 4.1) |
| `3` | Mưa lũ nước đục (TSS > 100, Mực nước 2.85m) |
| `4` | Xả thải nhiệt (Nhiệt độ 38.5°C) |
| `0` | Quay lại đọc từ núm biến trở xoay |

---

## 📊 Quy chuẩn & Ngưỡng cảnh báo (QCVN 08:2023/BTNMT)

| Chỉ tiêu | Ngưỡng Sông | Ngưỡng Hồ | Cảm biến giả lập |
|---|---|---|---|
| **pH** | 6.0 – 8.5 | 6.0 – 8.5 | Biến trở GPIO 34 (0–14) |
| **DO** | ≥ 5.0 mg/L | ≥ 5.0 mg/L | Biến trở GPIO 35 (0–10 mg/L) |
| **TSS** | ≤ 100 mg/L | ≤ 15 mg/L | Biến trở GPIO 32 (0–200 NTU × 1.2) |
| **Nhiệt độ** | 24 – 32 °C | 24 – 32 °C | DHT22 GPIO 4 |
| **Mực nước** | 0.5 – 2.5 m | 0.5 – 2.5 m | HC-SR04 GPIO 5/18 |

---

## 🧮 Thuật toán WQI — 3 bước

```
Bước 1 — Nội suy tuyến tính:
  q_pH, q_DO, q_TSS, q_Temp ∈ [0, 100]
  (Dùng bảng neo điểm + nội suy, không nhảy bậc đột ngột)

Bước 2 — Tổng hợp trọng số:
  WQI_raw = 0.35×q_DO + 0.30×q_pH + 0.25×q_TSS + 0.10×q_Temp

Bước 3 — q_min Gate (Nguyên lý yếu tố giới hạn):
  q_min = min(q_pH, q_DO, q_TSS, q_Temp)
  • q_min = 0   → WQI = 0            (Độc hại tuyệt đối)
  • q_min < 20  → WQI = min(raw, q_min + 5)
  • q_min < 45  → WQI = min(raw, q_min + 15)
  • Còn lại     → WQI = WQI_raw
```

| WQI | Mức | Ý nghĩa |
|---|---|---|
| ≥ 90 | Rất tốt (A) | Dùng cho sinh hoạt |
| 75–89 | Tốt (B) | Sinh hoạt qua xử lý |
| 50–74 | Trung bình | Nông nghiệp, tưới tiêu |
| 25–49 | Kém | Giao thông thủy |
| < 25 | Ô nhiễm nặng | Nguy hiểm |

### Debug WQI trực tiếp trên trình duyệt
```
http://localhost:5000/api/wqi/explain?ph=5.5&do=3.0&tss=120&temp=35&loai=Sông
```
→ Trả về JSON chi tiết từng bước: q_pH, q_DO, q_TSS, q_Temp, gate áp dụng, WQI cuối.

---

## 🚦 Logic cảnh báo 3 cấp

```
Vi phạm 1 lần   → 🟡 WARNING  (Cảnh báo nhẹ)
Vi phạm 3 lần   → 🔴 CRITICAL (Báo động đỏ — ghi DB, Telegram nếu cấu hình)
Sạch 1 lần      → WARNING → NORMAL   (phục hồi nhanh)
Sạch 2 lần liên → CRITICAL → NORMAL  (cần 2 lần xác nhận)
```

---

## 🎬 Kịch bản Demo — 7 kịch bản có sẵn trên Dashboard

| # | Kịch bản | Trigger | WQI dự kiến | Mức |
|---|---|---|---|---|
| 1 | Nước đạt chuẩn | `normal` | ~96–100 | 🟦 Rất tốt |
| 2 | Ô nhiễm axit xả thải | `acid_waste` | ~8–13 | 🔴 Ô nhiễm nặng |
| 3 | Nước đục sau mưa lũ | `dirty_runoff` | ~40–50 | 🟡 Kém |
| 4 | Cảnh báo lũ lụt | `flood` | ~45–55 | 🟡 Kém |
| 5 | Cảnh báo khô hạn | `drought` | ~70–80 | 🟠 Trung bình |
| 6 | Xả thải nhiệt công nghiệp | `hot_water` | ~50–60 | 🟠 Trung bình |
| 7 | Hồ phú dưỡng (tảo nở hoa) | `lake_algae` | ~15–25 | 🔴 Ô nhiễm nặng |

---

## 🛠️ Xử lý sự cố khi demo

| Tình huống | Giải pháp |
|---|---|
| **Mạng trường chặn cổng 1883** | Dùng 4G phát WiFi, hoặc bấm nút **Giả Lập** trên Dashboard |
| **Wokwi không kết nối HiveMQ** | ESP32 tự chuyển sang `test.mosquitto.org` sau 4 lần thất bại |
| **Trang trắng / cache cũ** | `Ctrl + Shift + R` (Hard Reload) |
| **WQI hiện sai** | Chạy `python test_system.py` kiểm tra — phải 9/9 PASS |
| **Muốn kiểm tra logic WQI** | Gõ `/api/wqi/explain?ph=...` lên trình duyệt |
| **Demo không có Wokwi** | Dùng 7 nút kịch bản trong tab **Giả Lập Kịch Bản** |

---

## 📡 API Endpoints

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/` | Web Dashboard |
| GET | `/api/stations` | Danh sách trạm + trạng thái |
| GET | `/api/stations/<id>/history` | Lịch sử đo đạc (limit=50) |
| GET | `/api/alerts` | Nhật ký cảnh báo |
| POST | `/api/alerts/clear` | Xóa nhật ký cảnh báo |
| POST | `/api/station/<id>/simulate` | Kích hoạt kịch bản giả lập |
| GET | `/api/wqi/explain` | Debug WQI chi tiết từng bước |
| GET | `/api/export/csv?type=do_luong` | Xuất CSV dữ liệu đo |
| GET | `/api/export/csv?type=canh_bao` | Xuất CSV cảnh báo |
| POST | `/reset` | Reset bộ đếm vi phạm |
| GET | `/stream` | SSE realtime stream |

---

*Nhóm 08 — Đề tài 51 — GVHD: ThS. Đinh Huy Hoàng*

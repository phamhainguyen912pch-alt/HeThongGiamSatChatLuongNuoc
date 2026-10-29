# 🌊 Hệ Thống Giám Sát Chất Lượng Nước Sông, Hồ

**Đề tài 51 – Nhóm 08 | GVHD: ThS. Đinh Huy Hoàng**  
Hệ thống IoT giám sát chất lượng nước sông, hồ theo tiêu chuẩn **QCVN 08:2023/BTNMT** và tính toán chỉ số chất lượng nước tổng hợp **WQI (Water Quality Index)** theo thời gian thực.  
Công nghệ sử dụng: **ESP32 (mô phỏng Wokwi) + MQTT (HiveMQ / Mosquitto) + Python Flask + SSE + SQLite + Chart.js**.

---

## 📋 Mục lục

1. [Cấu trúc dự án](#-cấu-trúc-dự-án)
2. [Cách chạy nhanh nhất (Khuyên dùng)](#-cách-chạy-nhanh-nhất-1-click)
3. [Mô phỏng phần cứng ESP32 trên Wokwi](#-mô-phỏng-phần-cứng-esp32-trên-wokwi)
4. [Các tính năng nâng cấp nổi bật](#-các-tính-năng-nâng-cấp-nổi-bật)
5. [Quy chuẩn QCVN 08:2023 & Chỉ số WQI](#-quy-chuẩn-qcvn-082023--chỉ-số-wqi)
6. [Kịch bản chi tiết khi Demo trước lớp](#-kịch-bản-chi-tiết-khi-demo-trước-lớp)
7. [Xử lý sự cố & Mẹo "cứu nguy" tại giảng đường](#-xử-lý-sự-cố--mẹo-cứu-nguy-tại-giảng-đường)

---

## 📁 Cấu trúc dự án

```
demo/
├── run_server.bat          # [MỚI] Script 1-click khởi chạy Server an toàn trên Windows
├── run_server.ps1          # [MỚI] Script PowerShell khởi chạy Server
├── test_system.py          # [MỚI] Script kiểm thử tự động toàn diện 9 bài test hệ thống
├── app.py                  # Backend Flask Server + MQTT Auto-failover + SSE + SQLite WAL + WQI
├── sketch.ino              # Firmware C++ cho ESP32 Wokwi (tự động chuyển broker dự phòng)
├── diagram.json            # Sơ đồ kết nối phần cứng và cảm biến ảo Wokwi
├── libraries.txt           # Danh sách thư viện Arduino cần nạp
├── water_monitoring.db     # SQLite database (bảng tram, do_luong, canh_bao)
├── templates/
│   └── index.html          # Web Dashboard Dark UI + Chart.js 5 chỉ tiêu + Web Audio + WQI
└── README.md               # Sổ tay hướng dẫn & kịch bản demo
```

---

## 🚀 Cách chạy nhanh nhất (1-Click)

### Cách 1: Dùng file `run_server.bat` (Khuyên dùng khi demo)
* Chỉ cần **nhấp đúp chuột (Double click)** vào file `run_server.bat`.
* File sẽ tự động nhận diện đường dẫn Python chuẩn trên máy bạn, kích hoạt CSDL và khởi động Server mà không sợ lỗi Windows execution alias.
* Sau khi cửa sổ console hiện:
  ```
  [*] Đang khởi động Web Server: http://localhost:5000
  ```
* Mở trình duyệt Web (Chrome / Edge / Firefox) và truy cập:
  ```
  http://localhost:5000
  ```

### Cách 2: Chạy thủ công qua terminal
```powershell
python app.py
# Hoặc nếu Python mặc định bị alias Windows Store chặn:
& "C:\Users\Admin\python311\python.exe" app.py
```

---

## 🔌 Mô phỏng phần cứng ESP32 trên Wokwi

1. Truy cập **https://wokwi.com** → Đăng nhập → **New Project** → Chọn **ESP32 (Arduino)**.
2. **Tab `sketch.ino`**: Dán toàn bộ nội dung file `sketch.ino`.
3. **Tab `diagram.json`**: Dán toàn bộ nội dung file `diagram.json`.
4. **Tab `libraries.txt`**: Thêm các thư viện:
   ```
   PubSubClient
   DHT sensor library
   Adafruit Unified Sensor
   ArduinoJson
   ```
5. Nhấn nút **Play (▶)** để bắt đầu chạy mô phỏng.
6. Mở **Serial Monitor** trên Wokwi để xem dữ liệu xuất ra mỗi 5 giây.

---

## ✨ Các tính năng nâng cấp nổi bật

1. **Biểu đồ thời gian thực trực quan hóa cả 5 chỉ tiêu:**
   * **Biểu đồ Hóa sinh**: Đường xu hướng độ pH (6.0 - 8.5) và Oxy hòa tan DO (≥ 5.0 mg/L).
   * **Biểu đồ Vật lý & Môi trường**: Tổng chất rắn TSS (≤ 100 mg/L), Nhiệt độ nước (24 - 32°C) và Mực nước (0.5 - 2.5m).
2. **Chỉ số Chất lượng nước tổng hợp WQI (Water Quality Index):**
   * Tự động tính toán điểm số từ 0 đến 100 dựa theo trọng số tác động của các chỉ tiêu theo QCVN 08.
   * Phân cấp trực quan: Rất tốt (Mức A), Tốt (Mức B), Trung bình (Mức C), Kém (Mức D), Ô nhiễm nặng.
3. **Khả năng chịu lỗi và tự phục hồi cao (Auto-failover):**
   * Hỗ trợ tự động luân chuyển giữa Broker chính `broker.hivemq.com` và Broker dự phòng `test.mosquitto.org` ở cả ESP32 và Server Python.
   * CSDL SQLite chạy chế độ **WAL (Write-Ahead Logging)** kết hợp timeout 30s, chống 100% lỗi `database is locked`.
4. **Cảnh báo đa kênh:**
   * Banner cảnh báo động nhấp nháy trên Web Dashboard.
   * Còi âm thanh báo động thời gian thực (Web Audio Synthesizer, có nút bật/tắt âm thanh).
   * Hỗ trợ thông báo qua Telegram Bot khi có báo động đỏ `CRITICAL`.
5. **Xuất báo cáo CSV chuẩn Excel tiếng Việt:**
   * Xuất cả lịch sử đo đạc và lịch sử vi phạm, kèm mã UTF-8 BOM giúp mở trực tiếp trên Microsoft Excel không bị lỗi font tiếng Việt.

---

## 📊 Quy chuẩn QCVN 08:2023 & Chỉ số WQI

| Chỉ tiêu | Ngưỡng cho phép | Thang đo cảm biến mô phỏng | Ý nghĩa giám sát |
| :--- | :--- | :--- | :--- |
| **pH** | **6.0 – 8.5** | 0 – 14 (Biến trở GPIO 34) | Phát hiện nước bị chua/axit hoặc kiềm hóa |
| **Oxy hòa tan (DO)** | **≥ 5.0 mg/L** | 0 – 10 mg/L (Biến trở GPIO 32) | Đảm bảo hô hấp cho hệ sinh thái thủy sinh |
| **TSS / Độ đục** | **≤ 100 mg/L** (Sông) / **≤ 15** (Hồ) | 0 – 200 NTU (Biến trở GPIO 35) | Phát hiện nước đục, phù sa hoặc chất thải lơ lửng |
| **Nhiệt độ nước** | **24 – 32 °C** | 0 – 50 °C (DHT22 GPIO 4) | Phát hiện xả thải nhiệt bất thường |
| **Mực nước** | **0.5 – 2.5 m** | 0 – 3.0 m (HC-SR04 GPIO 5, 18) | Cảnh báo lũ lụt (> 2.5m) hoặc cạn kiệt (< 0.5m) |

---

## 🎬 Kịch bản chi tiết khi Demo trước lớp

### Bước 1: Giới thiệu kiến trúc tổng thể (1 phút)
* *"Kính thưa Thầy và các bạn, nhóm 08 thực hiện Đề tài 51 - Hệ thống IoT giám sát chất lượng nước sông, hồ theo QCVN 08:2023/BTNMT."*
* *"Hệ thống gồm 3 tầng: Tầng biên (Edge) là firmware ESP32 mô phỏng trên Wokwi kết nối 5 cảm biến ảo; Tầng truyền thông (Middleware) dùng giao thức MQTT qua Broker công khai với cơ chế tự động chuyển broker dự phòng; Tầng ứng dụng (Application) gồm Server Python Flask, CSDL SQLite WAL và Web Dashboard cập nhật thời gian thực bằng SSE."*

### Bước 2: Tình huống 1 – Nước đạt chuẩn an toàn (Bình thường)
* **Thao tác:** Trên Wokwi, để các biến trở ở mức chuẩn (pH ~ 7.2, DO ~ 6.5, NTU ~ 30, DHT22 ~ 28°C, Mực nước ~ 1.5m).
* **Thuyết minh:** *"Khi các chỉ tiêu nằm trong ngưỡng quy chuẩn, Dashboard hiển thị trạng thái xanh 'BÌNH THƯỜNG', chỉ số WQI đạt 95 - 100 điểm (Mức A/B - Rất tốt), biểu đồ vẽ đường ổn định."*

### Bước 3: Tình huống 2 – Cảnh báo nhẹ (Vàng: 1–2 lần vi phạm)
* **Thao tác:** Vặn biến trở **Pot pH** về mức thấp (~4.0) hoặc **Pot DO** về thấp (~2.0 mg/L).
* **Thuyết minh:** *"Khi phát hiện chỉ tiêu vượt ngưỡng lần thứ nhất hoặc thứ hai, hệ thống chưa vội báo động giả để tránh nhiễu cảm biến, mà kích hoạt trạng thái Cảnh báo nhẹ (Vàng) kèm số lần theo dõi 1/3, 2/3."*

### Bước 4: Tình huống 3 – Báo động đỏ (Đỏ: Vi phạm 3 lần liên tiếp)
* **Thao tác:** Giữ nguyên mức vi phạm qua 15 giây (3 chu kỳ gửi dữ liệu).
* **Thuyết minh:** *"Khi vi phạm liên tiếp 3 lần, hệ thống chính thức nâng lên mức BÁO ĐỘNG ĐỎ: banner đỏ nhấp nháy, phát còi âm thanh cảnh báo, tự động ghi nhận bản ghi vi phạm vào bảng `canh_bao` trong database."*

### Bước 5: Tình huống 4 – Tự phục hồi về Bình thường
* **Thao tác:** Xoay núm biến trở trở lại mức bình thường (pH ~ 7.0, DO ~ 6.5).
* **Thuyết minh:** *"Khi mẫu nước trở lại ngưỡng an toàn liên tục 2 lần đo, hệ thống tự động reset về trạng thái 'BÌNH THƯỜNG' mà không cần người vận hành phải can thiệp thủ công."*

### Bước 6: Tình huống 5 – Mô phỏng cảnh báo Lũ / Hạn hán bằng HC-SR04
* **Thao tác:** Click vào cảm biến HC-SR04 trên Wokwi, kéo thanh trượt khoảng cách ngắn lại (~10cm) để mực nước dâng > 2.5m -> Kích hoạt cảnh báo Lũ.

### Bước 7: Trình diễn các tính năng nâng cao (30 giây)
* Bấm chuyển đổi giữa **Trạm 1 (Sông)** và **Trạm 2 (Hồ Trị An)** -> giải thích cơ chế ngưỡng TSS tự động siết chặt từ 100 xuống 15 mg/L theo loại nguồn nước.
* Bấm nút **"Xuất CSV"** -> Tải file dữ liệu đo đạc và mở lên Excel hiển thị tiếng Việt hoàn hảo.

---

## 🛠️ Xử lý sự cố & Mẹo "cứu nguy" tại giảng đường

| Tình huống rủi ro | Nguyên nhân | Biện pháp giải quyết tức thời |
| :--- | :--- | :--- |
| **Mạng WiFi trường chặn cổng MQTT 1883** | Firewall của trường chặn port IoT ra ngoài | **Mở 4G điện thoại phát WiFi cho laptop kết nối**, hoặc dùng ngay nút **"Giả lập Demo"** có sẵn trên góc phải Dashboard. |
| **Trình duyệt không kết nối được** | Mở nhầm port Live Server (5500) | Truy cập đúng địa chỉ: `http://localhost:5000`. |
| **Trang web lưu cache cũ** | Trình duyệt giữ bộ nhớ đệm | Nhấn tổ hợp phím **`Ctrl + Shift + R`** (Hard Reload). |
| **Muốn kiểm thử nhanh trước khi vào phòng thi** | Cần kiểm tra toàn bộ code xem có lỗi cú pháp hay DB không | Mở terminal gõ: `python test_system.py` để chạy bộ 9 bài test tự động. |

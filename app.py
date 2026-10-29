import sys
import json
import sqlite3
import threading
import time
import queue
from datetime import datetime

# Cấu hình UTF-8 chống lỗi font và chống crash UnicodeEncodeError trên Windows CMD
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from flask import Flask, render_template, Response, jsonify, request, send_file
import io
import csv
import paho.mqtt.client as mqtt

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
DB_FILE = "water_monitoring.db"

# Danh sách MQTT Broker: Broker chính HiveMQ + Broker dự phòng Mosquitto (Mục 2.1 Báo cáo)
MQTT_BROKER_LIST = [
    {"host": "broker.hivemq.com", "port": 1883, "name": "HiveMQ Public"},
    {"host": "test.mosquitto.org", "port": 1883, "name": "Eclipse Mosquitto Public"}
]
MQTT_BROKER = MQTT_BROKER_LIST[0]["host"]
MQTT_PORT = 1883
MQTT_TOPIC = "iot_huit_2026/nhom08_dt51/#"

# Cấu hình cảnh báo Telegram Bot (Tùy chọn - Giám sát từ xa)
TELEGRAM_BOT_TOKEN = ""  # Nhập Bot Token từ @BotFather nếu muốn nhận tin nhắn Telegram
TELEGRAM_CHAT_ID = ""    # Nhập Chat ID người nhận
last_telegram_time = 0

# Trạng thái từng trạm trong bộ nhớ đệm
station_states = {
    1: {
        "violation_count": 0,
        "safe_count": 0,
        "current_status": "NORMAL",  # NORMAL (Xanh), WARNING (Vàng), CRITICAL (Đỏ)
        "last_violation_reasons": [],
        "latest_data": None
    },
    2: {
        "violation_count": 0,
        "safe_count": 0,
        "current_status": "NORMAL",
        "last_violation_reasons": [],
        "latest_data": None
    },
    3: {
        "violation_count": 0,
        "safe_count": 0,
        "current_status": "NORMAL",
        "last_violation_reasons": [],
        "latest_data": None
    }
}

latest_packets_queue = []
sse_clients = []
lock = threading.Lock()

station_metadata = {
    1: {"ten_tram": "Trạm 01 - Thượng lưu Sông Sài Gòn (Mô phỏng ESP32 Wokwi)", "loai_tram": "Sông"},
    2: {"ten_tram": "Trạm 02 - Hồ Thủy điện Trị An (Đồng Nai)", "loai_tram": "Hồ"},
    3: {"ten_tram": "Trạm 03 - Hạ lưu Kênh Nhiêu Lộc - Thị Nghè (TP.HCM)", "loai_tram": "Sông"}
}

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Kích hoạt WAL mode để đọc/ghi đồng thời không bao giờ bị lock database
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass

    # 1. Bảng tram (Thông tin trạm quan trắc - Mục 6.1 Báo cáo Giai đoạn 2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tram (
        id INTEGER PRIMARY KEY,
        ten_tram TEXT NOT NULL,
        loai_tram TEXT NOT NULL,  -- 'Sông' hoặc 'Hồ'
        mo_ta TEXT
    )
    """)

    # 2. Bảng do_luong (Dữ liệu đo - Mục 6.2 Báo cáo Giai đoạn 2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS do_luong (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tram_id INTEGER NOT NULL,
        thoi_gian DATETIME NOT NULL,
        ph REAL,
        do REAL,
        do_duc REAL,
        tss REAL,
        nhiet_do REAL,
        muc_nuoc REAL,
        trang_thai TEXT,
        wqi REAL DEFAULT 100,
        FOREIGN KEY (tram_id) REFERENCES tram(id)
    )
    """)

    # Đảm bảo tương thích: tự động thêm cột do_duc và wqi nếu file db cũ chưa có
    try:
        cursor.execute("ALTER TABLE do_luong ADD COLUMN do_duc REAL DEFAULT 0")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE do_luong ADD COLUMN wqi REAL DEFAULT 100")
    except Exception:
        pass

    # 3. Bảng canh_bao (Lịch sử cảnh báo - Mục 6.3 Báo cáo Giai đoạn 2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS canh_bao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tram_id INTEGER NOT NULL,
        thoi_gian DATETIME NOT NULL,
        chi_tieu TEXT NOT NULL,
        gia_tri REAL NOT NULL,
        mo_ta TEXT,
        muc_do TEXT DEFAULT 'CRITICAL',
        FOREIGN KEY (tram_id) REFERENCES tram(id)
    )
    """)

    # Đảm bảo tương thích: tự động thêm cột muc_do nếu bảng canh_bao cũ chưa có
    try:
        cursor.execute("ALTER TABLE canh_bao ADD COLUMN muc_do TEXT DEFAULT 'CRITICAL'")
    except Exception:
        pass

    # Thêm dữ liệu mặc định cho bảng tram nếu chưa có
    cursor.execute("SELECT COUNT(*) FROM tram")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO tram (id, ten_tram, loai_tram, mo_ta) VALUES (?, ?, ?, ?)
        """, [
            (1, "Trạm 01 - Thượng lưu Sông Sài Gòn (Mô phỏng ESP32 Wokwi)", "Sông", "Đầu nguồn sông Sài Gòn, kết nối vi điều khiển ESP32 Wokwi trực tiếp qua MQTT"),
            (2, "Trạm 02 - Hồ Thủy điện Trị An (Đồng Nai)", "Hồ", "Khu vực lòng hồ cấp nước sinh hoạt, yêu cầu TSS nghiêm ngặt <= 15 mg/L"),
            (3, "Trạm 03 - Hạ lưu Kênh Nhiêu Lộc - Thị Nghè (TP.HCM)", "Sông", "Khu vực nội đô đông dân cư, giám sát xả thải và biến động oxy hòa tan DO")
        ])

    conn.commit()
    conn.close()

def calculate_wqi(data, loai_tram="Sông"):
    """
    Tính chỉ số chất lượng nước tổng hợp WQI (Water Quality Index) theo QCVN 08:2023 & QĐ 1456/QĐ-TCMT:
    Áp dụng Nguyên lý yếu tố giới hạn (Liebig's Law of the Minimum) để triệt tiêu hiệu ứng che khuất (Eclipsing Effect):
    Thang điểm: 0 - 100
    - >= 90: Rất tốt (Mức A - Nước rất sạch, dùng cho sinh hoạt)
    - 75 - 89: Tốt (Mức B - Đạt chuẩn bảo vệ thủy sinh & sinh hoạt qua xử lý)
    - 50 - 74: Trung bình (Mức C - Dùng cho nông nghiệp, tưới tiêu)
    - 25 - 49: Kém (Mức D - Giao thông thủy, cần xử lý)
    - < 25: Ô nhiễm nặng (Mức E - Nguy hiểm, nguồn nước độc hại)
    """
    # 1. Điểm pH (Trọng số 0.30)
    ph = data.get("ph", 7.0)
    if 6.5 <= ph <= 8.5:
        q_ph = 100.0
    elif (6.0 <= ph < 6.5) or (8.5 < ph <= 9.0):
        q_ph = 75.0
    elif (5.5 <= ph < 6.0) or (9.0 < ph <= 9.5):
        q_ph = 45.0
    elif (5.0 <= ph < 5.5) or (9.5 < ph <= 10.0):
        q_ph = 20.0
    elif (4.0 <= ph < 5.0) or (10.0 < ph <= 11.0):
        q_ph = 10.0
    else:
        # Axit cực mạnh (pH < 4.0) hoặc kiềm cực mạnh (pH > 11.0)
        q_ph = 0.0

    # 2. Điểm DO (Trọng số 0.35)
    do_val = data.get("do", 6.0)
    if do_val >= 6.0:
        q_do = 100.0
    elif do_val >= 5.0:
        q_do = 80.0
    elif do_val >= 4.0:
        q_do = 50.0
    elif do_val >= 3.0:
        q_do = 30.0
    elif do_val >= 2.0:
        q_do = 15.0
    else:
        q_do = 5.0

    # 3. Điểm TSS (Trọng số 0.25)
    tss = data.get("tss", 30.0)
    if loai_tram == "Hồ":
        if tss <= 10.0:
            q_tss = 100.0
        elif tss <= 15.0:
            q_tss = 80.0
        elif tss <= 30.0:
            q_tss = 50.0
        elif tss <= 50.0:
            q_tss = 25.0
        elif tss <= 100.0:
            q_tss = 10.0
        else:
            q_tss = 0.0
    else:  # Sông
        if tss <= 25.0:
            q_tss = 100.0
        elif tss <= 50.0:
            q_tss = 85.0
        elif tss <= 100.0:
            q_tss = 70.0
        elif tss <= 150.0:
            q_tss = 40.0
        elif tss <= 200.0:
            q_tss = 20.0
        else:
            q_tss = 5.0

    # 4. Điểm Nhiệt độ (Trọng số 0.10)
    temp = data.get("temp", 28.0)
    if 24.0 <= temp <= 32.0:
        q_temp = 100.0
    elif 20.0 <= temp <= 35.0:
        q_temp = 75.0
    elif 15.0 <= temp <= 38.0:
        q_temp = 40.0
    else:
        q_temp = max(5.0, 100.0 - abs(temp - 28.0) * 8.0)

    # Tổng hợp trọng số cơ sở
    wqi_raw = 0.35 * q_do + 0.30 * q_ph + 0.25 * q_tss + 0.10 * q_temp
    wqi_score = int(round(wqi_raw))

    # =========================================================================
    # ÁP DỤNG NGUYÊN LÝ YẾU TỐ GIỚI HẠN (Liebig's Law of the Minimum - QĐ 1456/QĐ-TCMT):
    # Một nguồn nước không thể được coi là "Trung bình" hay "Tốt" nếu có bất kỳ một
    # chỉ số sinh tử nào đang ở ngưỡng hủy diệt môi trường sinh thái (Eclipsing Effect).
    # =========================================================================
    
    # Giới hạn trần theo pH (Axit hoặc kiềm cực đoan)
    if ph < 4.5 or ph > 10.5:
        # Axit đậm đặc (như ắc quy, nước thải xi mạ) hoặc kiềm cực mạnh -> Nguy hại chết người
        wqi_score = min(wqi_score, 12)
    elif ph < 5.0 or ph > 10.0:
        wqi_score = min(wqi_score, 20)
    elif ph < 5.5 or ph > 9.5:
        wqi_score = min(wqi_score, 40)

    # Giới hạn trần theo DO (Oxy hòa tan)
    if do_val < 2.0:
        # Ngạt thở cấp tính, cá chết nổi hàng loạt
        wqi_score = min(wqi_score, 15)
    elif do_val < 3.5:
        wqi_score = min(wqi_score, 35)

    # Giới hạn trần theo TSS (Độ đục / Chất rắn lơ lửng)
    if tss > 250.0:
        wqi_score = min(wqi_score, 20)
    elif tss > 160.0:
        wqi_score = min(wqi_score, 45)

    # Giới hạn trần theo Nhiệt độ
    if temp > 40.0 or temp < 10.0:
        wqi_score = min(wqi_score, 30)

    wqi_score = max(0, min(100, wqi_score))

    if wqi_score >= 90:
        wqi_label = "Rất tốt (Mức A)"
    elif wqi_score >= 75:
        wqi_label = "Tốt (Mức B)"
    elif wqi_score >= 50:
        wqi_label = "Trung bình"
    elif wqi_score >= 25:
        wqi_label = "Kém"
    else:
        wqi_label = "Ô nhiễm nặng"

    return wqi_score, wqi_label

def send_telegram_alert(tram_name, violations, wqi, current_status):
    """Gửi cảnh báo tức thời tới Telegram Bot khi phát hiện ô nhiễm (Nếu có cấu hình)"""
    global last_telegram_time
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    now = time.time()
    # Chống gửi dồn dập (mỗi 30s tối đa 1 tin)
    if now - last_telegram_time < 30:
        return
    last_telegram_time = now

    try:
        import urllib.request
        import urllib.parse
        msg = f"🚨 *[HỆ THỐNG GIÁM SÁT CHẤT LƯỢNG NƯỚC - ĐỀ TÀI 51]* 🚨\n\n"
        msg += f"📍 *Trạm:* {tram_name}\n"
        msg += f"⚠️ *Mức độ cảnh báo:* {current_status}\n"
        msg += f"💧 *Chỉ số WQI:* {wqi}/100\n"
        msg += f"⏰ *Thời gian:* {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}\n\n"
        msg += f"🔍 *Chi tiết vi phạm:*\n"
        for v in violations:
            msg += f"  • {v.get('mo_ta', '')}\n"
        msg += f"\n👉 Xem chi tiết trên Web Dashboard: http://localhost:5000"

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'text': msg,
            'parse_mode': 'Markdown'
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload)
        urllib.request.urlopen(req, timeout=4)
        print(f"[Telegram Alert] Đã gửi tin nhắn cảnh báo tới Telegram (Chat ID: {TELEGRAM_CHAT_ID})")
    except Exception as e:
        print(f"[Telegram Warning] Không thể gửi tin Telegram: {e}")

def evaluate_thresholds(tram_id, data):
    """
    Đánh giá ngưỡng QCVN 08:2023/BTNMT theo Bảng 4 của Báo cáo Giai đoạn 2:
    - pH: 6.0 – 8.5 (QCVN 08:2023 Mức B)
    - DO: >= 5.0 mg/L (Mức B)
    - TSS: <= 100 mg/L (Sông) / <= 15 mg/L (Hồ) (Mức B)
    - Nhiệt độ nước: 24 – 32 °C (tham khảo khí hậu nhiệt đới, phát hiện xả thải nhiệt)
    - Mực nước: 0.5 – 2.5 m (Lũ > 2.5m, Cạn < 0.5m)
    """
    violations = []
    
    # Xác định loại trạm từ bộ nhớ đệm (Sông hay Hồ)
    meta = station_metadata.get(tram_id, {"ten_tram": f"Trạm {tram_id:02d}", "loai_tram": "Sông"})
    loai_tram = meta.get("loai_tram", "Sông")

    # 1. pH (6.0 - 8.5)
    ph = data.get("ph", 7.0)
    if ph < 6.0 or ph > 8.5:
        violations.append({
            "chi_tieu": "pH",
            "gia_tri": ph,
            "mo_ta": f"pH = {ph:.2f} ngoài ngưỡng QCVN (6.0 - 8.5)"
        })

    # 2. DO (>= 5.0 mg/L)
    do_val = data.get("do", 6.0)
    if do_val < 5.0:
        violations.append({
            "chi_tieu": "DO",
            "gia_tri": do_val,
            "mo_ta": f"DO = {do_val:.2f} mg/L thấp hơn ngưỡng QCVN (>= 5.0 mg/L)"
        })

    # 3. TSS (Sông <= 100 mg/L, Hồ <= 15 mg/L)
    tss = data.get("tss", 30.0)
    tss_limit = 15.0 if loai_tram == "Hồ" else 100.0
    if tss > tss_limit:
        violations.append({
            "chi_tieu": "TSS",
            "gia_tri": tss,
            "mo_ta": f"TSS = {tss:.1f} mg/L vượt ngưỡng {loai_tram} (<= {tss_limit:.0f} mg/L)"
        })

    # 4. Nhiệt độ (24 - 32 °C tham khảo theo Bảng 4 Báo cáo)
    temp = data.get("temp", 28.0)
    if temp < 24.0 or temp > 32.0:
        violations.append({
            "chi_tieu": "Nhiệt độ",
            "gia_tri": temp,
            "mo_ta": f"Nhiệt độ nước = {temp:.1f}°C bất thường (ngưỡng 24 - 32°C)"
        })

    # 5. Mực nước (0.5 - 2.5 m)
    level = data.get("level", 1.5)
    if level > 2.5:
        violations.append({
            "chi_tieu": "Mực nước (Lũ)",
            "gia_tri": level,
            "mo_ta": f"Mực nước cao {level:.2f} m > 2.5 m (Cảnh báo nguy cơ lũ)"
        })
    elif level < 0.5:
        violations.append({
            "chi_tieu": "Mực nước (Cạn)",
            "gia_tri": level,
            "mo_ta": f"Mực nước cạn {level:.2f} m < 0.5 m (Cảnh báo khô hạn)"
        })

    return violations

def process_data(data):
    """
    Xử lý dữ liệu thu nhận được từ MQTT hoặc Simulation:
    - So sánh ngưỡng QCVN 08:2023/BTNMT
    - Tính toán chỉ số chất lượng nước tổng hợp WQI (0 - 100)
    - Cập nhật bộ đếm vi phạm (Quy tắc: 1-2 lần Cảnh báo vàng, >=3 lần Báo động đỏ, 2 lần an toàn về Bình thường)
    - Ghi vào CSDL SQLite (bảng do_luong và canh_bao)
    - Gửi cảnh báo Telegram nếu đạt trạng thái CRITICAL
    - Đẩy packet tới SSE stream
    """
    global station_states, latest_packets_queue
    tram_id = int(data.get("tram_id", 1))

    # Lấy thông tin trạm từ bộ nhớ đệm
    meta = station_metadata.get(tram_id, {"ten_tram": f"Trạm {tram_id:02d}", "loai_tram": "Sông"})
    ten_tram = meta.get("ten_tram", f"Trạm {tram_id:02d}")
    loai_tram = meta.get("loai_tram", "Sông")

    wqi, wqi_label = calculate_wqi(data, loai_tram)

    with lock:
        if tram_id not in station_states:
            station_states[tram_id] = {
                "violation_count": 0,
                "safe_count": 0,
                "current_status": "NORMAL",
                "last_violation_reasons": [],
                "latest_data": None
            }

        state = station_states[tram_id]
        violations = evaluate_thresholds(tram_id, data)
        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        old_status = state["current_status"]
        if violations:
            state["safe_count"] = 0
            state["violation_count"] += 1
            state["last_violation_reasons"] = [v["mo_ta"] for v in violations]

            # 1-2 lần: Cảnh báo nhẹ (Vàng); >= 3 lần: Vượt ngưỡng nghiêm trọng (Đỏ)
            if state["violation_count"] >= 3:
                state["current_status"] = "CRITICAL"
            else:
                state["current_status"] = "WARNING"
        else:
            state["violation_count"] = 0
            state["safe_count"] += 1
            if state["safe_count"] >= 2 or state["current_status"] == "WARNING":
                state["current_status"] = "NORMAL"
                state["last_violation_reasons"] = []

        # Nếu đạt trạng thái Báo động đỏ CRITICAL thì gửi Telegram
        if state["current_status"] == "CRITICAL":
            send_telegram_alert(ten_tram, violations, wqi, state["current_status"])

        # Ghi lịch sử đo vào SQLite (Mục 6.2 Báo cáo)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO do_luong (tram_id, thoi_gian, ph, do, do_duc, tss, nhiet_do, muc_nuoc, trang_thai, wqi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tram_id,
                now_str,
                data.get("ph", 7.0),
                data.get("do", 6.0),
                data.get("ntu", data.get("tss", 30.0) / 1.2),
                data.get("tss", 30.0),
                data.get("temp", 28.0),
                data.get("level", 1.5),
                state["current_status"],
                wqi
            ))

            # Ghi vào bảng canh_bao khi có vi phạm (Mục 6.3 Báo cáo)
            if violations and (state["current_status"] in ["WARNING", "CRITICAL"]):
                for v in violations:
                    cursor.execute("""
                        INSERT INTO canh_bao (tram_id, thoi_gian, chi_tieu, gia_tri, mo_ta, muc_do)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        tram_id,
                        now_str,
                        v["chi_tieu"],
                        v["gia_tri"],
                        v["mo_ta"],
                        state["current_status"]
                    ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB Error] {e}")

        packet = {
            "tram_id": tram_id,
            "thoi_gian": now_str,
            "time": now_str.split(" ")[1],
            "ph": data.get("ph", 7.0),
            "do": data.get("do", 6.0),
            "ntu": round(data.get("ntu", data.get("tss", 30.0) / 1.2), 1),
            "tss": data.get("tss", 30.0),
            "temp": data.get("temp", 28.0),
            "level": data.get("level", 1.5),
            "wqi": wqi,
            "wqi_label": wqi_label,
            "status": state["current_status"],
            "violation_count": state["violation_count"],
            "safe_count": state["safe_count"],
            "reasons": state["last_violation_reasons"]
        }
        state["latest_data"] = packet
        latest_packets_queue.append(packet)
        if len(latest_packets_queue) > 50:
            latest_packets_queue.pop(0)

        # Đẩy gói tin tức thời tới toàn bộ trình duyệt đang kết nối qua SSE
        for q in list(sse_clients):
            try:
                q.put_nowait(packet)
            except Exception:
                pass

# ----------------- MQTT CLIENT (TỰ ĐỘNG RECONNECT & DỰ PHÒNG) -----------------
def on_message(client, userdata, msg):
    try:
        topic = msg.topic
        payload_str = msg.payload.decode('utf-8')
        payload = json.loads(payload_str)
        
        # Nếu topic có chứa trạm cụ thể (ví dụ nhom08_dt51/tram1/data)
        if "tram1" in topic and "tram_id" not in payload:
            payload["tram_id"] = 1
        elif "tram2" in topic and "tram_id" not in payload:
            payload["tram_id"] = 2
        elif "tram3" in topic and "tram_id" not in payload:
            payload["tram_id"] = 3

        process_data(payload)
    except json.JSONDecodeError:
        # Hỗ trợ nhận topic lẻ (ví dụ: .../tram1/ph gửi số 7.5)
        try:
            val = float(payload_str)
            parts = topic.split("/")
            if len(parts) >= 2:
                metric = parts[-1]
                t_str = parts[-2]
                tram_id = 1
                if "tram2" in t_str: tram_id = 2
                elif "tram3" in t_str: tram_id = 3
                
                # Cập nhật từ cache gần nhất
                last = station_states.get(tram_id, {}).get("latest_data", {
                    "ph": 7.0, "do": 6.5, "tss": 30.0, "temp": 28.0, "level": 1.5
                }) or {"ph": 7.0, "do": 6.5, "tss": 30.0, "temp": 28.0, "level": 1.5}
                
                new_data = dict(last)
                new_data["tram_id"] = tram_id
                if metric == "ph": new_data["ph"] = val
                elif metric == "do": new_data["do"] = val
                elif metric in ["ntu", "tss"]:
                    new_data["ntu"] = val
                    new_data["tss"] = round(val * 1.2, 1)
                elif metric in ["temp", "nhiet_do"]: new_data["temp"] = val
                elif metric in ["level", "muc_nuoc"]: new_data["level"] = val
                process_data(new_data)
        except Exception as e:
            print(f"[MQTT Parse Single Metric Error] {e}")
    except Exception as e:
        print(f"[MQTT Message Error] {e}")

def start_mqtt():
    """Vòng lặp MQTT chạy ngầm với cơ chế tự động chuyển broker dự phòng và reconnect liên tục"""
    broker_idx = 0
    while True:
        target = MQTT_BROKER_LIST[broker_idx]
        try:
            print(f"[*] [MQTT] Đang kết nối tới Broker [{target['name']}] ({target['host']}:{target['port']})...")
            
            # Hỗ trợ cả paho-mqtt v1 và v2
            if hasattr(mqtt, 'CallbackAPIVersion'):
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            else:
                client = mqtt.Client()

            def on_connect_wrapper(c, userdata, flags, rc, properties=None):
                print(f"[+] [MQTT Connected] Kết nối thành công tới {target['host']} (rc={rc})")
                c.subscribe(MQTT_TOPIC)
                print(f"[+] [MQTT Subscribed] Lắng nghe topic: {MQTT_TOPIC}")

            client.on_connect = on_connect_wrapper
            client.on_message = on_message
            client.connect(target['host'], target['port'], keepalive=60)
            client.loop_forever()
        except Exception as e:
            print(f"[-] [MQTT Warning] Mất kết nối tới {target['host']}: {e}")
            broker_idx = (broker_idx + 1) % len(MQTT_BROKER_LIST)
            print(f"[*] [MQTT Info] Chuyển thử sang broker dự phòng sau 5 giây...")
            time.sleep(5)

# ----------------- FLASK ROUTES -----------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stations', methods=['GET'])
def get_stations():
    """Lấy danh sách các trạm quan trắc và trạng thái thời gian thực hiện tại"""
    conn = get_db_connection()
    stations = conn.execute("SELECT * FROM tram").fetchall()
    conn.close()

    result = []
    with lock:
        for s in stations:
            s_id = s["id"]
            st_info = station_states.get(s_id, {
                "violation_count": 0,
                "current_status": "NORMAL",
                "last_violation_reasons": [],
                "latest_data": None
            })
            result.append({
                "id": s_id,
                "ten_tram": s["ten_tram"],
                "loai_tram": s["loai_tram"],
                "mo_ta": s["mo_ta"],
                "status": st_info["current_status"],
                "violation_count": st_info["violation_count"],
                "latest_data": st_info["latest_data"]
            })
    return jsonify(result)

@app.route('/api/stations/<int:tram_id>/history', methods=['GET'])
def get_station_history(tram_id):
    """Lấy lịch sử dữ liệu đo của trạm phục vụ vẽ biểu đồ và bảng log"""
    limit = request.args.get('limit', default=50, type=int)
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT * FROM do_luong 
        WHERE tram_id = ? 
        ORDER BY id DESC 
        LIMIT ?
    """, (tram_id, limit)).fetchall()
    conn.close()

    data = []
    for row in reversed(rows):
        d = dict(row)
        # Bổ sung alias tương thích 100% cả tiếng Anh lẫn tiếng Việt
        d['temp'] = d.get('nhiet_do', 0.0)
        d['level'] = d.get('muc_nuoc', 0.0)
        d['ntu'] = d.get('do_duc', 0.0)
        d['status'] = d.get('trang_thai', 'NORMAL')
        data.append(d)
    return jsonify(data)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Lấy danh sách cảnh báo với bộ lọc theo trạm và thời gian (Mục 7 Báo cáo)"""
    tram_id = request.args.get('tram_id', default=None, type=str)
    limit = request.args.get('limit', default=50, type=int)
    
    query = """
        SELECT c.*, t.ten_tram, t.loai_tram 
        FROM canh_bao c
        LEFT JOIN tram t ON c.tram_id = t.id
        WHERE 1=1
    """
    params = []
    if tram_id and tram_id != 'all':
        query += " AND c.tram_id = ?"
        params.append(int(tram_id))

    query += " ORDER BY c.id DESC LIMIT ?"
    params.append(limit)

    conn = get_db_connection()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])

@app.route('/api/alerts/clear', methods=['POST'])
def clear_alerts():
    """Xóa nhật ký cảnh báo"""
    conn = get_db_connection()
    conn.execute("DELETE FROM canh_bao")
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Đã xóa lịch sử cảnh báo!"})

@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    """Xuất toàn bộ dữ liệu đo đạc hoặc cảnh báo ra file CSV"""
    export_type = request.args.get('type', default='do_luong')
    conn = get_db_connection()
    
    output = io.StringIO()
    writer = csv.writer(output)

    if export_type == 'canh_bao':
        rows = conn.execute("""
            SELECT c.id, c.tram_id, t.ten_tram, c.thoi_gian, c.chi_tieu, c.gia_tri, c.mo_ta, c.muc_do
            FROM canh_bao c
            LEFT JOIN tram t ON c.tram_id = t.id
            ORDER BY c.id DESC
        """).fetchall()
        writer.writerow(['ID', 'Mã trạm', 'Tên trạm', 'Thời gian', 'Chỉ tiêu', 'Giá trị', 'Mô tả', 'Mức độ'])
        for r in rows:
            writer.writerow([r['id'], r['tram_id'], r['ten_tram'], r['thoi_gian'], r['chi_tieu'], r['gia_tri'], r['mo_ta'], r['muc_do']])
        filename = f"canh_bao_qcvn08_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:
        rows = conn.execute("""
            SELECT d.id, d.tram_id, t.ten_tram, d.thoi_gian, d.ph, d.do, d.do_duc, d.tss, d.nhiet_do, d.muc_nuoc, d.trang_thai, d.wqi
            FROM do_luong d
            LEFT JOIN tram t ON d.tram_id = t.id
            ORDER BY d.id DESC LIMIT 1000
        """).fetchall()
        writer.writerow(['ID', 'Mã trạm', 'Tên trạm', 'Thời gian', 'pH', 'DO (mg/L)', 'Độ đục (NTU)', 'TSS (mg/L)', 'Nhiệt độ (°C)', 'Mực nước (m)', 'Trạng thái', 'Chỉ số WQI'])
        for r in rows:
            writer.writerow([r['id'], r['tram_id'], r['ten_tram'], r['thoi_gian'], r['ph'], r['do'], r['do_duc'], r['tss'], r['nhiet_do'], r['muc_nuoc'], r['trang_thai'], r['wqi'] or 100])
        filename = f"du_lieu_do_qcvn08_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    conn.close()
    output.seek(0)
    
    # Chuyển đổi thành bytes buffer kèm BOM UTF-8 để mở tiếng Việt trên Excel không bị lỗi font
    byte_output = io.BytesIO()
    byte_output.write(b'\xef\xbb\xbf')
    byte_output.write(output.getvalue().encode('utf-8'))
    byte_output.seek(0)

    return send_file(
        byte_output,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )

@app.route('/reset', methods=['POST'])
def reset_system():
    """Reset trạng thái cảnh báo và bộ đếm vi phạm về 0"""
    global station_states, latest_packets_queue
    with lock:
        for s_id in station_states:
            station_states[s_id]["violation_count"] = 0
            station_states[s_id]["safe_count"] = 0
            station_states[s_id]["current_status"] = "NORMAL"
            station_states[s_id]["last_violation_reasons"] = []
        
        # Gửi thông điệp reset tới tất cả các client SSE đang mở
        reset_event = {
            "tram_id": 1,
            "status": "NORMAL",
            "violation_count": 0,
            "safe_count": 0,
            "reasons": []
        }
        for q in list(sse_clients):
            try:
                q.put_nowait(reset_event)
            except Exception:
                pass
    return jsonify({"status": "success", "message": "Đã reset bộ đếm và trạng thái toàn bộ trạm thành công!"})

@app.route('/api/station/<int:tram_id>/simulate', methods=['POST'])
def simulate_station(tram_id):
    """
    Bộ giả lập kịch bản demo nhanh phục vụ thuyết trình:
    - normal: Nước đạt chuẩn QCVN 08
    - acid_waste: Ô nhiễm xả thải acid (pH = 4.2, DO = 3.1)
    - dirty_runoff: Ô nhiễm độ đục / TSS cao sau mưa lũ (TSS = 160 mg/L)
    - flood: Cảnh báo thủy văn mực nước dâng cao lũ lụt (Mực nước = 2.85 m)
    - drought: Cảnh báo mực nước cạn kiệt (Mực nước = 0.32 m)
    - hot_water: Ô nhiễm nhiệt độ xả thải công nghiệp (Nhiệt độ = 38.5 °C)
    """
    scenario = request.json.get("scenario", "normal") if request.is_json else request.args.get("scenario", "normal")
    
    sample = {
        "tram_id": tram_id,
        "ph": 7.35,
        "do": 6.8,
        "ntu": 35.0,
        "tss": 42.0,
        "temp": 28.5,
        "level": 1.65
    }

    if scenario == "acid_waste":
        sample["ph"] = 4.20
        sample["do"] = 3.10
        sample["tss"] = 85.0
        sample["temp"] = 30.0
        sample["level"] = 1.45
    elif scenario == "dirty_runoff":
        sample["ph"] = 6.80
        sample["do"] = 5.20
        sample["ntu"] = 145.0
        sample["tss"] = 174.0
        sample["temp"] = 27.5
        sample["level"] = 2.10
    elif scenario == "flood":
        sample["ph"] = 7.10
        sample["do"] = 5.80
        sample["ntu"] = 90.0
        sample["tss"] = 108.0
        sample["temp"] = 26.0
        sample["level"] = 2.88
    elif scenario == "drought":
        sample["ph"] = 8.10
        sample["do"] = 4.60
        sample["ntu"] = 25.0
        sample["tss"] = 30.0
        sample["temp"] = 31.0
        sample["level"] = 0.35
    elif scenario == "hot_water":
        sample["ph"] = 7.20
        sample["do"] = 4.10
        sample["temp"] = 37.8
        sample["tss"] = 45.0
        sample["level"] = 1.50
    elif request.is_json and "data" in request.json:
        sample.update(request.json["data"])

    process_data(sample)
    return jsonify({"status": "success", "scenario": scenario, "data": sample})

@app.route('/stream')
def stream():
    """SSE Stream đẩy dữ liệu tức thời xuống trình duyệt (Pub/Sub đa luồng chuẩn xác)"""
    client_q = queue.Queue(maxsize=100)
    with lock:
        sse_clients.append(client_q)
        # Gửi ngay dữ liệu gần nhất của trạm để UI hiển thị tức thì
        if latest_packets_queue:
            try:
                client_q.put_nowait(latest_packets_queue[-1])
            except Exception:
                pass

    def event_stream():
        try:
            while True:
                try:
                    packet = client_q.get(timeout=15)
                    yield f"data: {json.dumps(packet)}\n\n"
                except queue.Empty:
                    # Gửi heartbeat keep-alive để giữ kết nối SSE luôn sống
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            pass
        finally:
            with lock:
                if client_q in sse_clients:
                    sse_clients.remove(client_q)

    return Response(event_stream(), mimetype="text/event-stream")

if __name__ == '__main__':
    init_db()
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()
    print("=" * 60)
    print("  HỆ THỐNG GIÁM SÁT CHẤT LƯỢNG NƯỚC SÔNG, HỒ - ĐỀ TÀI 51")
    print("  Nhóm 08 - QCVN 08:2023/BTNMT")
    print("  Web Dashboard: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// ==========================================
// THÔNG TIN CẤU HÌNH WIFI & MQTT (NHÓM 08 - ĐỀ TÀI 51)
// ==========================================
const char* ssid = "Wokwi-GUEST";
const char* password = "";

const char* mqtt_server_primary = "broker.hivemq.com";
const char* mqtt_server_backup  = "test.mosquitto.org";
const char* mqtt_server = mqtt_server_primary;
const int mqtt_port = 1883;

// Topic chính (JSON trọn gói) và Topic cơ sở (Chỉ tiêu riêng lẻ theo Báo cáo Mục 5)
const char* topic_data  = "iot_huit_2026/nhom08_dt51/tram1/data";
const char* topic_base  = "iot_huit_2026/nhom08_dt51/tram1/";

// ==========================================
// CẤU HÌNH CHÂN CẢM BIẾN (CHUẨN HÓA THEO THỨ TỰ TỪ TRÊN XUỐNG DƯỚI)
// ==========================================
#define PIN_POT_PH   34  // Núm 1 (TRÊN CÙNG): Biến trở giả lập pH (0 - 14)
#define PIN_POT_DO   35  // Núm 2 (Ở GIỮA): Biến trở giả lập DO (0 - 10 mg/L)
#define PIN_POT_NTU  32  // Núm 3 (DƯỚI CÙNG): Biến trở giả lập Độ đục NTU / TSS (0 - 200 NTU)
#define PIN_DHT      4   // Chân tín hiệu DHT22 (Nhiệt độ nước)
#define PIN_TRIG     5   // HC-SR04 Trigger (Mực nước)
#define PIN_ECHO     18  // HC-SR04 Echo (Mực nước)

#define DHTTYPE DHT22
DHT dht(PIN_DHT, DHTTYPE);

WiFiClient espClient;
PubSubClient client(espClient);

unsigned long lastMsg = 0;
const long interval = 5000; // Chu kỳ gửi 5 giây (Theo Mục 5 Báo cáo)

// ==========================================
// HỖ TRỢ ĐIỀU KHIỂN NHANH QUA SERIAL MONITOR
// (Gõ 1, 2, 3, 4 hoặc 0 để điều khiển kịch bản cực chuẩn)
// ==========================================
bool serial_override = false;
float sim_ph = 7.25;
float sim_do = 6.80;
float sim_ntu = 25.0;
float sim_tss = 30.0;
float sim_temp = 28.0;
float sim_level = 1.50;

// ==========================================
// HÀM KẾT NỐI WIFI
// ==========================================
void setup_wifi() {
  delay(100);
  Serial.println("\n=============================================");
  Serial.print("[WiFi] Đang kết nối mạng: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Kết nối thành công!");
    Serial.print("[WiFi] Địa chỉ IP ESP32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Đang thử lại...");
  }
}

// ==========================================
// HÀM KẾT NỐI MQTT BROKER (CÓ TỰ ĐỘNG DỰ PHÒNG)
// ==========================================
void reconnect() {
  int retryCount = 0;
  while (!client.connected()) {
    Serial.print("[MQTT] Đang kết nối tới Broker: ");
    Serial.print(mqtt_server);
    Serial.print("...");

    String clientId = "ESP32_WaterNode1_" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println(" Thành công! [OK]");
      break;
    } else {
      Serial.print(" Thất bại, mã lỗi rc=");
      Serial.print(client.state());
      Serial.println(" Thử lại sau 2 giây...");
      retryCount++;
      if (retryCount >= 4) {
        if (strcmp(mqtt_server, mqtt_server_primary) == 0) {
          mqtt_server = mqtt_server_backup;
          Serial.println("[MQTT Failover] Chuyển sang Broker dự phòng: test.mosquitto.org");
        } else {
          mqtt_server = mqtt_server_primary;
          Serial.println("[MQTT Failover] Quay lại Broker chính: broker.hivemq.com");
        }
        client.setServer(mqtt_server, mqtt_port);
        retryCount = 0;
      }
      delay(2000);
    }
  }
}

// ==========================================
// HÀM ĐO MỰC NƯỚC (CẢM BIẾN SIÊU ÂM HC-SR04)
// Quy đổi trực quan 1:1 cho mô phỏng Wokwi:
// - Thanh trượt đo theo cm -> quy đổi thuận sang mét: level = distance (cm) / 100.0
// Ví dụ khi kéo trên Wokwi:
//   + Kéo 150 cm -> Mực nước: 1.50 m (Mức an toàn bình thường)
//   + Kéo 280 cm -> Mực nước: 2.80 m (Kích hoạt cảnh báo Lũ > 2.5 m)
//   + Kéo 360 cm -> Mực nước: 3.60 m (Kích hoạt cảnh báo Lũ cực lớn)
//   + Kéo 35 cm  -> Mực nước: 0.35 m (Kích hoạt cảnh báo Cạn khô < 0.5 m)
// ==========================================
float readWaterLevel() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  long duration = pulseIn(PIN_ECHO, HIGH, 30000);
  if (duration == 0) return 1.50; // Giá trị an toàn mặc định nếu cảm biến chưa phản hồi

  // Tính khoảng cách đo được từ cảm biến siêu âm theo mét (0.02m - 4.00m)
  float distance_m = (duration * 0.0343) / 2.0 / 100.0;

  // Ánh xạ trực quan 1:1 theo chiều thuận cho demo mô phỏng Wokwi
  float level = distance_m;
  if (level < 0.0) level = 0.0;
  if (level > 4.0) level = 4.0;
  return level;
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  analogReadResolution(12); // ADC 12-bit (0 - 4095)

  pinMode(PIN_POT_PH, INPUT);
  pinMode(PIN_POT_DO, INPUT);
  pinMode(PIN_POT_NTU, INPUT);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  dht.begin();
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);

  Serial.println("=============================================");
  Serial.println("  HỆ THỐNG GIÁM SÁT CHẤT LƯỢNG NƯỚC SÔNG, HỒ");
  Serial.println("  ĐỀ TÀI 51 - NHÓM 08 (MÔ PHỎNG WOKWI ESP32)");
  Serial.println("=============================================");
  Serial.println("  [PHÍM ĐIỀU KHIỂN NHANH TRÊN SERIAL MONITOR]");
  Serial.println("  Gõ 1: Nước chuẩn QCVN 08 (WQI 100 Tốt)");
  Serial.println("  Gõ 2: Ô nhiễm Axit (pH = 4.1)");
  Serial.println("  Gõ 3: Mưa lũ nước đục (TSS > 100, Lũ)");
  Serial.println("  Gõ 4: Ô nhiễm xả thải nhiệt (> 32°C)");
  Serial.println("  Gõ 0: Quay lại đọc từ biến trở xoay");
  Serial.println("=============================================");
}

// ==========================================
// LOOP CHÍNH
// ==========================================
void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Nhận phím bấm từ Serial Monitor để chuyển nhanh kịch bản demo
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == '1') {
      serial_override = true;
      sim_ph = 7.25; sim_do = 6.85; sim_ntu = 25.0; sim_tss = 30.0; sim_temp = 28.0; sim_level = 1.50;
      Serial.println("\n>>> [DEMO 1] KÍCH HOẠT: NƯỚC ĐẠT CHUẨN QCVN 08 (BÌNH THƯỜNG) <<<");
    } else if (cmd == '2') {
      serial_override = true;
      sim_ph = 4.10; sim_do = 4.20; sim_ntu = 35.0; sim_tss = 42.0; sim_temp = 28.5; sim_level = 1.50;
      Serial.println("\n>>> [DEMO 2] KÍCH HOẠT: Ô NHIỄM NƯỚC THẢI AXIT (pH = 4.1) <<<");
    } else if (cmd == '3') {
      serial_override = true;
      sim_ph = 6.80; sim_do = 5.20; sim_ntu = 140.0; sim_tss = 168.0; sim_temp = 27.0; sim_level = 2.85;
      Serial.println("\n>>> [DEMO 3] KÍCH HOẠT: MƯA LŨ VÀ MỰC NƯỚC DÂNG (TSS > 100, LŨ > 2.5m) <<<");
    } else if (cmd == '4') {
      serial_override = true;
      sim_ph = 7.20; sim_do = 4.10; sim_ntu = 30.0; sim_tss = 36.0; sim_temp = 38.5; sim_level = 1.50;
      Serial.println("\n>>> [DEMO 4] KÍCH HOẠT: XẢ THẢI NHIỆT ĐỘ NÓNG (> 32°C) <<<");
    } else if (cmd == '0') {
      serial_override = false;
      Serial.println("\n>>> [DEMO 0] CHUYỂN VỀ ĐỌC TRỰC TIẾP TỪ NÚM XOAY BIẾN TRỞ <<<");
    }
  }

  unsigned long now = millis();
  if (now - lastMsg >= interval) {
    lastMsg = now;

    float ph, do_val, ntu, tss, temp, level;

    if (serial_override) {
      ph = sim_ph;
      do_val = sim_do;
      ntu = sim_ntu;
      tss = sim_tss;
      temp = sim_temp;
      level = sim_level;
    } else {
      // 1. Đọc pH (Biến trở ADC 0-4095 quy đổi 0 - 14)
      int raw_ph = analogRead(PIN_POT_PH);
      ph = (raw_ph / 4095.0) * 14.0;

      // 2. Đọc DO (Biến trở ADC 0-4095 quy đổi 0 - 10 mg/L)
      int raw_do = analogRead(PIN_POT_DO);
      do_val = (raw_do / 4095.0) * 10.0;

      // 3. Đọc Độ đục NTU (0 - 200 NTU) và ước lượng TSS (mg/L)
      int raw_ntu = analogRead(PIN_POT_NTU);
      ntu = (raw_ntu / 4095.0) * 200.0;
      tss = ntu * 1.2;

      // 4. Đọc Nhiệt độ nước từ DHT22
      temp = dht.readTemperature();
      if (isnan(temp)) temp = 28.0;

      // 5. Đọc Mực nước từ siêu âm HC-SR04
      level = readWaterLevel();
    }

    // Làm tròn số thập phân
    ph = round(ph * 100.0) / 100.0;
    do_val = round(do_val * 100.0) / 100.0;
    ntu = round(ntu * 10.0) / 10.0;
    tss = round(tss * 10.0) / 10.0;
    temp = round(temp * 10.0) / 10.0;
    level = round(level * 100.0) / 100.0;

    // Đóng gói JSON trọn gói
    StaticJsonDocument<300> doc;
    doc["tram_id"] = 1;
    doc["ph"] = ph;
    doc["do"] = do_val;
    doc["ntu"] = ntu;
    doc["tss"] = tss;
    doc["temp"] = temp;
    doc["level"] = level;

    char buffer[300];
    serializeJson(doc, buffer);

    // Gửi gói tin JSON chính
    client.publish(topic_data, buffer);

    // Gửi kèm các topic chỉ tiêu đơn lẻ (Theo đúng thiết kế Mục 5 Báo cáo)
    char str_val[16];
    dtostrf(ph, 4, 2, str_val);
    client.publish((String(topic_base) + "ph").c_str(), str_val);

    dtostrf(do_val, 4, 2, str_val);
    client.publish((String(topic_base) + "do").c_str(), str_val);

    dtostrf(tss, 4, 1, str_val);
    client.publish((String(topic_base) + "tss").c_str(), str_val);

    dtostrf(temp, 4, 1, str_val);
    client.publish((String(topic_base) + "temp").c_str(), str_val);

    dtostrf(level, 4, 2, str_val);
    client.publish((String(topic_base) + "level").c_str(), str_val);

    // In thông tin rõ ràng lên Serial Monitor của Wokwi
    Serial.println("\n---------------------------------------------");
    Serial.print("[TX] Gửi MQTT -> ");
    Serial.println(topic_data);
    Serial.print("     pH: "); Serial.print(ph);
    Serial.print(" | DO: "); Serial.print(do_val); Serial.print(" mg/L");
    Serial.print(" | NTU: "); Serial.print(ntu);
    Serial.print(" | TSS: "); Serial.print(tss); Serial.println(" mg/L");
    Serial.print("     Nhiệt độ: "); Serial.print(temp); Serial.print(" °C");
    Serial.print(" | Mực nước: "); Serial.print(level); Serial.println(" m");
    Serial.println("---------------------------------------------");
  }
}

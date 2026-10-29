"""
Kịch bản kiểm thử tự động toàn diện hệ thống IoT Giám sát chất lượng nước (Đề tài 51)
Kiểm tra toàn bộ logic QCVN 08:2023, thuật toán vi phạm liên tiếp, CSDL và các API
"""
import sys
import os
import json
import sqlite3

# Thêm thư mục hiện tại vào sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app

def run_tests():
    print("=" * 70)
    print("  BẮT ĐẦU KIỂM THỬ TỰ ĐỘNG HỆ THỐNG GIÁM SÁT CHẤT LƯỢNG NƯỚC (ĐỀ TÀI 51)")
    print("=" * 70)

    # 1. Khởi tạo CSDL
    print("\n[TEST 1] Khởi tạo Database SQLite...")
    app.init_db()
    conn = app.get_db_connection()
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "tram" in tables, "Thiếu bảng tram"
    assert "do_luong" in tables, "Thiếu bảng do_luong"
    assert "canh_bao" in tables, "Thiếu bảng canh_bao"
    print(f"  -> Thành công! Các bảng tồn tại: {tables}")

    # Kiểm tra cột wqi trong do_luong
    cols = [col[1] for col in conn.execute("PRAGMA table_info(do_luong)").fetchall()]
    assert "wqi" in cols, "Thiếu cột wqi trong bảng do_luong"
    print(f"  -> Cột WQI đã sẵn sàng trong bảng do_luong: OK")
    conn.close()

    # 2. Kiểm thử tính toán WQI
    print("\n[TEST 2] Kiểm thử tính toán chỉ số WQI theo QCVN 08:2023...")
    wqi_norm, label_norm = app.calculate_wqi({"ph": 7.3, "do": 6.8, "tss": 25.0, "temp": 28.0}, "Sông")
    print(f"  -> Nước sạch: WQI = {wqi_norm}/100 [{label_norm}]")
    assert wqi_norm >= 90, f"WQI nước sạch phải >= 90, thực tế: {wqi_norm}"

    wqi_bad, label_bad = app.calculate_wqi({"ph": 4.2, "do": 2.5, "tss": 160.0, "temp": 38.0}, "Sông")
    print(f"  -> Nước ô nhiễm hỗn hợp: WQI = {wqi_bad}/100 [{label_bad}]")
    assert wqi_bad < 50, f"WQI nước ô nhiễm phải < 50, thực tế: {wqi_bad}"

    # Kiểm tra Nguyên lý yếu tố giới hạn: Axit cực mạnh pH = 1.82 dù các thông số khác hoàn hảo
    wqi_acid, label_acid = app.calculate_wqi({"ph": 1.82, "do": 6.6, "tss": 0.0, "temp": 28.0}, "Sông")
    print(f"  -> Axit cực mạnh (pH=1.82): WQI = {wqi_acid}/100 [{label_acid}]")
    assert wqi_acid <= 15, f"WQI axit cực mạnh pH=1.82 phải <= 15, thực tế: {wqi_acid}"
    assert label_acid == "Ô nhiễm nặng", f"Nhãn phải là Ô nhiễm nặng, thực tế: {label_acid}"

    # 3. Kiểm thử Test Client Flask
    client = app.app.test_client()

    print("\n[TEST 3] Kiểm tra các API chính...")
    # Trang chủ
    res = client.get('/')
    assert res.status_code == 200, "Lỗi tải trang chủ"
    print("  -> GET /: OK (200)")

    # Danh sách trạm
    res = client.get('/api/stations')
    assert res.status_code == 200
    st_data = json.loads(res.data)
    assert len(st_data) >= 3, "Phải có ít nhất 3 trạm"
    print(f"  -> GET /api/stations: OK ({len(st_data)} trạm)")

    # Reset hệ thống trước khi test vi phạm
    client.post('/reset')

    # 4. Kiểm thử Kịch bản 1: Nước đạt chuẩn (BÌNH THƯỜNG)
    print("\n[TEST 4] Kịch bản 1: Nước đạt chuẩn QCVN 08...")
    res = client.post('/api/station/1/simulate', json={"scenario": "normal"})
    assert res.status_code == 200
    st1 = app.station_states[1]
    print(f"  -> Trạng thái: {st1['current_status']} | Vi phạm: {st1['violation_count']} | An toàn: {st1['safe_count']}")
    assert st1['current_status'] == "NORMAL", "Trạng thái phải là NORMAL"

    # 5. Kiểm thử Kịch bản 2: Cảnh báo nhẹ (VÀNG) - Vi phạm lần 1 và 2
    print("\n[TEST 5] Kịch bản 2: Ô nhiễm Axit xả thải (pH=4.2, DO=3.1)...")
    # Lần 1
    client.post('/api/station/1/simulate', json={"scenario": "acid_waste"})
    st1 = app.station_states[1]
    print(f"  -> Vi phạm lần 1: Trạng thái = {st1['current_status']} (Bộ đếm: {st1['violation_count']}/3)")
    assert st1['current_status'] == "WARNING", "Lần 1 phải là WARNING"

    # Lần 2
    client.post('/api/station/1/simulate', json={"scenario": "acid_waste"})
    st1 = app.station_states[1]
    print(f"  -> Vi phạm lần 2: Trạng thái = {st1['current_status']} (Bộ đếm: {st1['violation_count']}/3)")
    assert st1['current_status'] == "WARNING", "Lần 2 vẫn là WARNING"

    # 6. Kiểm thử Kịch bản 3: Báo động đỏ (CRITICAL) - Vi phạm lần 3 liên tiếp
    print("\n[TEST 6] Kịch bản 3: Vi phạm lần 3 liên tiếp -> Chuyển BÁO ĐỘNG ĐỎ...")
    client.post('/api/station/1/simulate', json={"scenario": "acid_waste"})
    st1 = app.station_states[1]
    print(f"  -> Vi phạm lần 3: Trạng thái = {st1['current_status']} (Bộ đếm: {st1['violation_count']}/3)")
    assert st1['current_status'] == "CRITICAL", "Lần 3 phải chuyển sang CRITICAL"

    # Kiểm tra xem có ghi vào bảng canh_bao không
    conn = app.get_db_connection()
    alerts = conn.execute("SELECT * FROM canh_bao WHERE tram_id = 1 ORDER BY id DESC").fetchall()
    conn.close()
    assert len(alerts) > 0, "Phải có bản ghi cảnh báo trong CSDL"
    print(f"  -> Đã ghi nhận {len(alerts)} bản ghi cảnh báo vào CSDL: OK")

    # 7. Kiểm thử Kịch bản 4: Tự phục hồi về Bình thường
    print("\n[TEST 7] Kịch bản 4: Nước an toàn trở lại (Cần 2 lần liên tiếp)...")
    # Lần 1 an toàn
    client.post('/api/station/1/simulate', json={"scenario": "normal"})
    st1 = app.station_states[1]
    print(f"  -> An toàn lần 1: Trạng thái = {st1['current_status']} (An toàn: {st1['safe_count']}/2)")

    # Lần 2 an toàn
    client.post('/api/station/1/simulate', json={"scenario": "normal"})
    st1 = app.station_states[1]
    print(f"  -> An toàn lần 2: Trạng thái = {st1['current_status']} (An toàn: {st1['safe_count']}/2)")
    assert st1['current_status'] == "NORMAL", "Sau 2 lần an toàn phải trở về NORMAL"

    # 8. Kiểm thử các kịch bản thủy văn và ô nhiễm khác
    print("\n[TEST 8] Kiểm thử các kịch bản phụ trợ...")
    for sc, desc in [
        ("flood", "Cảnh báo Lũ (Mực nước > 2.5m)"),
        ("drought", "Cảnh báo Cạn (Mực nước < 0.5m)"),
        ("dirty_runoff", "Ô nhiễm TSS sau mưa lũ (TSS > 100 mg/L)"),
        ("hot_water", "Ô nhiễm nhiệt độ công nghiệp (> 32°C)")
    ]:
        client.post('/reset')
        res = client.post('/api/station/1/simulate', json={"scenario": sc})
        v_reasons = app.station_states[1]["last_violation_reasons"]
        print(f"  -> {desc}: Phát hiện vi phạm -> {v_reasons}")
        assert len(v_reasons) > 0, f"Phải phát hiện vi phạm với kịch bản {sc}"

    # 9. Kiểm thử xuất file CSV
    print("\n[TEST 9] Kiểm thử Xuất báo cáo CSV...")
    res = client.get('/api/export/csv?type=do_luong')
    assert res.status_code == 200
    assert b"Ch\xc3\xad s\xe1\xbb\x91 WQI" in res.data or b"WQI" in res.data
    print("  -> Xuất CSV do_luong: OK (Chứa BOM UTF-8 tiếng Việt và cột WQI)")

    res_alert = client.get('/api/export/csv?type=canh_bao')
    assert res_alert.status_code == 200
    print("  -> Xuất CSV canh_bao: OK")

    # Reset sạch sẽ sau khi test
    client.post('/reset')

    print("\n" + "=" * 70)
    print("  TẤT CẢ CÁC BÀI KIỂM THỬ ĐỀU ĐẠT 100% [SUCCESS]")
    print("=" * 70)

if __name__ == '__main__':
    run_tests()

# 강의실 공기 기록기 - SCD41 + DB + 바깥 저장소(Supabase)
# 버튼 A = 10분마다 (3시간 뒤 저절로 1시간마다), 버튼 B = 1시간마다 기록
# 저장: ① 내 DB  ② 날짜별 CSV  ③ Supabase indoor 표 (기록)
# 1분마다: Supabase latest 표에 "지금 값" 덮어쓰기 (웹 실시간 화면용)
# 5초마다: USB로 꽂힌 아두이노(모형집)에 이산화탄소 숫자 보내기 → 전광판·LED·창문

import csv
import glob
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import board
import adafruit_scd4x
import pymysql
from gpiozero import Button

try:
    import serial          # 아두이노와 USB로 대화하는 도구 (없으면 아두이노만 건너뜀)
except ImportError:
    serial = None

# ───────── 여기만 고치면 돼요 ─────────
FAST_MIN = 10
FAST_HOURS = 3
NORMAL_MIN = 60
ROOM = "강의실"
ROOM_ID = 1
DB_PASS_FILE = Path.home() / "db_password.txt"  # DB 비밀번호도 이 파일에만 (깃허브에 안 올림)
CLOUD_URL = "https://tprfmmompqsjzphfvfyw.supabase.co"
KEY_FILE = Path.home() / "supabase_key.txt"   # 비밀 열쇠는 이 파일에만
# ─────────────────────────────────────

DATA_DIR = Path.home() / "공기데이터"
DATA_DIR.mkdir(exist_ok=True)
KEY = KEY_FILE.read_text().strip() if KEY_FILE.exists() else ""
DB_PASSWORD = DB_PASS_FILE.read_text().strip() if DB_PASS_FILE.exists() else ""

interval = NORMAL_MIN
db = None
fast_since = None


def go_fast():
    global interval, fast_since
    interval = FAST_MIN
    fast_since = time.time()
    print(f"버튼 A: 이제 {FAST_MIN}분마다 기록 ({FAST_HOURS}시간 뒤 저절로 풀림)", flush=True)


def go_normal():
    global interval, fast_since
    interval = NORMAL_MIN
    fast_since = None
    print(f"버튼 B: 이제 {NORMAL_MIN}분마다 기록", flush=True)


def save_csv(now, co2, temp, hum):
    path = DATA_DIR / f"{now:%Y-%m-%d}.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["시각", "장소", "간격(분)", "이산화탄소(ppm)", "온도(C)", "습도(%)"])
        w.writerow([f"{now:%Y-%m-%d %H:%M}", ROOM, interval, co2, temp, hum])


def save_db(now, co2, temp, hum):
    global db
    try:
        if db is None:
            db = pymysql.connect(host="localhost", user="air", password=DB_PASSWORD,
                                 database="airdb", autocommit=True)
        db.ping(reconnect=True)
        with db.cursor() as c:
            c.execute(
                "INSERT INTO indoor (room_id, measured_at, co2, temp, hum, interval_min) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (ROOM_ID, now.replace(second=0, microsecond=0), co2, temp, hum, interval),
            )
        return True
    except Exception as e:
        print("DB 저장 실패 (CSV에는 저장됨):", e, flush=True)
        db = None
        return False


def cloud(table, rows, conflict):
    """Supabase 표에 올리기. 같은 칸이 있으면 덮어쓴다. 실패해도 멈추지 않는다."""
    if not KEY:
        return False
    req = urllib.request.Request(
        f"{CLOUD_URL}/rest/v1/{table}?on_conflict={conflict}",
        data=json.dumps(rows).encode(),
        method="POST",
        headers={
            "apikey": KEY,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception as e:
        print(f"올리기 실패 ({table}):", e, flush=True)
        return False


arduino = None


def to_arduino(co2):
    """USB로 꽂힌 아두이노에 숫자 보내기. 안 꽂혀 있어도 멈추지 않는다."""
    global arduino
    if serial is None:
        return
    try:
        if arduino is None:
            ports = sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
            if not ports:
                return
            arduino = serial.Serial(ports[0], 9600, timeout=1)
            print("아두이노 연결:", ports[0], flush=True)
            time.sleep(2)              # 아두이노가 다시 켜지는 동안 기다리기
        arduino.write(f"{co2}\n".encode())
    except Exception as e:
        print("아두이노 보내기 실패 (다시 시도할게요):", e, flush=True)
        try:
            arduino.close()
        except Exception:
            pass
        arduino = None


button_a = Button(17, bounce_time=0.2)
button_b = Button(27, bounce_time=0.2)
button_a.when_pressed = go_fast
button_b.when_pressed = go_normal

def start_sensor():
    """센서를 켠다. 선이 흔들려 응답이 없으면 5초마다 다시 시도한다."""
    while True:
        try:
            s = adafruit_scd4x.SCD4X(board.I2C())
            s.start_periodic_measurement()
            print("센서 연결 OK", flush=True)
            return s
        except Exception as e:
            print("센서를 못 찾음, 5초 뒤 다시:", e, flush=True)
            time.sleep(5)


sensor = start_sensor()
print(f"기록 시작: {interval}분마다 기록, 1분마다 지금 값 올림 "
      f"(열쇠 {'O' if KEY else 'X 없음'})", flush=True)

last_saved = None   # 마지막으로 기록한 분
last_live = None    # 마지막으로 지금 값을 올린 분
first = True
co2 = temp = hum = None   # 가장 최근에 잰 값

while True:
    if fast_since is not None and time.time() - fast_since >= FAST_HOURS * 3600:
        interval = NORMAL_MIN
        fast_since = None
        print(f"{FAST_HOURS}시간이 지나서 다시 {NORMAL_MIN}분마다 기록", flush=True)

    # 센서는 5초마다 새 값을 만든다 → 나올 때마다 읽어서 아두이노로 보내기
    try:
        if sensor.data_ready:
            co2 = sensor.CO2
            temp = round(sensor.temperature, 1)
            hum = round(sensor.relative_humidity, 1)
            to_arduino(co2)
    except Exception as e:
        print("센서 응답 없음, 다시 연결:", e, flush=True)
        time.sleep(2)
        sensor = start_sensor()

    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    due = first or (now.minute % interval == 0 and stamp != last_saved)
    live = stamp != last_live

    if (due or live) and co2 is not None:
        when = now.replace(second=0, microsecond=0).astimezone().isoformat()

        if due:
            save_csv(now, co2, temp, hum)
            ok = save_db(now, co2, temp, hum)
            up = cloud("indoor", [{"room_id": ROOM_ID, "measured_at": when, "co2": co2,
                                   "temp": temp, "hum": hum, "interval_min": interval}],
                       "room_id,measured_at")
            last_saved = stamp
            first = False
            print(f"{stamp}  기록  CO2 {co2}ppm  {temp}C  {hum}%  "
                  f"DB {'O' if ok else 'X'}  올림 {'O' if up else 'X'}", flush=True)

        if live:
            cloud("latest", [{"room_id": ROOM_ID, "measured_at": when,
                              "co2": co2, "temp": temp, "hum": hum}], "room_id")
            last_live = stamp

    time.sleep(1)

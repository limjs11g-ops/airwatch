# 바깥 공기 기록기 - 기상청(온도·습도) + 에어코리아(미세먼지) → Supabase outdoor 표
# 매시 50분에 crontab 으로 한 번씩 실행된다.
# 실행할 때마다 최근 24시간을 다시 채운다 → 인터넷이 끊겼던 시간도 저절로 메워진다.
#
#   python3 ~/outdoor.py          최근 24시간 저장
#   python3 ~/outdoor.py --month  처음 한 번: 지난 한 달 미세먼지까지 채우기
#
# 열쇠 파일 두 개 (코드에는 비밀을 쓰지 않는다)
#   ~/supabase_key.txt     기록기와 같은 Supabase 열쇠 (이미 있음)
#   ~/data_go_kr_key.txt   공공데이터포털 일반 인증키 (스트림릿에 넣은 것과 같은 것)

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ───────── 여기만 고치면 돼요 ─────────
STATION = "옥천읍"      # 에어코리아 측정소 (웹과 같게)
NX, NY = 71, 100        # 기상청 격자 (웹과 같게)
CLOUD_URL = "https://tprfmmompqsjzphfvfyw.supabase.co"
# ─────────────────────────────────────

KST = timezone(timedelta(hours=9))
HOME = Path.home()


def read_key(name):
    p = HOME / name
    return p.read_text().strip() if p.exists() else ""


SB_KEY = read_key("supabase_key.txt")
DATA_KEY = urllib.parse.unquote(read_key("data_go_kr_key.txt"))   # 인코딩된 열쇠를 넣어도 풀어서 씀


def get_json(url, params):
    """공공데이터 부르기. 열쇠가 틀리면 JSON 대신 오류 글이 와서 그 글을 보여 준다."""
    q = urllib.parse.urlencode(dict(params, serviceKey=DATA_KEY))
    with urllib.request.urlopen(f"{url}?{q}", timeout=15) as r:
        text = r.read().decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        raise RuntimeError(text[:200].replace("\n", " "))


def weather(hours=24):
    """기상청 초단기실황: 매시 정각 값, 40분쯤 올라옴 → 최근 hours 시간"""
    top = (datetime.now(KST) - timedelta(minutes=45)).replace(minute=0, second=0, microsecond=0)
    out = {}
    for h in range(hours):
        t = top - timedelta(hours=h)
        try:
            body = get_json("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst",
                            {"pageNo": 1, "numOfRows": 10, "dataType": "JSON",
                             "base_date": f"{t:%Y%m%d}", "base_time": f"{t:%H}00", "nx": NX, "ny": NY})
            items = body["response"]["body"]["items"]["item"]
            v = {i["category"]: float(i["obsrValue"]) for i in items}
            out[t] = {"temp": v.get("T1H"), "hum": v.get("REH")}
        except Exception as e:
            print(f"기상청 {t:%m-%d %H}시 실패:", e, flush=True)
    return out


def dust(month=False):
    """에어코리아 측정소 값: 하루(24줄) 또는 한 달(약 720줄)"""
    body = get_json("https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty",
                    {"returnType": "json", "numOfRows": 800 if month else 24, "pageNo": 1,
                     "stationName": STATION, "dataTerm": "MONTH" if month else "DAILY", "ver": "1.0"})
    num = lambda v: int(v) if str(v).isdigit() else None
    out = {}
    for it in body["response"]["body"]["items"]:
        day, hm = it["dataTime"].split()               # "2026-11-25 24:00" 처럼 24시도 옴
        t = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST) + timedelta(hours=int(hm[:2]))
        out[t] = {"pm10": num(it.get("pm10Value")), "pm25": num(it.get("pm25Value"))}
    return out


def upload(rows):
    """Supabase outdoor 표에 올리기. 같은 시각이 있으면 덮어쓴다. 빈 값(None)은 안 보낸다."""
    groups = {}
    for r in rows:
        r = {k: v for k, v in r.items() if v is not None}
        groups.setdefault(tuple(sorted(r)), []).append(r)   # 칸 모양이 같은 줄끼리 한 번에
    for g in groups.values():
        req = urllib.request.Request(
            f"{CLOUD_URL}/rest/v1/outdoor?on_conflict=measured_at",
            data=json.dumps(g).encode(), method="POST",
            headers={"apikey": SB_KEY, "Content-Type": "application/json",
                     "Prefer": "resolution=merge-duplicates,return=minimal"})
        with urllib.request.urlopen(req, timeout=15):
            pass


def main():
    if not SB_KEY or not DATA_KEY:
        print("열쇠 파일이 없어요: ~/supabase_key.txt · ~/data_go_kr_key.txt", flush=True)
        return
    month = "--month" in sys.argv
    w = weather()
    try:
        d = dust(month)
    except Exception as e:
        print("에어코리아 실패:", e, flush=True)
        d = {}

    rows = []
    for t in sorted(set(w) | set(d)):
        r = {"measured_at": t.isoformat()}
        r.update(w.get(t, {}))
        r.update(d.get(t, {}))
        if any(v is not None for k, v in r.items() if k != "measured_at"):
            rows.append(r)
    if not rows:
        print("받은 값이 없어요.", flush=True)
        return
    try:
        upload(rows)
    except Exception as e:
        print("Supabase 올리기 실패:", e, flush=True)
        return
    n_w = sum(1 for r in rows if r.get("temp") is not None)
    n_d = sum(1 for r in rows if r.get("pm25") is not None)
    print(f"{datetime.now(KST):%Y-%m-%d %H:%M}  저장 {len(rows)}줄 "
          f"(온도·습도 {n_w} · 초미세먼지 {n_d})", flush=True)


if __name__ == "__main__":
    main()

"""정보관 401호 공기 현황 - 실시간 웹 화면 (Streamlit)
라즈베리파이 → Supabase → 이 화면 (1분마다 저절로 새로 불러옴)
바깥 공기: 에어코리아(미세먼지) + 기상청 초단기실황(기온·습도) - 공공데이터포털
"""
import math
import os
from datetime import datetime, timedelta, timezone

import altair as alt
import pandas as pd
import requests
import streamlit as st

URL = "https://tprfmmompqsjzphfvfyw.supabase.co/rest/v1"
KEY = "sb_publishable_Uzj5v0HgZ7Fke9J8jVA5FQ_h25mN-Hm"   # 읽기 전용 공개 열쇠
KST = timezone(timedelta(hours=9))
ROOM = "정보관 401호"

STATION = "옥천읍"      # 에어코리아 측정소
NX, NY = 71, 100        # 기상청 격자 (충북 옥천)

OPEN_AT = 1000   # 이 이상이면 열기 (학교보건법 기준)
WARN_AT = 800    # 이 이상이면 곧 환기
CLOSE_AT = 500   # 연 뒤 이 아래로 내려오면 닫기 (바깥 공기 약 420ppm)

st.set_page_config(page_title=f"{ROOM} 공기 현황", page_icon="🪟", layout="centered")
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 760px;}
.big {font-size: 64px; font-weight: 900; line-height: 1; margin: 0;}
.unit {font-size: 22px; font-weight: 700; color: #6B7280;}
.lamp {border-radius: 24px; padding: 28px 30px; color: #fff; margin: 8px 0 18px;}
.lamp h2 {color: #fff; margin: 0 0 6px; font-size: 34px;}
.lamp p {margin: 0; font-size: 18px; opacity: .95;}
.card {border: 1px solid #E5E7EB; border-radius: 18px; padding: 18px 20px; height: 100%;}
.label {font-size: 15px; color: #6B7280; margin-bottom: 6px;}
.mid {font-size: 36px; font-weight: 800;}
.small {font-size: 26px; font-weight: 800;}
.note {font-size: 13px; color: #6B7280; margin-top: 4px;}
.gram {font-size: 13px; font-weight: 700; color: #6B7280;}
.gauge {position: relative; height: 9px; border-radius: 6px; background: rgba(128,128,128,.22); margin-top: 14px;}
.gauge .fill {position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; opacity: .85;}
.gauge .band {position: absolute; top: -3px; bottom: -3px; border-radius: 3px; background: rgba(42,157,143,.35);}
.gauge .zone {position: absolute; top: 0; bottom: 0;}
.gauge .mark {position: absolute; top: -5px; bottom: -5px; width: 2px;}
.gauge .tk {position: absolute; bottom: -6px; width: 1px; height: 5px; background: rgba(128,128,128,.7);}
.gauge .dot {position: absolute; top: 50%; width: 12px; height: 12px; border-radius: 50%; background: #fff;
             border: 3px solid; transform: translate(-50%, -50%);}
.ticks {position: relative; height: 14px; margin-top: 7px; font-size: 10px; color: #6B7280;}
.ticks span {position: absolute; transform: translateX(-50%); white-space: nowrap;}
</style>
""", unsafe_allow_html=True)


def secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:
        return os.environ.get(name, "")


# ───────── 실내 (Supabase) ─────────
def get(path):
    r = requests.get(f"{URL}/{path}", headers={"apikey": KEY}, timeout=10)
    r.raise_for_status()
    return r.json()


# ───────── 바깥 (공공데이터포털) ─────────
@st.cache_data(ttl=600, show_spinner=False)
def air_korea(key):
    """에어코리아 측정소별 실시간 측정정보"""
    r = requests.get(
        "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty",
        params={"serviceKey": key, "returnType": "json", "numOfRows": 24, "pageNo": 1,
                "stationName": STATION, "dataTerm": "DAILY", "ver": "1.0"}, timeout=10)
    items = r.json()["response"]["body"]["items"]
    num = lambda v: int(v) if str(v).isdigit() else None
    # 측정소가 점검·통신장애로 "-" 를 보내면, 숫자가 있는 가장 최근 시각 값을 대신 씀
    item = next((i for i in items if num(i.get("pm25Value")) is not None), items[0])
    return {"time": item.get("dataTime"), "pm10": num(item.get("pm10Value")),
            "pm25": num(item.get("pm25Value")), "old": item is not items[0]}


@st.cache_data(ttl=600, show_spinner=False)
def kma_now(key):
    """기상청 초단기실황 (매시 정각 자료, 40분쯤 올라옴)"""
    t = datetime.now(KST) - timedelta(minutes=45)
    r = requests.get(
        "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst",
        params={"serviceKey": key, "pageNo": 1, "numOfRows": 10, "dataType": "JSON",
                "base_date": f"{t:%Y%m%d}", "base_time": f"{t:%H}00", "nx": NX, "ny": NY},
        timeout=10)
    items = r.json()["response"]["body"]["items"]["item"]
    v = {i["category"]: float(i["obsrValue"]) for i in items}
    return {"time": f"{t:%H}:00", "temp": v.get("T1H"), "hum": v.get("REH"), "rain": v.get("PTY", 0)}


def outdoor():
    key = secret("DATA_GO_KR_KEY")
    if not key:
        return None, None
    a = w = None
    try:
        a = air_korea(key)
    except Exception:
        pass
    try:
        w = kma_now(key)
    except Exception:
        pass
    return a, w


def pm25_grade(v):
    if v is None:
        return "정보 없음", "#6B7280"
    if v <= 15:
        return "좋음", "#2A9D8F"
    if v <= 35:
        return "보통", "#2F6FB0"
    if v <= 75:
        return "나쁨", "#E08A00"
    return "매우 나쁨", "#D64545"


def judge(co2, air, wx, was_open=False):
    """논문 2.3.3 판단 규칙과 같은 순서 · 같은 문구"""
    bad_air = air and air["pm25"] is not None and air["pm25"] > 35   # 초미세먼지 36 이상 = 나쁨
    rain = wx and (wx.get("rain") or 0) > 0                           # 기상청 강수형태 0 = 비 안 옴
    cold = wx and wx["temp"] is not None and wx["temp"] < 5
    if co2 >= OPEN_AT:
        if bad_air or rain:
            why = f"바깥 초미세먼지가 나빠요({air['pm25']}㎍/㎥)" if bad_air else "바깥에 비나 눈이 와요"
            return ("#D97706", "🟠 복도 문만 짧게",
                    f"이산화탄소가 {OPEN_AT:,}ppm을 넘었는데 {why}. "
                    "창문 대신 복도 쪽 문을 잠깐 열어 주세요.")
        tip = " 바깥이 추우니 크게 열고 5분 안에 닫아요." if cold else ""
        return ("#D64545", "🔴 창문 5분 열기",
                f"이산화탄소가 학교 기준 {OPEN_AT:,}ppm을 넘었어요. 바깥 공기는 괜찮아요.{tip}")
    if was_open and co2 < CLOSE_AT:
        return ("#2F6FB0", "🔵 이제 닫기",
                f"환기 뒤 {CLOSE_AT:,}ppm 아래로 내려왔어요. 닫아서 냉난방 열을 아껴요.")
    if was_open:
        return ("#5B8DB8", "🪟 환기 중 · 조금 더 열어 두세요",
                f"공기가 바뀌고 있어요. {CLOSE_AT:,}ppm 아래로 내려가면 닫으라고 알려 드릴게요.")
    if co2 >= WARN_AT:
        return "#E08A00", "🟡 곧 환기가 필요해요", f"{OPEN_AT:,}ppm에 가까워지고 있어요. 쉬는 시간에 열어 주세요."
    return "#2A9D8F", "🟢 공기 좋음 · 닫아 두세요", f"{WARN_AT:,}ppm 아래예요. 닫아 두면 냉난방 열을 아낄 수 있어요."


def was_high(minutes=60):
    """최근 {minutes}분 안에 1,000ppm 이상이었던 기록이 있으면 True (= 환기 중이었음)"""
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = get(f"indoor?select=co2&room_id=eq.1&measured_at=gte.{since}&co2=gte.{OPEN_AT}&limit=1")
        return bool(rows)
    except Exception:
        return False


# 시연 모드: 주소 뒤에 ?test=1 / 2 / 3 을 붙이면 논문 시험 상황을 그대로 보여 줌
TESTS = {
    "1": {"co2": 1150, "pm25": 12, "pm10": 25, "was_open": False, "name": "① 창문 5분 열기 (실내 1,150ppm · 바깥 초미세먼지 좋음 12)"},
    "2": {"co2": 1150, "pm25": 48, "pm10": 80, "was_open": False, "name": "② 복도 문만 짧게 (실내 1,150ppm · 바깥 초미세먼지 나쁨 48)"},
    "3": {"co2": 480, "pm25": 12, "pm10": 25, "was_open": True, "name": "③ 이제 닫기 (1,150ppm에서 환기 → 480ppm으로 내려옴)"},
}


def temp_note(t):
    if t < 18:
        return "난방 기준(18~20℃)보다 낮아요"
    if t > 20:
        return "난방 기준(18~20℃)보다 높아요"
    return "난방 기준 안이에요"


def abs_hum(t, rh):
    """절대습도(g/㎥) = 공기 1㎥ 안에 실제로 든 물의 양. 온도·상대습도로 계산 (Magnus 공식)"""
    if t is None or rh is None:
        return None
    es = 6.112 * math.exp(17.67 * t / (t + 243.5))      # 그 온도의 포화 수증기압(hPa)
    return es * rh * 2.1674 / (273.15 + t)


def gauge(v, lo, hi, step, color, band=None, marks=(), zones=(), label_step=None, fmt=lambda x: f"{x:g}"):
    """숫자 밑 가로 막대 (눈금 step마다, 숫자는 label_step마다)"""
    pct = lambda x: (min(max(x, lo), hi) - lo) / (hi - lo) * 100
    h = '<div class="gauge">'
    for a, b, c in zones:
        h += f'<div class="zone" style="left:{pct(a)}%;width:{pct(b) - pct(a)}%;background:{c}"></div>'
    if band:
        h += f'<div class="band" style="left:{pct(band[0])}%;width:{pct(band[1]) - pct(band[0])}%"></div>'
    if v is not None:
        h += f'<div class="fill" style="width:{pct(v)}%;background:{color}"></div>'
    for x, c in marks:
        if x is not None:
            h += f'<div class="mark" style="left:{pct(x)}%;background:{c}"></div>'
    n = round((hi - lo) / step)
    h += "".join(f'<i class="tk" style="left:{i / n * 100}%"></i>' for i in range(n + 1))
    if v is not None:
        h += f'<div class="dot" style="left:{pct(v)}%;border-color:{color}"></div>'
    h += '</div><div class="ticks">'
    m = round((hi - lo) / (label_step or step))
    h += "".join(f'<span style="left:{i / m * 100}%">{fmt(lo + i * (label_step or step))}</span>'
                 for i in range(m + 1))
    return h + "</div>"


SAT20 = 17.3   # 20℃ 공기가 품을 수 있는 최대 물의 양 (g/㎥)


def hum20(t, rh):
    """습도를 20℃ 기준으로 맞춘 % = 절대습도 ÷ 17.3 (실내·외부를 같은 잣대로 비교)"""
    a = abs_hum(t, rh)
    return None if a is None else a / SAT20 * 100


T_RANGE = dict(lo=-10, hi=30, step=2, label_step=10)   # 실내·외부 온도 막대는 같은 잣대
PCT = lambda x: f"{int(x)}%"


def hum_note(h):
    if h < 30:
        return "건조해요 (기준 30~80%)"
    if h > 80:
        return "습해요 (기준 30~80%)"
    return "기준(30~80%) 안이에요"


st.title(f"🪟 {ROOM} 공기 현황")
st.caption("이산화탄소 센서(SCD41) + 라즈베리파이로 재고, 1분마다 저절로 새로 불러와요.")


@st.fragment(run_every="60s")
def now_panel():
    try:
        rows = get("latest?select=*&room_id=eq.1")
    except Exception:
        st.error("자료를 불러오지 못했어요. 잠시 뒤 다시 시도해요.")
        return
    if not rows:
        st.info("아직 올라온 값이 없어요.")
        return
    r = rows[0]
    t = datetime.fromisoformat(r["measured_at"]).astimezone(KST)
    ago = int((datetime.now(KST) - t).total_seconds() // 60)
    air, wx = outdoor()

    case = TESTS.get(st.query_params.get("test", ""))
    if case:
        st.info(f"🧪 **시연 모드** — {case['name']}  \n실제 측정값이 아니라 시험용 값이에요. "
                "주소 뒤의 `?test=` 를 지우면 실제 값으로 돌아가요.")
        r = dict(r, co2=case["co2"])
        air = {"pm25": case["pm25"], "pm10": case["pm10"], "time": "시험값"}
        wx = dict(wx, rain=0) if wx else wx      # 시험 때는 비 조건을 빼고 미세먼지만 봄
        was_open = case["was_open"]
    else:
        was_open = r["co2"] < OPEN_AT and was_high()

    color, head, sub = judge(r["co2"], air, wx, was_open)
    st.markdown(f'<div class="lamp" style="background:{color}"><h2>{head}</h2><p>{sub}</p></div>',
                unsafe_allow_html=True)

    st.markdown("**🏫 실내**")
    c1, c2, c3 = st.columns([1.4, 1, 1])
    ot_v = wx["temp"] if wx and wx["temp"] is not None else None
    ip = hum20(r["temp"], r["hum"])
    op = hum20(wx["temp"], wx["hum"]) if wx and wx["temp"] is not None and wx["hum"] is not None else None
    c1.markdown(f'<div class="card"><div class="label">이산화탄소</div>'
                f'<div class="big">{r["co2"]:,}<span class="unit"> ppm</span></div>'
                f'<div class="note">{OPEN_AT:,} 넘으면 열기 · {CLOSE_AT:,} 아래면 닫기</div>'
                + gauge(r["co2"], 400, 1600, 200, "#E4572E", marks=[(OPEN_AT, "#D64545"), (CLOSE_AT, "#2F6FB0")],
                        fmt=lambda x: f"{int(x):,}") + '</div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="card"><div class="label">실내 온도</div>'
                f'<div class="mid">{r["temp"]:.1f}℃</div><div class="note">{temp_note(r["temp"])}</div>'
                + gauge(r["temp"], color="#E08A00", band=(18, 20), marks=[(ot_v, "rgba(224,138,0,.9)")], **T_RANGE)
                + '</div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="card"><div class="label">실내 습도 (20℃ 기준)</div>'
                f'<div class="gram">{abs_hum(r["temp"], r["hum"]):.1f} g/㎥</div>'
                f'<div class="mid">{ip:.0f}%</div>'
                f'<div class="note">상대습도 {r["hum"]:.0f}% · {hum_note(r["hum"])}</div>'
                + gauge(ip, 0, 100, 20, "#2F6FB0", band=(30, 80), marks=[(op, "rgba(47,111,176,.9)")], fmt=PCT)
                + '</div>', unsafe_allow_html=True)

    when = f"{t:%m월 %d일 %H:%M} 측정"
    if ago >= 5:
        st.warning(f"⚠️ {when} · {ago}분 동안 새 값이 없어요. 라즈베리파이 연결을 확인해 주세요.")
    else:
        st.caption(f"🕒 {when} · {max(ago, 0)}분 전")

    st.markdown("**🌤️ 외부 (공공데이터)**")
    if air is None and wx is None:
        st.info("공공데이터 열쇠를 넣으면 외부 미세먼지·온도·습도가 여기 나와요.")
        return
    d1, d2, d3 = st.columns(3)
    pv = air["pm25"] if air else None
    g, gc = pm25_grade(pv)
    pm = f'{pv}' if pv is not None else "-"
    d1.markdown(f'<div class="card"><div class="label">초미세먼지</div>'
                f'<div class="small" style="color:{gc}">{pm}<span class="unit"> ㎍/㎥</span></div>'
                f'<div class="note">{g} · 미세먼지 {air["pm10"] if air and air["pm10"] is not None else "-"}'
                f'{" · " + air["time"][-5:] + " 값" if air and air.get("old") else ""}</div>'
                + gauge(pv, 0, 80, 10, "#7B61C9",
                        zones=[(0, 15, "rgba(42,157,143,.35)"), (15, 35, "rgba(47,111,176,.35)"),
                               (35, 75, "rgba(224,138,0,.35)"), (75, 80, "rgba(214,69,69,.4)")])
                + '</div>', unsafe_allow_html=True)
    ot = f'{ot_v:.1f}℃' if ot_v is not None else "-"
    diff = f'실내와 {abs(r["temp"] - ot_v):.1f}℃ 차이' if ot_v is not None else ""
    d2.markdown(f'<div class="card"><div class="label">외부 온도</div>'
                f'<div class="small">{ot}</div><div class="note">{diff}</div>'
                + gauge(ot_v, color="#E08A00", marks=[(r["temp"], "rgba(224,138,0,.9)")], **T_RANGE)
                + '</div>', unsafe_allow_html=True)
    oa = abs_hum(wx["temp"], wx["hum"]) if op is not None else None
    orh = f'상대습도 {wx["hum"]:.0f}%' if op is not None else ""
    d3.markdown(f'<div class="card"><div class="label">외부 습도 (20℃ 기준)</div>'
                f'<div class="gram">{f"{oa:.1f} g/㎥" if oa is not None else "&nbsp;"}</div>'
                f'<div class="small">{f"{op:.0f}%" if op is not None else "-"}</div>'
                f'<div class="note">{orh}</div>'
                + gauge(op, 0, 100, 20, "#2F6FB0", band=(30, 80), marks=[(ip, "rgba(47,111,176,.9)")], fmt=PCT)
                + '</div>', unsafe_allow_html=True)
    src = []
    if air:
        src.append(f"에어코리아 {STATION} {air['time']}")
    if wx:
        src.append(f"기상청 초단기실황 {wx['time']}")
    st.caption("출처: " + " · ".join(src) + " (10분마다 새로 불러옴)")


now_panel()

st.divider()
st.subheader("📈 하루 기록")

today = datetime.now(KST).date()
day = st.date_input("날짜", value=today, max_value=today, format="YYYY-MM-DD")


SERIES = [  # 이름, 실내 열, 외부 열, 색, 기준 아래, 기준 위, 최소 눈금 폭
    ("이산화탄소 (ppm)", "co2", None, "#E4572E", None, None, 60),
    ("온도 (℃) · 실내 / 외부", "temp", "temp", "#E08A00", 18, 20, 2),
    ("절대습도 (g/㎥) · 공기 1㎥ 속 물의 양", "ah", "ah", "#2F6FB0", None, None, 1),
    ("외부 초미세먼지 (㎍/㎥)", None, "pm25", "#7B61C9", 0, 15, 10),
]
GAP = {  # 실내·외부 차이 글자: 단위, 실내가 클 때, 외부가 클 때
    "temp": ("℃", "실내가 따뜻", "외부가 따뜻"),
    "ah": (" g/㎥", "실내가 더 습함", "외부가 더 습함"),
}


def fit(v, min_span):
    """값이 그래프 높이를 꽉 채우도록 위아래 범위를 데이터에 딱 맞춤"""
    lo, hi = float(v.min()), float(v.max())
    if hi - lo < min_span:
        mid = (hi + lo) / 2
        lo, hi = mid - min_span / 2, mid + min_span / 2
    pad = (hi - lo) * 0.12
    return [lo - pad, hi + pad]


def combo_chart(df, out):
    """실내(실선)·바깥(점선)을 위아래로 붙인 한 덩어리 그래프 + 같이 움직이는 세로선"""
    hover = alt.selection_point(fields=["시각"], nearest=True, on="pointerover",
                                empty=False, clear="pointerout", name="hover")
    panels = [p for p in SERIES if p[1] or (not out.empty and out[p[2]].notna().any())]
    rows = []
    for i, (name, col, oc, color, lo, hi, span) in enumerate(panels):
        last = i == len(panels) - 1
        has_out = oc is not None and not out.empty and out[oc].notna().any()
        vals = [df[col]] if col else []
        if has_out:
            vals.append(out[oc].dropna())
        dom = fit(pd.concat(vals), span)
        if col == "co2" and dom[1] < OPEN_AT <= dom[1] * 1.15:
            dom[1] = OPEN_AT * 1.03
        x = alt.X("시각:T", title=None, axis=alt.Axis(
            format="%H:%M", grid=False, labels=last, ticks=last, domain=last))
        sc = alt.Scale(domain=dom, nice=False, zero=False)
        yax = alt.Axis(tickCount=4, gridOpacity=0.4)
        base = alt.Chart(df).encode(x=x)
        layers = []
        if lo is not None and hi > dom[0] and lo < dom[1]:   # 학교 기준 띠 (범위 안에 든 만큼만)
            layers.append(base.mark_area(opacity=0.13, color="#2A9D8F", clip=True).encode(
                y=alt.YDatum(max(lo, dom[0]), scale=sc, title=None, axis=yax),
                y2=alt.Y2Datum(min(hi, dom[1]))))
        if col == "co2" and dom[1] >= OPEN_AT:
            layers.append(base.mark_rule(strokeDash=[6, 4], color="#D64545").encode(
                y=alt.YDatum(OPEN_AT, scale=sc, title=None, axis=yax)))
        if has_out:   # 바깥 = 점선
            layers.append(alt.Chart(out).mark_line(
                interpolate="monotone", strokeWidth=2.5 if not col else 2, color=color, clip=True,
                strokeDash=[] if not col else [6, 4], opacity=1 if not col else 0.75).encode(
                x=x, y=alt.Y(f"{oc}:Q", title=None, scale=sc, axis=yax)))
        if col:       # 실내 = 실선 + 색 채움
            y = alt.Y(f"{col}:Q", title=None, scale=sc, axis=yax)
            layers += [
                base.mark_area(interpolate="monotone", clip=True, color=color, opacity=0.16).encode(
                    y=y, y2=alt.Y2Datum(dom[0])),
                base.mark_line(interpolate="monotone", strokeWidth=2.5, color=color, clip=True).encode(y=y),
            ]
        # 마우스 올린 시각 표시 (세로선 + 점 + 숫자)
        hy = alt.Y(f"{col or 'o_' + oc}:Q", title=None, scale=sc, axis=yax)
        layers += [
            base.mark_point(size=80, opacity=0).encode(y=hy, tooltip=alt.value(None)).add_params(hover),
            base.mark_rule(color="#9CA3AF").transform_filter(hover),
            base.mark_point(size=90, filled=True, color=color).encode(y=hy).transform_filter(hover),
        ]
        label = dict(align="left", dx=9, fontSize=15, fontWeight="bold", color=color)
        if col and has_out:   # 실내·외부 둘 다: 숫자는 각자 선 위에, 차이는 둘 사이 가운데에
            unit, warm_in, warm_out = GAP[col]
            o = f"datum.o_{oc}"
            ok = f"isValid({o})"
            up = f"{ok} && {o} > datum.{col}"          # 외부가 위쪽이면 → 외부 글자는 위, 실내 글자는 아래
            oy = alt.Y(f"o_{oc}:Q", title=None, scale=sc, axis=yax)
            layers += [
                # 실내 숫자: 외부와 안 겹치게 반대쪽에
                base.mark_text(dy=-12, **label).encode(y=hy, text=alt.Text(f"{col}:Q", format=",.1~f"))
                .transform_filter(hover).transform_filter(f"!({up})"),
                base.mark_text(dy=16, **label).encode(y=hy, text=alt.Text(f"{col}:Q", format=",.1~f"))
                .transform_filter(hover).transform_filter(up),
                # 실내 ↔ 외부 잇는 막대 + 외부 점 (외부 점선 위)
                base.mark_rule(color=color, strokeWidth=3, opacity=0.55).encode(y=hy, y2=f"o_{oc}:Q")
                .transform_filter(hover).transform_filter(ok),
                base.mark_point(size=70, filled=True, color="white", stroke=color, strokeWidth=2).encode(y=oy)
                .transform_filter(hover).transform_filter(ok),
                # 외부 숫자: 외부 점선 위의 점 바로 옆
                base.mark_text(dy=-12, opacity=0.85, **dict(label, fontSize=13, fontWeight="normal"))
                .encode(y=oy, text="t:N").transform_filter(hover).transform_filter(up)
                .transform_calculate(t=f"'외부 ' + format({o}, '.1f')"),
                base.mark_text(dy=16, opacity=0.85, **dict(label, fontSize=13, fontWeight="normal"))
                .encode(y=oy, text="t:N").transform_filter(hover).transform_filter(f"{ok} && !({up})")
                .transform_calculate(t=f"'외부 ' + format({o}, '.1f')"),
                # 차이: 실내와 외부의 정확히 가운데 높이, 막대 왼쪽
                base.mark_text(align="right", dx=-10, fontSize=13, fontWeight="bold", color=color).encode(
                    y=alt.Y("mid:Q", title=None, scale=sc, axis=yax), text="gap:N")
                .transform_filter(hover).transform_filter(ok)
                .transform_calculate(mid=f"(datum.{col} + {o}) / 2",
                                     gap=f"'차이 ' + format(abs(datum.{col} - {o}), '.1f') + '{unit} '"
                                         f" + (datum.{col} >= {o} ? '({warm_in})' : '({warm_out})')"),
            ]
        elif col:             # 실내만 (이산화탄소)
            layers.append(base.mark_text(dy=-12, **label).encode(
                y=hy, text=alt.Text(f"{col}:Q", format=",.1~f")).transform_filter(hover))
        else:                 # 외부만 (초미세먼지): 숫자 + 등급을 선 위 점 옆에
            layers.append(base.mark_text(dy=-12, **label).encode(y=hy, text="t:N")
                          .transform_filter(hover).transform_filter(f"isValid(datum.o_{oc})")
                          .transform_calculate(t=f"format(datum.o_{oc}, '.0f') + ' · ' + "
                                                 f"(datum.o_{oc} <= 15 ? '좋음' : datum.o_{oc} <= 35 ? '보통' : "
                                                 f"datum.o_{oc} <= 75 ? '나쁨' : '매우 나쁨')"))
        if i == 0:
            layers.append(base.mark_text(align="left", dx=9, dy=-30, fontSize=12, color="#6B7280").encode(
                y=hy, text=alt.Text("시각:T", format="%H:%M")).transform_filter(hover))
        rows.append(alt.layer(*layers).properties(
            width=640, height=150 if last else 140,
            title=alt.TitleParams(name, anchor="start", fontSize=14, color=color, offset=4)))
    chart = alt.vconcat(*rows, spacing=10).resolve_scale(x="shared").configure_view(stroke=None)
    st.altair_chart(chart, width="stretch")


@st.cache_data(ttl=1800, show_spinner=False)
def outdoor_24h(key, anchor):
    """공공데이터에서 최근 24시간 바깥 값을 직접 가져오기 (기상청 매시 + 에어코리아)"""
    from concurrent.futures import ThreadPoolExecutor
    top = datetime.fromisoformat(anchor)

    def one(h):
        t = top - timedelta(hours=h)
        try:
            r = requests.get(
                "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst",
                params={"serviceKey": key, "pageNo": 1, "numOfRows": 10, "dataType": "JSON",
                        "base_date": f"{t:%Y%m%d}", "base_time": f"{t:%H}00", "nx": NX, "ny": NY},
                timeout=10)
            v = {i["category"]: float(i["obsrValue"]) for i in r.json()["response"]["body"]["items"]["item"]}
            return {"시각": t.replace(tzinfo=None), "temp": v.get("T1H"), "hum": v.get("REH")}
        except Exception:
            return None

    with ThreadPoolExecutor(8) as ex:
        wx = [w for w in ex.map(one, range(24)) if w]
    o = pd.DataFrame(wx, columns=["시각", "temp", "hum"])

    try:
        r = requests.get(
            "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty",
            params={"serviceKey": key, "returnType": "json", "numOfRows": 24, "pageNo": 1,
                    "stationName": STATION, "dataTerm": "DAILY", "ver": "1.0"}, timeout=10)
        pm = []
        for it in r.json()["response"]["body"]["items"]:
            day, hm = it["dataTime"].split()
            t = datetime.strptime(day, "%Y-%m-%d") + timedelta(hours=int(hm[:2]))
            num = lambda v: float(v) if str(v).replace(".", "", 1).isdigit() else None
            pm.append({"시각": t, "pm10": num(it.get("pm10Value")), "pm25": num(it.get("pm25Value"))})
        p = pd.DataFrame(pm, columns=["시각", "pm10", "pm25"])
    except Exception:
        p = pd.DataFrame(columns=["시각", "pm10", "pm25"])
    o = o.merge(p, on="시각", how="outer") if not o.empty or not p.empty else \
        pd.DataFrame(columns=["시각", "temp", "hum", "pm10", "pm25"])
    return o.sort_values("시각").reset_index(drop=True)


def outdoor_rows(start, end):
    """바깥 값: Supabase에 쌓인 기록 → 없으면 공공데이터에서 최근 24시간 직접"""
    cols = ["시각", "temp", "hum", "pm10", "pm25"]
    try:
        rows = get("outdoor?select=measured_at,temp,hum,pm10,pm25"
                   f"&measured_at=gte.{start.isoformat().replace('+', '%2B')}"
                   f"&measured_at=lt.{end.isoformat().replace('+', '%2B')}"
                   "&order=measured_at.asc")
    except Exception:
        rows = []
    saved = pd.DataFrame(rows, columns=["measured_at"] + cols[1:])
    saved["시각"] = (pd.to_datetime(saved["measured_at"]).dt.tz_convert(KST).dt.tz_localize(None)
                   if not saved.empty else pd.Series(dtype="datetime64[ns]"))
    saved = saved[cols]
    # 최근 24시간은 공공데이터에서도 직접 받아, 저장된 기록의 빈칸을 메움 (파이가 끊겼던 시간 등)
    key = secret("DATA_GO_KR_KEY")
    if not key or end < datetime.now(KST) - timedelta(hours=25):
        return saved.reset_index(drop=True)
    anchor = (datetime.now(KST) - timedelta(minutes=45)).replace(minute=0, second=0, microsecond=0)
    live = outdoor_24h(key, anchor.isoformat())
    if live.empty:
        return saved.reset_index(drop=True)
    live = live.copy()
    live["시각"] = pd.to_datetime(live["시각"])
    lo, hi = start.replace(tzinfo=None), end.replace(tzinfo=None)
    live = live[(live["시각"] >= lo) & (live["시각"] < hi)][cols]
    if saved.empty:
        return live.reset_index(drop=True)
    both = saved.set_index("시각").combine_first(live.set_index("시각")).reset_index()[cols]
    for c in cols[1:]:
        both[c] = pd.to_numeric(both[c], errors="coerce")
    return both.sort_values("시각").reset_index(drop=True)


@st.fragment(run_every="60s")
def day_chart(day):
    start = datetime.combine(day, datetime.min.time(), KST)
    end = start + timedelta(days=1)
    try:
        rows = get("indoor?select=measured_at,co2,temp,hum&room_id=eq.1"
                   f"&measured_at=gte.{start.isoformat().replace('+', '%2B')}"
                   f"&measured_at=lt.{end.isoformat().replace('+', '%2B')}"
                   "&order=measured_at.asc")
    except Exception:
        st.error("기록을 불러오지 못했어요.")
        return
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("이 날은 기록이 없어요.")
        return
    df["시각"] = pd.to_datetime(df["measured_at"]).dt.tz_convert(KST).dt.tz_localize(None)
    df["ah"] = [abs_hum(t, h) for t, h in zip(df.temp, df.hum)]
    out = outdoor_rows(start, end)
    if not out.empty:   # 실내 각 시각에 그때의 외부 값(1시간 단위)을 붙임
        out = out.copy()
        out["ah"] = [abs_hum(t, h) if pd.notna(t) and pd.notna(h) else None
                     for t, h in zip(out.temp, out.hum)]
        out["ah"] = pd.to_numeric(out["ah"])
        o = out[["시각", "temp", "hum", "ah", "pm25"]].rename(
            columns={"temp": "o_temp", "hum": "o_hum", "ah": "o_ah", "pm25": "o_pm25"})
        df = pd.merge_asof(df.sort_values("시각"), o.sort_values("시각"), on="시각",
                           direction="backward", tolerance=pd.Timedelta("90min"))

    a, b, c = st.columns(3)
    a.metric("이산화탄소 최고", f"{df.co2.max():,} ppm", help=f"{df.loc[df.co2.idxmax(), '시각']:%H:%M}")
    b.metric("온도 범위", f"{df.temp.min():.1f}~{df.temp.max():.1f}℃")
    c.metric("습도 범위", f"{df.hum.min():.0f}~{df.hum.max():.0f}%",
             help=f"절대습도 {df.ah.min():.1f}~{df.ah.max():.1f} g/㎥")

    combo_chart(df, out)
    st.caption("**실선 = 실내 · 점선 = 외부** (기상청·에어코리아, 1시간마다 · 지난 날짜 온도·습도는 기상청 대전 관측소)  \n"
               "마우스(손가락)를 그래프에 올리면 그 시각의 값이 한 번에 보여요.  \n"
               "초록 띠 = 학교 기준 (초미세먼지는 '좋음' 15 이하) · 빨간 점선 = 이산화탄소 1,000ppm  \n"
               "절대습도 = 공기 1㎥에 든 물의 양. 온도가 달라도 실내·외부를 바로 비교할 수 있어요 "
               "(겨울엔 외부 %가 높아 보여도 물은 더 적어요)")

    with st.expander("표로 보기"):
        st.dataframe(df[["시각", "co2", "temp", "hum", "ah"]].round({"ah": 1}).rename(
            columns={"co2": "이산화탄소(ppm)", "temp": "실내 온도(℃)", "hum": "실내 습도(%)",
                     "ah": "절대습도(g/㎥)"}),
            hide_index=True, width="stretch")


day_chart(day)


# ───────── 요일·시간 패턴: 언제 답답해지나 ─────────
DAYS = ["월", "화", "수", "목", "금", "토", "일"]


@st.cache_data(ttl=1800, show_spinner=False)
def indoor_since(since_iso):
    """실내 기록 전부 (Supabase는 한 번에 1,000줄까지라 나눠서 받음)"""
    rows, off = [], 0
    while True:
        part = get("indoor?select=measured_at,co2&room_id=eq.1"
                   f"&measured_at=gte.{since_iso.replace('+', '%2B')}"
                   f"&order=measured_at.asc&limit=1000&offset={off}")
        rows += part
        if len(part) < 1000:
            return rows
        off += 1000


def pattern_panel():
    since = (datetime.now(KST) - timedelta(days=28)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows = indoor_since(since.isoformat())
    except Exception:
        st.error("기록을 불러오지 못했어요.")
        return
    df = pd.DataFrame(rows)
    if len(df) < 20:
        st.info("기록이 더 쌓이면 요일·시간별 패턴이 나와요.")
        return
    t = pd.to_datetime(df["measured_at"]).dt.tz_convert(KST)
    df = df.assign(요일=t.dt.weekday.map(lambda d: DAYS[d]), 시=t.dt.hour, 날=t.dt.date)
    g = (df.groupby(["요일", "시"]).co2.agg(평균="mean", 최고="max", 기록="count").reset_index())
    g["평균"] = g["평균"].round()
    g["넘음"] = g["평균"] >= OPEN_AT
    days = [d for d in DAYS if d in set(g["요일"])]
    full = pd.MultiIndex.from_product([days, range(24)], names=["요일", "시"])   # 기록 없는 칸도 회색으로
    g = g.set_index(["요일", "시"]).reindex(full).reset_index()

    worst = g.loc[g["평균"].idxmax()]
    over = g[g["넘음"] == True]  # noqa: E712 (빈 칸은 NaN)
    n_days = df["날"].nunique()
    a, b, c = st.columns(3)
    a.metric("가장 답답한 때", f"{worst['요일']} {int(worst['시'])}시",
             help=f"평균 {int(worst['평균']):,}ppm · 최고 {int(worst['최고']):,}ppm")
    b.metric("평균이 1,000ppm 넘는 칸", f"{len(over)}칸", help="요일 × 시간 칸 중 평균이 학교 기준을 넘는 칸")
    c.metric("분석한 기록", f"{n_days}일 · {len(df):,}개", help="최근 4주")

    base = alt.Chart(g).encode(
        x=alt.X("시:O", title="시각", axis=alt.Axis(labelAngle=0, labelExpr="datum.value + '시'", grid=False)),
        y=alt.Y("요일:N", sort=days, title=None, axis=alt.Axis(grid=False)),
    )
    cells = base.mark_rect(cornerRadius=3, stroke=None).encode(
        color=alt.condition("isValid(datum.평균)",
                            alt.Color("평균:Q", title="평균 ppm",
                                      scale=alt.Scale(scheme="oranges", domain=[400, 1200], clamp=True),
                                      legend=alt.Legend(orient="bottom", gradientLength=260,
                                                        values=[400, 600, 800, 1000, 1200])),
                            alt.value("rgba(156,163,175,0.5)")),
        tooltip=[alt.Tooltip("요일:N"), alt.Tooltip("시:O", title="시"),
                 alt.Tooltip("평균:Q", title="평균 ppm", format=",.0f"),
                 alt.Tooltip("최고:Q", title="최고 ppm", format=",.0f"),
                 alt.Tooltip("기록:Q", title="기록 수")],
    )
    marks = base.mark_text(fontSize=11, fontWeight="bold", color="white").encode(
        text=alt.Text("평균:Q", format=",.0f")).transform_filter(f"datum.평균 >= {OPEN_AT}")
    chart = (cells + marks).properties(width=640, height=34 * len(days) + 150).configure_view(stroke=None)
    st.altair_chart(chart, width="stretch")

    tip = (f"**{worst['요일']}요일 {int(worst['시'])}시** 앞 쉬는 시간에 미리 열어 두면 좋아요."
           if worst["평균"] >= WARN_AT else "아직 기준을 넘는 시간대가 없어요. 지금처럼 닫아 두세요.")
    st.caption(f"색이 진할수록 이산화탄소가 많아요. 칸 안 숫자 = 평균이 {OPEN_AT:,}ppm을 넘은 시간 · 흐린 회색 = 기록 없음.  \n"
               f"💡 {tip}")
    with st.expander("표로 보기 (요일·시간별)"):
        st.dataframe(g.dropna(subset=["평균"]).rename(columns={"평균": "평균(ppm)", "최고": "최고(ppm)", "기록": "기록 수"})
                     .drop(columns="넘음"), hide_index=True, width="stretch")


st.divider()
st.subheader("🗓️ 언제 답답해지나 — 요일·시간 패턴")
pattern_panel()

st.divider()
st.caption("기준: 학교보건법 시행규칙 — 이산화탄소 1,000ppm 이하, 난방 온도 18\\~20℃, 습도 30\\~80%  \n"
           "외부 공기: 공공데이터포털 — 한국환경공단 에어코리아, 기상청 초단기실황  \n"
           "만든 사람: 충북도립대학교 AI산업학과 컴퓨터드론전공 임건호")

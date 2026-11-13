"""정보관 401호 공기 현황 - 실시간 웹 화면 (Streamlit)
라즈베리파이 → Supabase → 이 화면 (1분마다 저절로 새로 불러옴)
바깥 공기: 에어코리아(미세먼지) + 기상청 초단기실황(기온·습도) - 공공데이터포털
"""
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
CLOSE_AT = 800   # 이 아래로 내려오면 닫기

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
        params={"serviceKey": key, "returnType": "json", "numOfRows": 1, "pageNo": 1,
                "stationName": STATION, "dataTerm": "DAILY", "ver": "1.0"}, timeout=10)
    item = r.json()["response"]["body"]["items"][0]
    num = lambda v: int(v) if str(v).isdigit() else None
    return {"time": item.get("dataTime"), "pm10": num(item.get("pm10Value")),
            "pm25": num(item.get("pm25Value"))}


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


def judge(co2, air, wx):
    bad_air = air and air["pm25"] is not None and air["pm25"] > 35
    cold = wx and wx["temp"] is not None and wx["temp"] < 5
    if co2 >= OPEN_AT:
        if bad_air:
            return "#D64545", "🔴 5분만 짧게 여세요", "이산화탄소는 높은데 바깥 미세먼지가 나빠요. 짧게 열고 바로 닫아요."
        if cold:
            return "#D64545", "🔴 지금 여세요 (짧고 크게)", "바깥이 추워요. 창문을 크게 열고 3~5분 만에 닫으면 열 손실이 적어요."
        return "#D64545", "🔴 지금 창문을 여세요", f"이산화탄소가 학교 기준 {OPEN_AT:,}ppm을 넘었어요."
    if co2 >= WARN_AT:
        return "#E08A00", "🟡 곧 환기가 필요해요", f"{OPEN_AT:,}ppm에 가까워지고 있어요. 쉬는 시간에 열어 주세요."
    return "#2A9D8F", "🟢 공기 좋음 · 닫아 두세요", f"{CLOSE_AT:,}ppm 아래예요. 닫아 두면 냉난방 열을 아낄 수 있어요."


def temp_note(t):
    if t < 18:
        return "난방 기준(18~20℃)보다 낮아요"
    if t > 20:
        return "난방 기준(18~20℃)보다 높아요"
    return "난방 기준 안이에요"


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

    color, head, sub = judge(r["co2"], air, wx)
    st.markdown(f'<div class="lamp" style="background:{color}"><h2>{head}</h2><p>{sub}</p></div>',
                unsafe_allow_html=True)

    st.markdown("**🏫 실내**")
    c1, c2, c3 = st.columns([1.4, 1, 1])
    c1.markdown(f'<div class="card"><div class="label">이산화탄소</div>'
                f'<div class="big">{r["co2"]:,}<span class="unit"> ppm</span></div></div>',
                unsafe_allow_html=True)
    c2.markdown(f'<div class="card"><div class="label">온도</div>'
                f'<div class="mid">{r["temp"]:.1f}℃</div><div class="note">{temp_note(r["temp"])}</div></div>',
                unsafe_allow_html=True)
    c3.markdown(f'<div class="card"><div class="label">습도</div>'
                f'<div class="mid">{r["hum"]:.0f}%</div><div class="note">{hum_note(r["hum"])}</div></div>',
                unsafe_allow_html=True)

    when = f"{t:%m월 %d일 %H:%M} 측정"
    if ago >= 5:
        st.warning(f"⚠️ {when} · {ago}분 동안 새 값이 없어요. 라즈베리파이 연결을 확인해 주세요.")
    else:
        st.caption(f"🕒 {when} · {max(ago, 0)}분 전")

    st.markdown("**🌤️ 바깥 (공공데이터)**")
    if air is None and wx is None:
        st.info("공공데이터 열쇠를 넣으면 바깥 미세먼지·기온·습도가 여기 나와요.")
        return
    d1, d2, d3 = st.columns(3)
    g, gc = pm25_grade(air["pm25"] if air else None)
    pm = f'{air["pm25"]}' if air and air["pm25"] is not None else "-"
    d1.markdown(f'<div class="card"><div class="label">초미세먼지</div>'
                f'<div class="small" style="color:{gc}">{pm}<span class="unit"> ㎍/㎥</span></div>'
                f'<div class="note">{g} · 미세먼지 {air["pm10"] if air and air["pm10"] is not None else "-"}</div></div>',
                unsafe_allow_html=True)
    ot = f'{wx["temp"]:.1f}℃' if wx and wx["temp"] is not None else "-"
    oh = f'{wx["hum"]:.0f}%' if wx and wx["hum"] is not None else "-"
    diff = (f'실내와 {r["temp"] - wx["temp"]:+.1f}℃ 차이'.replace("+", "")
            if wx and wx["temp"] is not None else "")
    d2.markdown(f'<div class="card"><div class="label">바깥 기온</div>'
                f'<div class="small">{ot}</div><div class="note">{diff}</div></div>', unsafe_allow_html=True)
    d3.markdown(f'<div class="card"><div class="label">바깥 습도</div>'
                f'<div class="small">{oh}</div><div class="note">&nbsp;</div></div>', unsafe_allow_html=True)
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


def small_chart(df, field, title, color, domain=None, band=None, rule=None, rule_text=None, height=200):
    base = alt.Chart(df).encode(x=alt.X("시각:T", title=None, axis=alt.Axis(format="%H:%M")))
    y = alt.Y(f"{field}:Q", title=title,
              scale=alt.Scale(domain=domain) if domain else alt.Scale(zero=False))
    layers = []
    if band:
        layers.append(alt.Chart(pd.DataFrame({"a": [band[0]], "b": [band[1]]}))
                      .mark_rect(opacity=0.12, color="#2A9D8F").encode(y="a:Q", y2="b:Q"))
    layers.append(base.mark_line(color=color, strokeWidth=2,
                                 point=alt.OverlayMarkDef(size=14, color=color)).encode(
        y=y, tooltip=[alt.Tooltip("시각:T", format="%H:%M"), alt.Tooltip("co2:Q", title="이산화탄소 ppm"),
                      alt.Tooltip("temp:Q", title="온도 ℃"), alt.Tooltip("hum:Q", title="습도 %")]))
    if rule:
        layers.append(alt.Chart(pd.DataFrame({"y": [rule]})).mark_rule(strokeDash=[6, 4], color="#13233F")
                      .encode(y="y:Q"))
        layers.append(alt.Chart(pd.DataFrame({"y": [rule], "t": [rule_text]})).mark_text(
            align="left", dx=4, dy=-8, color="#13233F", fontWeight="bold").encode(
            y="y:Q", text="t:N", x=alt.value(4)))
    st.altair_chart(alt.layer(*layers).properties(height=height), width="stretch")


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

    a, b, c = st.columns(3)
    a.metric("이산화탄소 최고", f"{df.co2.max():,} ppm", help=f"{df.loc[df.co2.idxmax(), '시각']:%H:%M}")
    b.metric("온도 범위", f"{df.temp.min():.1f}~{df.temp.max():.1f}℃")
    c.metric("습도 범위", f"{df.hum.min():.0f}~{df.hum.max():.0f}%")

    st.markdown("**이산화탄소 (ppm)**")
    small_chart(df, "co2", None, "#E4572E", domain=[350, max(1100, int(df.co2.max() * 1.1))],
                rule=OPEN_AT, rule_text="학교 기준 1,000ppm", height=260)
    st.markdown("**온도 (℃)** · 초록 띠 = 학교 난방 기준 18~20℃")
    small_chart(df, "temp", None, "#E08A00", band=(18, 20))
    st.markdown("**습도 (%)** · 초록 띠 = 학교 기준 30~80%")
    small_chart(df, "hum", None, "#2F6FB0", band=(30, 80))

    with st.expander("표로 보기"):
        st.dataframe(df[["시각", "co2", "temp", "hum"]].rename(
            columns={"co2": "이산화탄소(ppm)", "temp": "온도(℃)", "hum": "습도(%)"}),
            hide_index=True, width="stretch")


day_chart(day)

st.divider()
st.caption("기준: 학교보건법 시행규칙 — 이산화탄소 1,000ppm 이하, 난방 온도 18~20℃, 습도 30~80%  \n"
           "바깥 공기: 공공데이터포털 — 한국환경공단 에어코리아, 기상청 초단기실황  \n"
           "만든 사람: 충북도립대학교 컴퓨터드론과 팀 건서호진 (임건호 · 장서진)")

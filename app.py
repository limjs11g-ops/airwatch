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


SERIES = [  # 이름, 실내 열, 바깥 열, 색, 기준 아래, 기준 위, 최소 눈금 폭
    ("이산화탄소 (ppm)", "co2", None, "#E4572E", None, None, 60),
    ("온도 (℃)", "temp", "temp", "#E08A00", 18, 20, 2),
    ("습도 (%)", "hum", "hum", "#2F6FB0", 30, 80, 6),
    ("바깥 초미세먼지 (㎍/㎥)", None, "pm25", "#7B61C9", 0, 15, 10),
]


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
            base.mark_text(align="left", dx=9, dy=-12, fontSize=15, fontWeight="bold", color=color).encode(
                y=hy, text=alt.Text(f"{col or 'o_' + oc}:Q", format=",.1~f")).transform_filter(hover),
        ]
        if col and has_out:
            layers.append(base.mark_text(align="left", dx=9, dy=12, fontSize=12, color=color, opacity=0.85)
                          .encode(y=hy, text="t:N").transform_filter(hover)
                          .transform_filter(f"isValid(datum.o_{oc})")
                          .transform_calculate(t=f"'바깥 ' + format(datum.o_{oc}, '.1f')"))
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
    o = pd.DataFrame(rows, columns=["measured_at"] + cols[1:])
    if not o.empty:
        o["시각"] = pd.to_datetime(o["measured_at"]).dt.tz_convert(KST).dt.tz_localize(None)
        return o[cols]
    key = secret("DATA_GO_KR_KEY")
    if not key or end < datetime.now(KST) - timedelta(hours=25):
        return pd.DataFrame(columns=cols)
    anchor = (datetime.now(KST) - timedelta(minutes=45)).replace(minute=0, second=0, microsecond=0)
    o = outdoor_24h(key, anchor.isoformat())
    if o.empty:
        return pd.DataFrame(columns=cols)
    o["시각"] = pd.to_datetime(o["시각"])
    lo, hi = start.replace(tzinfo=None), end.replace(tzinfo=None)
    return o[(o["시각"] >= lo) & (o["시각"] < hi)][cols].reset_index(drop=True)


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
    out = outdoor_rows(start, end)
    if not out.empty:   # 실내 각 시각에 그때의 바깥 값(1시간 단위)을 붙임
        o = out[["시각", "temp", "hum", "pm25"]].rename(
            columns={"temp": "o_temp", "hum": "o_hum", "pm25": "o_pm25"})
        df = pd.merge_asof(df.sort_values("시각"), o.sort_values("시각"), on="시각",
                           direction="backward", tolerance=pd.Timedelta("90min"))

    a, b, c = st.columns(3)
    a.metric("이산화탄소 최고", f"{df.co2.max():,} ppm", help=f"{df.loc[df.co2.idxmax(), '시각']:%H:%M}")
    b.metric("온도 범위", f"{df.temp.min():.1f}~{df.temp.max():.1f}℃")
    c.metric("습도 범위", f"{df.hum.min():.0f}~{df.hum.max():.0f}%")

    combo_chart(df, out)
    st.caption("**실선 = 실내 · 점선 = 바깥** (기상청·에어코리아, 1시간마다)  \n"
               "마우스(손가락)를 그래프에 올리면 그 시각의 값이 한 번에 보여요.  \n"
               "초록 띠 = 학교 기준 (초미세먼지는 '좋음' 15 이하) · 빨간 점선 = 이산화탄소 1,000ppm")

    with st.expander("표로 보기"):
        st.dataframe(df[["시각", "co2", "temp", "hum"]].rename(
            columns={"co2": "이산화탄소(ppm)", "temp": "온도(℃)", "hum": "습도(%)"}),
            hide_index=True, width="stretch")


day_chart(day)

st.divider()
st.caption("기준: 학교보건법 시행규칙 — 이산화탄소 1,000ppm 이하, 난방 온도 18\\~20℃, 습도 30\\~80%  \n"
           "바깥 공기: 공공데이터포털 — 한국환경공단 에어코리아, 기상청 초단기실황  \n"
           "만든 사람: 충북도립대학교 컴퓨터드론과 팀 건서호진 (임건호 · 장서진)")

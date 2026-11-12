"""정보관 401호 공기 현황 - 실시간 웹 화면 (Streamlit)
라즈베리파이 → Supabase → 이 화면 (1분마다 저절로 새로 불러옴)
"""
import os
from datetime import datetime, timedelta, timezone

import altair as alt
import pandas as pd
import requests
import streamlit as st

URL = "https://tprfmmompqsjzphfvfyw.supabase.co/rest/v1"
# 읽기 전용 공개 열쇠 (쓰기는 못 함)
KEY = "sb_publishable_Uzj5v0HgZ7Fke9J8jVA5FQ_h25mN-Hm"
KST = timezone(timedelta(hours=9))
ROOM = "정보관 401호"

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
.card {border: 1px solid #E5E7EB; border-radius: 18px; padding: 18px 20px;}
.label {font-size: 15px; color: #6B7280; margin-bottom: 6px;}
.mid {font-size: 36px; font-weight: 800;}
.note {font-size: 13px; color: #6B7280; margin-top: 4px;}
</style>
""", unsafe_allow_html=True)


def get(path):
    if os.environ.get("MOCK_DIR"):
        return mock(path)
    r = requests.get(f"{URL}/{path}", headers={"apikey": KEY}, timeout=10)
    r.raise_for_status()
    return r.json()


def mock(path):
    df = pd.read_csv(os.environ["MOCK_DIR"])
    t = pd.to_datetime(df["시각"]).dt.tz_localize(KST)
    rows = [{"measured_at": a.isoformat(), "co2": int(b), "temp": float(c), "hum": float(d)}
            for a, b, c, d in zip(t, df["이산화탄소(ppm)"], df["온도(C)"], df["습도(%)"])]
    if path.startswith("latest"):
        r = dict(rows[34]); r["measured_at"] = datetime.now(KST).isoformat()
        return [r]
    return rows


def judge(co2):
    if co2 >= OPEN_AT:
        return "#D64545", "🔴 지금 창문을 여세요", f"이산화탄소가 학교 기준 {OPEN_AT:,}ppm을 넘었어요."
    if co2 >= WARN_AT:
        return "#E08A00", "🟡 곧 환기가 필요해요", f"{OPEN_AT:,}ppm에 가까워지고 있어요. 쉬는 시간에 열어 주세요."
    return "#2A9D8F", "🟢 공기 좋음 · 닫아 두세요", f"{CLOSE_AT:,}ppm 아래예요. 닫아 두면 냉난방 열을 아낄 수 있어요."


def temp_note(t):
    if t < 18:
        return "난방 기준(18~20℃)보다 낮아요"
    if t > 20:
        return "난방철 기준(18~20℃)보다 높아요"
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

    color, head, sub = judge(r["co2"])
    st.markdown(f'<div class="lamp" style="background:{color}"><h2>{head}</h2><p>{sub}</p></div>',
                unsafe_allow_html=True)

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


now_panel()

st.divider()
st.subheader("📈 하루 기록")

today = datetime.now(KST).date()
day = st.date_input("날짜", value=today, max_value=today, format="YYYY-MM-DD")


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
    if os.environ.get("MOCK_DIR") and not df.empty:
        df["measured_at"] = pd.to_datetime(df["measured_at"])
        df = df[df["measured_at"].dt.date == day] if (df["measured_at"].dt.date == day).any() else df
    if df.empty:
        st.info("이 날은 기록이 없어요.")
        return
    df["시각"] = pd.to_datetime(df["measured_at"]).dt.tz_convert(KST).dt.tz_localize(None)

    a, b, c = st.columns(3)
    a.metric("최고", f"{df.co2.max():,} ppm", help=f"{df.loc[df.co2.idxmax(), '시각']:%H:%M}")
    b.metric("평균", f"{df.co2.mean():,.0f} ppm")
    c.metric(f"{OPEN_AT:,}ppm 넘은 기록", f"{(df.co2 >= OPEN_AT).sum()}번")

    top = max(1100, int(df.co2.max() * 1.1))
    base = alt.Chart(df).encode(x=alt.X("시각:T", title=None, axis=alt.Axis(format="%H:%M")))
    line = base.mark_line(color="#E4572E", strokeWidth=2, point=alt.OverlayMarkDef(size=18, color="#E4572E")).encode(
        y=alt.Y("co2:Q", title="이산화탄소 (ppm)", scale=alt.Scale(domain=[350, top])),
        tooltip=[alt.Tooltip("시각:T", format="%H:%M"), alt.Tooltip("co2:Q", title="ppm"),
                 alt.Tooltip("temp:Q", title="℃"), alt.Tooltip("hum:Q", title="%")])
    rule = alt.Chart(pd.DataFrame({"y": [OPEN_AT]})).mark_rule(strokeDash=[6, 4], color="#13233F").encode(y="y:Q")
    text = alt.Chart(pd.DataFrame({"y": [OPEN_AT], "t": ["학교 기준 1,000ppm"]})).mark_text(
        align="left", dx=4, dy=-8, color="#13233F", fontWeight="bold").encode(y="y:Q", text="t:N", x=alt.value(4))
    st.altair_chart((line + rule + text).properties(height=320), width="stretch")

    with st.expander("온도 · 습도 보기"):
        t_line = base.mark_line(color="#E08A00", strokeWidth=2).encode(
            y=alt.Y("temp:Q", title="온도 (℃)", scale=alt.Scale(zero=False)))
        band = alt.Chart(pd.DataFrame({"a": [18], "b": [20]})).mark_rect(opacity=0.12, color="#2A9D8F").encode(
            y="a:Q", y2="b:Q")
        st.altair_chart((band + t_line).properties(height=220), width="stretch")
        st.caption("초록 띠 = 학교 난방 기준 18~20℃")
        h_line = base.mark_line(color="#2A9D8F", strokeWidth=2).encode(
            y=alt.Y("hum:Q", title="습도 (%)", scale=alt.Scale(zero=False)))
        st.altair_chart(h_line.properties(height=200), width="stretch")

    with st.expander("표로 보기"):
        st.dataframe(df[["시각", "co2", "temp", "hum"]].rename(
            columns={"co2": "이산화탄소(ppm)", "temp": "온도(℃)", "hum": "습도(%)"}),
            hide_index=True, width="stretch")


day_chart(day)

st.divider()
st.caption("기준: 학교보건법 시행규칙 — 이산화탄소 1,000ppm 이하, 난방 온도 18~20℃, 습도 30~80%  \n"
           "만든 사람: 충북도립대학교 컴퓨터드론과 팀 건서호진 (임건호 · 장서진)")

-- 강의실 공기 기록 표 (라즈베리파이 MariaDB "airdb" / Supabase 공통)
-- 코드(pi/scd41_logger.py, app.py)가 실제로 쓰는 칸 기준으로 정리했습니다.

-- ① 실내 기록: 10분 또는 1시간마다 한 줄
CREATE TABLE indoor (
  room_id      INT          NOT NULL,          -- 강의실 번호 (지금은 1)
  measured_at  DATETIME     NOT NULL,          -- 잰 시각 (분 단위)
  co2          INT          NOT NULL,          -- 이산화탄소 (ppm)
  temp         DECIMAL(4,1),                   -- 온도 (℃)
  hum          DECIMAL(4,1),                   -- 상대습도 (%)
  interval_min INT,                            -- 기록 간격 (10 또는 60)
  PRIMARY KEY (room_id, measured_at)           -- 같은 시각이 두 번 들어가지 않게
);

-- ② 지금 값: 강의실마다 한 줄, 1분마다 덮어쓰기 (Supabase, 웹 실시간 화면용)
CREATE TABLE latest (
  room_id      INT          PRIMARY KEY,
  measured_at  TIMESTAMPTZ  NOT NULL,
  co2          INT,
  temp         NUMERIC(4,1),
  hum          NUMERIC(4,1)
);

-- ③ 바깥 공기: 에어코리아(옥천읍 측정소) + 기상청(격자 71,100) 값 (Supabase)
CREATE TABLE outdoor (
  measured_at  TIMESTAMPTZ  PRIMARY KEY,
  temp         NUMERIC(4,1),                   -- 바깥 온도 (℃)
  hum          NUMERIC(4,1),                   -- 바깥 습도 (%)
  pm10         INT,                            -- 미세먼지 (㎍/㎥)
  pm25         INT                             -- 초미세먼지 (㎍/㎥)
);

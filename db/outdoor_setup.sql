-- 바깥 공기 표 준비 (Supabase → SQL Editor 에 붙여 넣고 Run, 한 번만)
-- 이미 있으면 그대로 두고, 웹(공개 열쇠)이 읽을 수 있게 허락만 다시 건다.

CREATE TABLE IF NOT EXISTS outdoor (
  measured_at  TIMESTAMPTZ  PRIMARY KEY,
  temp         NUMERIC(4,1),                   -- 바깥 온도 (℃)
  hum          NUMERIC(4,1),                   -- 바깥 습도 (%)
  pm10         INT,                            -- 미세먼지 (㎍/㎥)
  pm25         INT                             -- 초미세먼지 (㎍/㎥)
);

ALTER TABLE outdoor ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "웹은 읽기만" ON outdoor;
CREATE POLICY "웹은 읽기만" ON outdoor FOR SELECT TO anon USING (true);

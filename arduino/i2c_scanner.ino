// 전광판 주소(번호) 찾기
// 올린 다음 → 오른쪽 위 돋보기(시리얼 모니터) 누르고 → 아래 속도를 9600 으로
// "찾았어요: 0x27" 처럼 나오면 그 번호를 lcd_test.ino 에 넣으면 돼요

#include <Wire.h>

void setup() {
  Wire.begin();
  Serial.begin(9600);
  delay(1000);
  Serial.println("찾는 중...");
  int found = 0;
  for (byte a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.print("찾았어요: 0x");
      if (a < 16) Serial.print("0");
      Serial.println(a, HEX);
      found++;
    }
  }
  if (found == 0) Serial.println("못 찾았어요 -> SDA(A4), SCL(A5) 선을 확인하세요");
}

void loop() {}

// QAPASS 1602 전광판(I2C) 시험용
// 화면 1줄: Hello!   2줄: 1초마다 숫자가 올라가요
// 글자가 안 보이면 → 아래 0x27 을 0x3F 로 바꿔서 다시 올려 보세요

#include <Wire.h>                 // 선 2개(SDA, SCL)로 대화하는 기본 도구
#include <LiquidCrystal_I2C.h>    // 전광판을 쉽게 쓰게 해 주는 도구

LiquidCrystal_I2C lcd(0x27, 16, 2);   // 주소 0x27, 한 줄 16칸, 2줄

void setup() {
  lcd.init();           // 전광판 깨우기
  lcd.backlight();      // 뒤쪽 불 켜기
  lcd.setCursor(0, 0);  // 첫째 칸, 첫째 줄로 이동
  lcd.print("Hello!");
}

void loop() {
  lcd.setCursor(0, 1);  // 첫째 칸, 둘째 줄로 이동
  lcd.print(millis() / 1000);   // 켜진 지 몇 초인지
  lcd.print(" sec");
  delay(1000);
}

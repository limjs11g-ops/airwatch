// 교실 환기 모형집 - 우드락 1호 (+ QAPASS 1602 전광판)
// 버튼을 누르면: CO2가 오르는 상황 재생 → 신호등 → 부저 → 창문 열림 → 회복 → 창문 닫힘
// 라즈베리파이가 USB로 진짜 CO2 숫자를 보내 주면 그 숫자대로도 움직여요 (예: "1023" + 줄바꿈)

#include <Servo.h>          // 서보 모터를 쉽게 움직이게 해 주는 기본 도구
#include <Wire.h>           // 전광판과 선 2개로 대화하는 도구
#include <LiquidCrystal_I2C.h>  // QAPASS 1602 전광판 도구

const int GREEN = 9;        // 초록 LED 핀
const int YELLOW = 10;      // 노랑 LED 핀
const int RED = 11;         // 빨강 LED 핀
const int BUTTON = 2;       // 시연 버튼 핀
const int BUZZER = 8;       // 부저 핀 (없으면 그냥 둬도 돼요)
const int SERVO_PIN = 6;    // 서보 모터 신호선 핀

const int CLOSED = 0;       // 창문 닫힘 각도
const int OPENED = 80;      // 창문 열림 각도 (모형에 맞게 바꿔도 돼요)

Servo windowServo;          // 창문 서보
LiquidCrystal_I2C lcd(0x27, 16, 2);  // 전광판 (안 나오면 0x3F 로)
int co2 = 450;              // 지금 CO2 값 (처음엔 깨끗한 공기)
int angle = CLOSED;         // 창문이 지금 몇 도인지 기억

// 신호등 켜기: 1이면 켜고 0이면 끔
void light(int g, int y, int r) {
  digitalWrite(GREEN, g);
  digitalWrite(YELLOW, y);
  digitalWrite(RED, r);
}

// 전광판에 숫자와 상태 쓰기
//  1줄: CO2  1023 ppm
//  2줄: GOOD / WARNING / OPEN WINDOW!
void showLcd(int v) {
  lcd.setCursor(0, 0);
  lcd.print("CO2 ");
  if (v < 1000) lcd.print(" ");   // 자리 맞추기
  lcd.print(v);
  lcd.print(" ppm    ");
  lcd.setCursor(0, 1);
  if (v >= 1000)      lcd.print("OPEN WINDOW!    ");
  else if (v >= 800)  lcd.print("WARNING         ");
  else                lcd.print("GOOD            ");
}

// CO2 숫자에 맞는 불 켜기 (800 미만 초록, 1000 미만 노랑, 그 이상 빨강) + 전광판
void showLevel(int v) {
  if (v >= 1000)      light(0, 0, 1);
  else if (v >= 800)  light(0, 1, 0);
  else                light(1, 0, 0);
  showLcd(v);
}

// 창문을 천천히 움직이기 (한 번에 확 돌면 모형이 흔들려요)
void moveWindow(int target) {
  while (angle != target) {
    angle += (target > angle) ? 1 : -1;
    windowServo.write(angle);
    delay(12);
  }
}

// 부저 n번 울리기
void beep(int n) {
  for (int i = 0; i < n; i++) {
    digitalWrite(BUZZER, HIGH); delay(150);
    digitalWrite(BUZZER, LOW);  delay(150);
  }
}

// 시연: 공기가 탁해졌다가 환기로 회복되는 과정
void demo() {
  Serial.println("DEMO START");
  for (co2 = 450; co2 < 1050; co2 += 10) {   // 약 4초 동안 450 → 1050
    showLevel(co2);
    Serial.println(co2);
    delay(60);
  }
  beep(3);                                    // 빨간불 되면 삐삐삐
  moveWindow(OPENED);                         // 창문 열기
  for (; co2 > 700; co2 -= 10) {              // 환기되면서 숫자 내려감
    showLevel(co2);
    Serial.println(co2);
    delay(80);
  }
  moveWindow(CLOSED);                         // 초록불 되면 창문 닫기
  showLevel(co2);
  Serial.println("DEMO END");
}

void setup() {
  pinMode(GREEN, OUTPUT);
  pinMode(YELLOW, OUTPUT);
  pinMode(RED, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  pinMode(BUTTON, INPUT_PULLUP);  // 버튼 안 누르면 HIGH, 누르면 LOW (저항 없이 OK)
  windowServo.attach(SERVO_PIN);
  windowServo.write(CLOSED);
  Serial.begin(9600);             // 라즈베리파이·컴퓨터와 대화하는 속도
  Serial.setTimeout(200);
  lcd.init();                     // 전광판 깨우기
  lcd.backlight();                // 전광판 불 켜기
  showLevel(co2);
}

void loop() {
  // 1) 시연 버튼
  if (digitalRead(BUTTON) == LOW) {
    delay(30);                                // 버튼 떨림 무시
    if (digitalRead(BUTTON) == LOW) {
      demo();
      while (digitalRead(BUTTON) == LOW) {}   // 손 뗄 때까지 기다리기
    }
  }

  // 2) 라즈베리파이가 보내는 진짜 CO2 숫자
  if (Serial.available()) {
    int v = Serial.parseInt();
    if (v > 0) {
      co2 = v;
      showLevel(co2);
      if (co2 >= 1000)     moveWindow(OPENED);
      else if (co2 < 800)  moveWindow(CLOSED);   // 800~999는 그대로 두기
    }
  }
}

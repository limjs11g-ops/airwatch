// 모형집: 전광판 + 신호등 + 환기팬 + 소리(수동 부저)
// 시연용 기준: 초록 <600, 노랑 600~799, 빨강 800+
// 라즈베리파이가 USB로 CO2 숫자를 보내 준다 (예: "823" + 줄바꿈)
// 15초 동안 숫자가 안 오면 연습 모드(450↔1000 오르내림)로 움직인다

// ===== 1. 설정 =====
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

const int GREEN  = 9;
const int YELLOW = 10;
const int RED    = 11;
const int FAN    = 7;
const int BUZZER = 8;

const int RELAY_ON  = LOW;    // 이 릴레이는 LOW일 때 켜진다
const int RELAY_OFF = HIGH;

const int WARN_AT = 600;
const int OPEN_AT = 800;
const int GAP     = 20;       // 경계에서 깜빡이지 않게 내려갈 때는 20 더 내려가야 바뀜

int co2 = 450;
int step = 10;
int level = 0;                // 0 초록, 1 노랑, 2 빨강
bool fanOn = false;
unsigned long lastReal = 0;
unsigned long lastWake = 0;

void wakeLcd();
void show();
void updateLevel();
void playSound(int from, int to);

// ===== 2. 켜질 때 한 번 =====
void setup() {
  pinMode(GREEN, OUTPUT);
  pinMode(YELLOW, OUTPUT);
  pinMode(RED, OUTPUT);
  pinMode(FAN, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  digitalWrite(FAN, RELAY_OFF);

  Serial.begin(9600);
  Serial.setTimeout(200);

  Wire.begin();
  Wire.setWireTimeout(3000, true);   // 선이 흔들려 전광판이 멈춰도 아두이노는 안 멈춤
  wakeLcd();
  show();

  tone(BUZZER, 1047, 120);           // 켜질 때 "띡"
}

// ===== 3. 계속 반복 =====
void loop() {
  if (Serial.available()) {
    int v = Serial.parseInt();
    if (v > 0) {
      co2 = v;
      lastReal = millis();
      updateLevel();
      show();
    }
  }

  // 전광판이 깨졌거나 20초가 지나면 다시 깨우기 (네모칸 자동 복구)
  if (Wire.getWireTimeoutFlag()) {
    Wire.clearWireTimeoutFlag();
    wakeLcd();
    show();
  } else if (millis() - lastWake > 20000) {
    wakeLcd();
    show();
  }

  // 연습 모드
  if (lastReal == 0 || millis() - lastReal > 15000) {
    co2 += step;
    if (co2 >= 1000) step = -10;
    if (co2 <= 450)  step = 10;
    updateLevel();
    show();
    delay(150);
  }
}

// ===== 4. 도우미 =====
void updateLevel() {
  int old = level;
  if (level == 0 && co2 >= WARN_AT) level = 1;
  if (level == 1 && co2 >= OPEN_AT) level = 2;
  if (level == 2 && co2 < OPEN_AT - GAP) level = (co2 < WARN_AT - GAP) ? 0 : 1;
  if (level == 1 && co2 < WARN_AT - GAP) level = 0;

  bool real = (lastReal != 0) && (millis() - lastReal <= 15000);
  if (level != old && real) playSound(old, level);   // 진짜 값일 때만 소리
}

void playSound(int from, int to) {
  if (from == 0 && to == 1) {
    tone(BUZZER, 880, 250);                           // 노랑: "띵~"
  } else if (to == 2) {
    for (int i = 0; i < 3; i++) {                     // 빨강: 사이렌 3번
      for (int f = 700; f <= 1600; f += 30) { tone(BUZZER, f); delay(6); }
      for (int f = 1600; f >= 700; f -= 30) { tone(BUZZER, f); delay(6); }
    }
    noTone(BUZZER);
  } else if (to == 0) {
    tone(BUZZER, 523, 150); delay(180);               // 초록 복귀: 도·미·솔
    tone(BUZZER, 659, 150); delay(180);
    tone(BUZZER, 784, 300); delay(320);
    noTone(BUZZER);
  }
}

void wakeLcd() {
  lcd.init();
  lcd.backlight();
  lastWake = millis();
}

void show() {
  lcd.setCursor(0, 0);
  lcd.print("CO2 ");
  if (co2 < 1000) lcd.print(" ");
  if (co2 < 100)  lcd.print(" ");
  lcd.print(co2);
  lcd.print(" ppm    ");

  lcd.setCursor(0, 1);
  if (level == 2)      lcd.print("OPEN WINDOW!    ");
  else if (level == 1) lcd.print("WARNING         ");
  else                 lcd.print("GOOD            ");

  digitalWrite(GREEN,  level == 0 ? HIGH : LOW);
  digitalWrite(YELLOW, level == 1 ? HIGH : LOW);
  digitalWrite(RED,    level == 2 ? HIGH : LOW);

  if (level == 2) fanOn = true;      // 빨강이면 팬 켜기
  if (level == 0) fanOn = false;     // 초록으로 돌아와야 끄기
  digitalWrite(FAN, fanOn ? RELAY_ON : RELAY_OFF);
}

// 20 kHz software PWM on D11 to drive TTL laser (yellow wire)
// Fades 0→100%→0%, holding each step ~10 ms

const uint8_t pwmPin = 11;
const uint32_t pwmFreq = 20000;   // 20 kHz within module’s 50 kHz limit
const uint32_t period_us = 1000000UL / pwmFreq;  // 50 us period

void setup() {
  pinMode(pwmPin, OUTPUT);
}

void runPWM(uint8_t duty /*0-255*/, uint32_t hold_ms) {
  // Convert 0-255 to high time (us) within a 50 µs period
  uint32_t high_us = (uint32_t)duty * period_us / 255;
  uint32_t cycles = (hold_ms * 1000UL) / period_us;
  for (uint32_t i = 0; i < cycles; i++) {
    digitalWrite(pwmPin, HIGH);
    delayMicroseconds(high_us);
    digitalWrite(pwmPin, LOW);
    delayMicroseconds(period_us - high_us);
  }
}

void loop() {
  for (int v = 0; v <= 255; v++) runPWM(v, 10);
  for (int v = 255; v >= 0; v--) runPWM(v, 10);
}
// HLK-LD1115H-24G starter reader on Arduino Nano Every
//
// Wiring (Nano Every ↔ HLK-LD1115H-24G):
//   Nano Every D0 (RX)  <-- Radar TX   (radar sends data to Arduino)
//   Nano Every D1 (TX)  --> Radar RX   (Arduino sends config commands to radar)
//   Nano Every GND      <---> Radar GND (common ground required)
//   Nano Every 5V       --> Radar VCC  (power supply, check your module specs;
//                                        some modules want 3.3V logic on RX.
//                                        If so, add a voltage divider on D1->Radar RX)
//
// Notes:
// - Do NOT cross TX/RX twice: Arduino RX (D0) must go to Radar TX.
// - The radar outputs TTL-level serial at 115200 baud.
// - Serial (USB) is used for logging to your computer.
// - Serial1 (D0/D1) is used to talk to the radar.

#define STARTUP_DELAY 15000
bool is_running = false;

void setup() {
  is_running = false;

  // USB logging back to your computer
  Serial.begin(115200);

  // Radar connection on Serial1 (pins D0 = RX, D1 = TX)
  Serial1.begin(115200);
  Serial.println("HLK-LD1115H-24G radar demo starting...");
}

void loop() {
  int remaining_time_ms = STARTUP_DELAY - millis();
  if (!is_running) {
    if (remaining_time_ms > 0) {
      Serial.print("Sensor warming, ms left: ");
      Serial.print(remaining_time_ms, DEC);
      Serial.println("");
      delay(1000);
      return;
    }
    else {
      is_running = true;
    }
  }

  // Forward anything received from the radar to your computer
  while (Serial1.available()) {
    char c = Serial1.read();
    // Skip NULs and other non-printables except CR/LF
    if ((unsigned char) c == 0x00) continue;
    if (c != '\r' && c != '\n' && (c < 0x20 || c > 0x7E)) continue;

    Serial.write(c);
  }

  // Optional: forward any keystrokes from the Serial Monitor
  // down to the radar (e.g. sending config commands like "th1=100")
  while (Serial.available()) {
    char c = Serial.read();
    Serial1.write(c);
  }
}
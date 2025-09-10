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
int motion_value = 0;
int occupancy_value = 0;
int input_pos = 0;  // current write position in input_buffer
static void parseRadarLine(const char* line);

#define INPUT_BUFFER_LEN 32
char input_buffer[INPUT_BUFFER_LEN];

void setup() {
  is_running = false;

  // USB logging back to your computer
  Serial.begin(115200);

  // Radar connection on Serial1 (pins D0 = RX, D1 = TX)
  Serial1.begin(115200);

  // Configure sensor parameters
  Serial1.println("th1=250");
  memset(input_buffer, 0, INPUT_BUFFER_LEN);
  input_pos = 0;

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

    // Echo filtered characters to USB serial for visibility
    //if (!((unsigned char)c == 0x00) && (c == '\r' || c == '\n' || (c >= 0x20 && c <= 0x7E))) {
    //  Serial.write(c);
    //}

    // Build a line for parsing (accept printable ASCII; newline terminates)
    if (c == '\r' || c == '\n') {
      if (input_pos > 0) {
        // Terminate the string
        if (input_pos >= INPUT_BUFFER_LEN) input_pos = INPUT_BUFFER_LEN - 1;
        input_buffer[input_pos] = '\0';
        // Parse the completed line
        parseRadarLine(input_buffer);
        // Reset buffer
        memset(input_buffer, 0, INPUT_BUFFER_LEN);
        input_pos = 0;
      }
      // ignore multiple CR/LF sequences
      continue;
    }

    // Accept only printable ASCII into the buffer
    if (c >= 0x20 && c <= 0x7E) {
      if (input_pos < INPUT_BUFFER_LEN - 1) {
        input_buffer[input_pos++] = c;
      } else {
        // Buffer full without newline; flush and restart to avoid overflow
        input_buffer[INPUT_BUFFER_LEN - 1] = '\0';
        parseRadarLine(input_buffer);
        memset(input_buffer, 0, INPUT_BUFFER_LEN);
        input_pos = 0;
      }
    }
  }

  // Optional: forward any keystrokes from the Serial Monitor
  // down to the radar (e.g. sending config commands like "th1=100")
  while (Serial.available()) {
    char c = Serial.read();
    Serial1.write(c);
  }
}
static void parseRadarLine(const char* line) {
  // Expected formats:
  //   "mov, <bin> <strength>"  -> update motion_value with <strength>
  //   "occ, <bin> <strength>"  -> update occupancy_value with <strength>
  // Ignore the first integer (spectral bin) and capture the second integer (signal strength)

  if (strncmp(line, "mov,", 4) == 0) {
    int strength = 0;
    if (sscanf(line, "mov, %*d %d", &strength) == 1) {
      motion_value = strength;
      Serial.print("motion_value=");
      Serial.println(motion_value);
    }
    return;
  }

  if (strncmp(line, "occ,", 4) == 0) {
    int strength = 0;
    if (sscanf(line, "occ, %*d %d", &strength) == 1) {
      occupancy_value = strength;
      Serial.print("occupancy_value=");
      Serial.println(occupancy_value);
    }
    return;
  }
}
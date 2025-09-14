// Baud: 115200, line endings: Newline (\n)

/*
 * DELTA BOARD
 * Laser D6
 * Laser E0
 * Laser F6
 * Laser G1
 * Laser G3
 **/

#include <Arduino.h>

static const char name[8] = "DELTA";

#define SERIAL_BAUD 115200

static int32_t g_value = 12345;  // lives in RAM

void setup() {
  Serial.begin(SERIAL_BAUD);

  // Give USB 2s to enumerate, but do not block forever
  unsigned long start = millis();
  while (!Serial && (millis() - start) < 2000) { }

  Serial.println("READY");
}

void loop() {
  static char buf[64];
  static size_t len = 0;

  // Read bytes into a simple line buffer
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      // End of line reached. Process command if we have any chars.
      if (len > 0) {
        buf[len] = '\0';

        // Trim trailing spaces
        while (len > 0 && (buf[len - 1] == ' ' || buf[len - 1] == '\t')) {
          buf[--len] = '\0';
        }

        // Process commands
        if (strcasecmp(buf, "NAME") == 0) {
          Serial.println(name);
        }
        else {
          Serial.println("ERR: Unknown cmd");
        }
      }
      // Reset buffer for next line
      len = 0;
    }
    else {
      if (len < (sizeof(buf) - 1)) {
        buf[len++] = c;
      }
      else {
        // Overflow: reset and report
        len = 0;
        Serial.println("ERR: Overflow");
      }
    }
  }
}
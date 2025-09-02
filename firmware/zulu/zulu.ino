// Nano Every minimal serial key-value demo
// Baud: 115200, line endings: Newline (\n)

#include <Arduino.h>

static const char name[8] = "BRAVO";

static int32_t g_value = 12345;  // lives in RAM

void setup() {
  Serial.begin(115200);
  // Give USB a moment to enumerate, but do not block forever
  unsigned long start = millis();
  while (!Serial && (millis() - start) < 2000) { /* wait up to ~2s */ }

  Serial.println("READY");  // one-time boot message
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
        if (strcasecmp(buf, "GET") == 0) {
          Serial.println(g_value);
        } else if (strncasecmp(buf, "SET", 3) == 0) {
          // Expect: SET <int>
          const char* p = buf + 3;
          // Skip spaces
          while (*p == ' ' || *p == '\t') p++;
          if (*p == '\0') {
            Serial.println("ERR Missing integer");
          } else {
            // Parse as 32-bit signed
            char* endp = nullptr;
            long v = strtol(p, &endp, 10);
            if (endp == p) {
              Serial.println("ERR Bad integer");
            } else {
              g_value = (int32_t)v;
              Serial.println("OK");
            }
          }
        } else if (strcasecmp(buf, "PING") == 0) {
          Serial.println("PONG");
        } else if (strcasecmp(buf, "NAME") == 0) {
          Serial.println(name);
        } else {
          Serial.println("ERR Unknown");
        }
      }
      // Reset buffer for next line
      len = 0;
    } else {
      if (len < (sizeof(buf) - 1)) {
        buf[len++] = c;
      } else {
        // Overflow: reset and report
        len = 0;
        Serial.println("ERR Too long");
      }
    }
  }
}
#include <Arduino.h>
#include <ArduinoJson.h>

/*
  LV-MaxSonar-EZ0 (MB1000) continuous read + JSON USB API (Nano Every)

  Protocol (USB CDC on Serial):
    {"get":true}
  Response:
    {"ok":true,"raw":"R123","inches":123,"age_ms":7}

  Wiring:
    Sensor TX (pin 5) -> Nano Every RX header pin (label "RX", header pin 17)
    Sensor RX (pin 4) left open or held HIGH for free-run (~49 ms period)
    Sensor BW (pin 1) open or LOW so TX outputs ASCII R###<CR> at 9600 8N1
    5V and GND to sensor supply
*/

static volatile uint32_t last_ts_ms = 0;   // millis when last complete frame parsed
static volatile int      last_inches = -1; // last parsed inches (0..255)
static volatile char     last_raw[6] = ""; // "R###"
static volatile bool     have_frame = false;

static char s1buf[16];
static uint8_t s1len = 0;

static char inbuf[160];
static size_t inlen = 0;

// Fog control output (idle LOW)
static const uint8_t FOG_PIN = 7; // choose a free digital pin
static volatile bool fog_active = false;
static volatile uint32_t fog_end_ms = 0;

static void start_fog(uint32_t duration_ms) {
  noInterrupts();
  digitalWrite(FOG_PIN, HIGH);
  fog_active = true;
  fog_end_ms = millis() + duration_ms;
  interrupts();
}

static void service_fog() {
  if (fog_active) {
    uint32_t now = millis();
    // handle wraparound safely
    if ((int32_t)(now - fog_end_ms) >= 0) {
      digitalWrite(FOG_PIN, LOW);
      fog_active = false;
    }
  }
}

static void reply_ok() {
  StaticJsonDocument<64> d;
  d["ok"] = true;
  serializeJson(d, Serial);
  Serial.write('\n');
}

static void parseSerial1() {
  while (Serial1.available()) {
    char c = (char)Serial1.read();
    if (c == '\r' || c == '\n') {
      if (s1len >= 4 && s1buf[0] == 'R' && isDigit(s1buf[1]) && isDigit(s1buf[2]) && isDigit(s1buf[3])) {
        s1buf[4] = '\0';
        int val = (s1buf[1]-'0')*100 + (s1buf[2]-'0')*10 + (s1buf[3]-'0');
        noInterrupts();
        strncpy((char*)last_raw, s1buf, sizeof(last_raw));
        last_raw[4] = '\0';
        last_inches = val;
        last_ts_ms = millis();
        have_frame = true;
        interrupts();
      }
      s1len = 0;
    } else {
      if (s1len < sizeof(s1buf)-1) s1buf[s1len++] = c;
      else s1len = 0; // overflow guard
    }
  }
}

static void reply_error(const char* msg) {
  StaticJsonDocument<128> d;
  d["ok"] = false;
  d["err"] = msg;
  serializeJson(d, Serial);
  Serial.write('\n');
}

static void reply_reading() {
  int inches; char rawc[6]; uint32_t ts; bool have;
  noInterrupts();
  inches = last_inches;
  strncpy(rawc, (const char*)last_raw, sizeof(rawc)); rawc[5] = '\0';
  ts = last_ts_ms;
  have = have_frame;
  interrupts();

  StaticJsonDocument<192> d;
  if (!have) {
    d["ok"] = false;
    d["err"] = "no_data_yet";
  } else {
    d["ok"] = true;
    d["raw"] = rawc;
    d["inches"] = inches;
    d["age_ms"] = (uint32_t)(millis() - ts);
  }
  serializeJson(d, Serial);
  Serial.write('\n');
}

void setup() {
  // USB CDC for JSON API
  Serial.begin(2000000);
  Serial.setTimeout(0);

  // Sensor serial. The sensor transmits ASCII R###<CR> at 9600 8N1.
  Serial1.begin(9600);

  // Fog output pin setup
  pinMode(FOG_PIN, OUTPUT);
  digitalWrite(FOG_PIN, LOW);

  // Give the sensor a short time to power up; it calibrates on first cycle.
  delay(300); // see General Power-Up Instruction and first-read timing guidance. 
}

void loop() {
  // Always keep the cache fresh
  parseSerial1();
  service_fog();

  // Handle one-line JSON on USB
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (inlen) {
        inbuf[inlen] = 0;
        StaticJsonDocument<160> doc;
        DeserializationError e = deserializeJson(doc, inbuf);
        inlen = 0;

        if (e) { reply_error("bad_json"); continue; }

        // Backward compatibility: {"get":true}
        if (doc["get"] == true) {
          reply_reading();
          continue;
        }

        const char* hw = doc["hardware"] | (const char*)nullptr;
        const char* cmd = doc["command"] | (const char*)nullptr;
        JsonVariant payload = doc["payload"];

        if (!hw || !cmd) { reply_error("missing_fields"); continue; }

        // Handle READ commands
        if (strcmp(cmd, "read") == 0) {
          if (strcmp(hw, "distance") == 0) {
            reply_reading();
          } else if (strcmp(hw, "fog") == 0) {
            // Return simple fog status
            StaticJsonDocument<128> d;
            d["ok"] = true;
            d["hardware"] = "fog";
            d["active"] = fog_active;
            d["remaining_ms"] = fog_active ? (uint32_t)(fog_end_ms - millis()) : 0;
            serializeJson(d, Serial);
            Serial.write('\n');
          } else {
            reply_error("unknown_hardware");
          }
          continue;
        }

        // Handle ENABLE commands (only makes sense for fog)
        if (strcmp(cmd, "enable") == 0) {
          if (strcmp(hw, "fog") != 0) { reply_error("unsupported_cmd_for_hardware"); continue; }
          if (payload.isNull() || !payload.containsKey("duration")) { reply_error("bad_payload"); continue; }
          uint32_t dur = payload["duration"].as<uint32_t>();
          if (dur == 0) { reply_error("bad_duration"); continue; }
          start_fog(dur);

          StaticJsonDocument<160> d;
          d["ok"] = true;
          d["hardware"] = "fog";
          d["command"] = "enable";
          d["duration"] = dur;
          serializeJson(d, Serial);
          Serial.write('\n');
          continue;
        }

        // Unknown command
        reply_error("unknown_cmd");
      }
    } else if (inlen + 1 < sizeof(inbuf)) {
      inbuf[inlen++] = c;
    }
  }
}
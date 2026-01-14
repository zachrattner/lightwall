#include <Arduino.h>
#include <string.h>
#include <stdlib.h>
#include <RadarSensor.h>

RadarSensor radar(2, 3); 

#define SERIAL_BAUD_RATE         115200
#define RADAR_BAUD_RATE          256000
#define BOOTUP_DELAY_MS          2000
#define NAME_BUFFER_SIZE         8
#define DATA_TIMEOUT_MS          1000 

typedef struct {
    unsigned int timestamp_ms;
    int x_mm;
    int y_mm;
    int distance_mm;
    int angle_deg;
    int speed_cm_s;
} radar_reading_t;

radar_reading_t latest_radar_reading;
unsigned long last_valid_packet_ms = 0;

static const char name[NAME_BUFFER_SIZE] = "PAPA";

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  radar.begin(RADAR_BAUD_RATE);
  
  memset(&latest_radar_reading, 0, sizeof(radar_reading_t));

  uint32_t t0 = millis();
  while (!Serial && (millis() - t0 < BOOTUP_DELAY_MS)) { }
  Serial.println("READY");
}

void loop() {
  unsigned long now = millis();

  if (radar.update()) {
    last_valid_packet_ms = now;
    
    RadarTarget tgt = radar.getTarget();
    latest_radar_reading.timestamp_ms = now;
    latest_radar_reading.x_mm = tgt.x;
    latest_radar_reading.y_mm = tgt.y;
    latest_radar_reading.distance_mm = tgt.distance;
    latest_radar_reading.angle_deg = tgt.angle;
    latest_radar_reading.speed_cm_s = tgt.speed;
  }

  // If we haven't heard from the sensor in 1 second, reset data to 0
  if (now - last_valid_packet_ms > DATA_TIMEOUT_MS) {
     memset(&latest_radar_reading, 0, sizeof(radar_reading_t));
     latest_radar_reading.timestamp_ms = now; 
  }

  // Handle serial commands
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.equalsIgnoreCase("NAME")) {
      Serial.println(name);
    }
    else if (cmd.equalsIgnoreCase("READ")) {
      Serial.print(latest_radar_reading.timestamp_ms);
      Serial.print(" ");
      Serial.print(latest_radar_reading.x_mm);
      Serial.print(" ");
      Serial.print(latest_radar_reading.y_mm);
      Serial.print(" ");
      Serial.print(latest_radar_reading.distance_mm);
      Serial.print(" ");
      Serial.print(latest_radar_reading.angle_deg);
      Serial.print(" ");
      Serial.println(latest_radar_reading.speed_cm_s);
    }
    else if (cmd.length() > 0) {
      Serial.println("ERR: unknown command");
    }
  }
}
// https://core-electronics.com.au/guides/detect-and-track-humans-with-mmwave-radar-on-an-arduino

#include <RadarSensor.h>

RadarSensor radar(2,3); // RX, TX pins to sensor TX, RX pins

void setup() {
  Serial.begin(115200);
  radar.begin(256000);
  Serial.println("Radar Sensor Started");
}

void loop() {
  if(radar.update()) {

    RadarTarget tgt = radar.getTarget();
    Serial.print("X (mm): "); Serial.println(tgt.x);
    Serial.print("Y (mm): "); Serial.println(tgt.y);
    Serial.print("Distance (mm): "); Serial.println(tgt.distance);
    Serial.print("Angle (degrees): "); Serial.println(tgt.angle);
    Serial.print("Speed (cm/s): "); Serial.println(tgt.speed);
    Serial.println("-------------------------");
    delay(100);
    }
}
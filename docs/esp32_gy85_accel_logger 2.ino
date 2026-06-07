#include <Wire.h>
#include <Adafruit_ADXL345_U.h>

#define SDA_PIN 8
#define SCL_PIN 9

Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);

unsigned long startTime;

void setup() {
  Serial.begin(115200);
  delay(1000);

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!accel.begin()) {
    Serial.println("ERROR: ADXL345 not found on GY-85");
    while (1) {
      delay(100);
    }
  }

  accel.setRange(ADXL345_RANGE_16_G);

  startTime = millis();

  Serial.println("time_ms,ax,ay,az,accel_mag");
}

void loop() {
  sensors_event_t event;
  accel.getEvent(&event);

  unsigned long timeMs = millis() - startTime;

  float ax = event.acceleration.x;
  float ay = event.acceleration.y;
  float az = event.acceleration.z;

  float accelMag = sqrt(ax * ax + ay * ay + az * az);

  Serial.print(timeMs);
  Serial.print(",");
  Serial.print(ax, 4);
  Serial.print(",");
  Serial.print(ay, 4);
  Serial.print(",");
  Serial.print(az, 4);
  Serial.print(",");
  Serial.println(accelMag, 4);

  delay(10);  // 100 Hz
}

# IMU + ESP32 Extension

This document outlines a practical hardware extension path for BowTrack. The main repository is still camera-first, but an IMU can add motion signals that are difficult to recover reliably from a single view, especially bow roll, angular velocity, and stroke smoothness.

## Goal

Use a small bow-mounted IMU and an `ESP32-C3 SuperMini` to stream motion data into a desktop tool, then align that data with BowTrack video analysis.

High-level flow:

```text
IMU on bow
   -> ESP32-C3 SuperMini
   -> USB serial or BLE
   -> desktop logger / live plots
   -> CSV export
   -> optional sync with BowTrack video metrics
```

## Development environment

The firmware path is configured for `PlatformIO` with:

- board: `esp32-c3-devkitm-1`
- framework: `arduino`
- monitor speed: `115200`

The project config lives at [platformio.ini](/Users/harvardsummer/Library/Mobile%20Documents/com~apple~CloudDocs/GitHub/BowTrack/platformio.ini:1), and the firmware entry point is [src/main.cpp](/Users/harvardsummer/Library/Mobile%20Documents/com~apple~CloudDocs/GitHub/BowTrack/src/main.cpp:1).

Typical PlatformIO commands:

```bash
pio run --target upload
pio device monitor
```

## Recommended sensor choices

### Best practical choice: `BNO085`

If the goal is the cleanest engineering path, `BNO085` is the strongest option because it provides fused orientation directly. That makes it especially useful for:

- bow roll
- bow tilt
- angular stability
- smoothness estimation

It reduces the amount of sensor-fusion code needed on the microcontroller or desktop side.

### Best advanced choice: `ICM-20948`

If the goal is deeper control and a more advanced implementation, `ICM-20948` is a strong 9-axis option. It is better suited than older modules for a more polished prototype, but it expects you to handle more of the filtering and calibration work yourself.

### Best low-cost choice: `GY-85`

`GY-85` is a valid and practical sensor for this project. It is especially attractive when cost matters, when the goal is to get a hardware prototype running quickly, or when the main objective is to prove the data pipeline before investing in a more refined sensor stack.

The `GY-85` combines:

- `ITG3205` gyroscope
- `ADXL345` accelerometer
- `HMC5883L` magnetometer
- `BMP085` barometric pressure sensor

That means it is a real low-cost `9-axis` IMU option for BowTrack. The `BMP085` does not add axes, but it does not hurt anything either. For this project, the main useful signals are still the accelerometer, gyroscope, and magnetometer.

The main reason to treat `GY-85` as an entry-point sensor is not that it lacks axes. It does have the full `3 + 3 + 3` sensing stack. The limitation is more about polish:

- the chips are older than newer integrated IMUs
- the board is bulkier than more compact modern options
- calibration and sensor-fusion work tend to be more manual
- orientation is usually less convenient than on newer fused-sensor modules

So the right way to think about it is:

- `GY-85` is a strong low-cost prototype sensor
- `BNO085` is the easiest path to stable orientation
- `ICM-20948` is a stronger advanced option if we want more control

## Why the ESP32-C3 works well

The `ESP32-C3 SuperMini` is a good fit because it gives us:

- I2C for the IMU
- enough processing for sensor logging and simple filtering
- USB serial for easy development
- BLE for a wireless version
- low cost and small size

For BowTrack, that means:

1. a simple wired prototype
2. an optional wireless practice tool
3. a clean path toward sensor fusion with the video pipeline

## Suggested implementation path

### Wired IMU logger

Start with:

- `ESP32-C3 SuperMini`
- `GY-85` as the main low-cost sensor, or a newer IMU
- USB cable to the desktop

Use this phase to verify:

- sensor wiring
- stable sampling
- serial CSV output
- basic plots for acceleration and angular velocity

### Desktop live viewer

Add a desktop tool to:

- connect over serial
- show live acceleration and gyro graphs
- record CSV sessions
- export data for BowTrack video sync

Recommended stack:

- `Python`
- `PySide6`
- `pyqtgraph`
- `pyserial`
- `numpy`
- `PyOpenGL`
- `PyOpenGL_accelerate`

### BowTrack sensor fusion

Combine:

- camera-based bow angle error
- camera-based contact-point drift
- shoulder/posture fallback when bow detection is weak
- IMU-based roll, angular velocity, and jerk

This is the point where BowTrack becomes a richer practice-analysis system rather than just a video overlay tool.

## Wiring for a `GY-85`

Use I2C:

```text
GY-85            ESP32-C3 SuperMini
VCC      ------> 3V3
GND      ------> GND
SDA      ------> GPIO8
SCL      ------> GPIO9
```

Basic note:

- use `3.3V`
- start with USB power during development
- expect some soldering and physical mounting work

## Expected I2C devices

On many `GY-85` boards, a scan will typically find addresses like:

- `0x53` for `ADXL345`
- `0x68` for `ITG3205`
- `0x1E` for `HMC5883L`

That is a good first wiring check before writing higher-level code.

Starter I2C scanner sketch:

```cpp
#include <Wire.h>

static const int SDA_PIN = 8;
static const int SCL_PIN = 9;

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println("Scanning I2C...");
}

void loop() {
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("Found device at 0x");
      Serial.println(address, HEX);
    }
  }
  Serial.println("Done");
  delay(5000);
}
```

## Firmware guidance

The first firmware milestone should capture:

- timestamp
- accelerometer data
- gyroscope data
- optionally magnetometer data

Suggested CSV serial format:

```text
time_ms,ax,ay,az,gx,gy,gz,mx,my,mz
```

Example row:

```text
1020,0.12,-0.03,9.71,0.4,0.2,-0.1,35.1,-12.4,8.2
```

For the first implementation, a `100-200 Hz` sample rate is a good target.

Minimal firmware goals:

- read accelerometer and gyroscope data
- emit one CSV row per sample
- avoid blocking serial output as much as possible
- keep a stable time base using `millis()` or `micros()`

Starter firmware shape:

```cpp
// Pseudocode structure
void setup() {
  init_serial();
  init_i2c();
  init_imu();
  print_header("time_ms,ax,ay,az,gx,gy,gz,mx,my,mz");
}

void loop() {
  Sample sample = read_imu_sample();
  print_csv_row(sample);
  delay(10);  // about 100 Hz to start
}
```

If the first prototype uses a `GY-85`, it is reasonable to start with just `ADXL345 + ITG3205` before adding the magnetometer. The current PlatformIO-ready firmware is available in [src/main.cpp](/Users/harvardsummer/Library/Mobile%20Documents/com~apple~CloudDocs/GitHub/BowTrack/src/main.cpp:1), and the Arduino sketch copy is available in [esp32_gy85_accel_logger.ino](/Users/harvardsummer/Library/Mobile%20Documents/com~apple~CloudDocs/GitHub/BowTrack/docs/esp32_gy85_accel_logger.ino:1).

## Desktop app guidance

The first desktop tool does not need to be complicated. It should do four things well:

1. connect to the serial port
2. plot live channels
3. record CSV
4. export a session that can be aligned with video

Recommended Python packages:

```bash
pip install PySide6 pyqtgraph pyserial numpy
```

Minimal desktop responsibilities:

```text
- read serial lines
- parse CSV rows
- append samples to rolling buffers
- update live plots
- optionally save rows to disk
```

Suggested session columns:

```text
time_ms,ax,ay,az,gx,gy,gz,mx,my,mz,notes
```

## Important measurement caveat

Do not treat double-integrated accelerometer data as true bow position. Position estimates from raw acceleration will drift quickly. For this project, the IMU is most useful for:

- orientation
- angular velocity
- roll / tilt changes
- jerk and smoothness signals
- motion event detection such as string crossings

If the desktop tool shows a trajectory, it should be labeled as a rough visualization rather than a precise physical path.

## BowTrack metrics that benefit most from an IMU

The best early sensor-fusion targets are:

- `bow roll / tilt`
- `angular velocity`
- `stroke smoothness`
- `jerk`
- `string-crossing motion spikes`

The camera can still carry:

- bridge reference estimation
- bow angle relative to the bridge
- contact-point drift
- shoulder posture and fallback analysis

## Example parts list

These are example purchase links shared during development. Prices can change, and these notes are included as a practical build record rather than a long-term guarantee.

- `GY-85 BMP085 Sensor Modules 9 Axis Sensor Module (ITG3205 + ADXL345 + HMC5883L), 6DOF/9DOF IMU Sensor`
  - Approx. price noted: `$4.38`
  - Note: requires soldering
  - Link: [AliExpress listing](https://www.aliexpress.us/item/3256803649766316.html?spm=a2g0o.order_list.order_list_main.22.51f618027m97bX&gatewayAdapt=glo2usa)

- `2pcs ESP32C3 Supermini Development Board`
  - Approx. price noted: `$5.49` for two pieces
  - Note: requires soldering
  - Link: [Temu listing](https://www.temu.com/goods.html?_bg_fs=1&goods_id=606169150155587&parent_order_sn=PO-211-06234479867513254&_oak_order_sn=211-06234534917753254&_oak_goods_num=1&sku_id=88630542522956&_x_sessn_id=4sl5sdt1i6&refer_page_name=bgt_order_detail&refer_page_id=10045_1780840080033_b6qkacfibg&refer_page_sn=10045)

- `WEP 926LED V3 Soldering Station 130W MAX Soldering Iron Kit`
  - Approx. price noted: `$29.99`
  - Includes solder wire, tips, tweezers, solder sucker, tip cleaner, temperature control, sleep mode, and C/F conversion
  - Link: [Amazon listing](https://www.amazon.com/dp/B0BX2N258S?ref_=ppx_hzsearch_conn_dt_b_fed_asin_title_3)

## What to implement next

1. Add a simple I2C scanner sketch and confirm the IMU addresses.
2. Add an ESP32 logger that outputs `accel + gyro + timestamps`.
3. Add a small desktop logger in Python for live plots and CSV recording.
4. Sync one IMU session with one BowTrack video clip.
5. Test whether IMU-derived smoothness or roll improves the feedback beyond camera-only analysis.

## Design principle

Following the violin bow-interface literature, the hardware should remain optional, lightweight, and as nonintrusive as possible. The camera-first path is still the default. The IMU path is only worth keeping if it adds real feedback value without making the setup awkward for normal practice.

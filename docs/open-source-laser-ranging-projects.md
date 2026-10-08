# Open-source starting points for laser ranging and LiDAR integration

A categorised list of repositories that are actually useful when you are integrating a laser
rangefinder or LiDAR into something. Single-point DToF modules, 2D scanners, flight stacks, and the
message standards that connect them.

**Every link in this file was checked and returns HTTP 200** before publication. An earlier draft of
this list contained three repositories that did not exist — plausible-looking names I had
misremembered. They were removed. A list that sends you to a 404 wastes the only thing you were
going to give it, which is thirty seconds of trust.

**Disclosure:** I maintain entry 1.1. It is marked as such. Everything else here is other people's
work and none of it is affiliated with me.

---

## 1. Single-point DToF ranging modules

These are the closest cousins of an industrial 905 nm ranging module: one beam, one distance, a
serial or I²C interface.

### 1.1 `erdilrf/erdilrf-drivers` — *maintained by the author of this list*

<https://github.com/erdilrf/erdilrf-drivers>

Host driver (Python, zero dependencies) and a header-only Arduino/C++ driver for the **LR1000E2 8-byte
UART protocol family**, plus a full protocol reference and a `decode` CLI that parses a captured frame
with no hardware attached. 50 tests, none requiring a serial port.

Worth reading even if you use a different module: [`protocol/verification.md`](https://github.com/erdilrf/erdilrf-drivers/blob/main/protocol/verification.md)
re-derives a manufacturer's checksums from the stated rule rather than trusting the printed values,
and [`docs/what-the-datasheet-does-not-say.md`](https://github.com/erdilrf/erdilrf-drivers/blob/main/docs/what-the-datasheet-does-not-say.md)
documents four gaps in a published datasheet. The method transfers; the constants do not.

### 1.2 `budryerson/TFMINI-Plus`

<https://github.com/budryerson/TFMINI-Plus>

Arduino library for the **Benewake TFMini-Plus and TFMini-S** LiDAR distance sensors. The de-facto
community library for these modules, and the reference for how to structure a driver that has to cope
with two firmware variants of the same product.

Also see [`budryerson/TFMini-Plus-I2C`](https://github.com/budryerson/TFMini-Plus-I2C) for the I²C
variant — useful because it shows the same device behind two different physical layers.

### 1.3 `garmin/LIDARLite_v3_Arduino_Library`

<https://github.com/garmin/LIDARLite_v3_Arduino_Library>

First-party Arduino library for the **Garmin LIDAR-Lite v3**. A vendor publishing its own driver is
rarer than it should be, and this one is a decent model for what a vendor driver ought to contain.

### 1.4 VL53L0X / VL53L1X — the ST ToF family

Short-range ToF sensors with the widest ecosystem of any ranging part, which makes them the fastest
way to get *any* working distance pipeline before you commit to a long-range module.

| Repository | Note |
|---|---|
| <https://github.com/stm32duino/VL53L1X> | ST's own Arduino core library for VL53L1X |
| <https://github.com/pololu/vl53l0x-arduino> | Pololu's VL53L0X library — exceptionally clear register-level code |
| <https://github.com/adafruit/Adafruit_VL53L0X> | Adafruit's, with the usual tutorial support |
| <https://github.com/DFRobot/DFRobot_VL53L0X> | DFRobot's, for their breakout boards |

Range is centimetres to a few metres, not hundreds. Use them to validate your I²C plumbing and your
data path; do not use them to validate a long-range optical design.

---

## 2. 2D scanning LiDAR

If you need a scan plane rather than a point.

| Repository | What it is |
|---|---|
| <https://github.com/Slamtec/rplidar_sdk> | Slamtec RPLIDAR SDK — the most widely deployed low-cost 2D LiDAR |
| <https://github.com/ldrobotSensorTeam/ldlidar_stl_ros2> | LD06/LD19 ROS 2 driver — very common on small robots |
| <https://github.com/YDLIDAR/ydlidar_ros2_driver> | YDLIDAR ROS 2 driver |

These are scanning mechanisms: a spinning or rotating assembly producing a point cloud, not a single
range. If your problem is "how far to that one thing", a single-point module will be smaller, cheaper,
faster and far easier to power.

---

## 3. 3D and automotive-grade

Heavier, and mostly relevant if you are building perception rather than measurement.

| Repository | What it is |
|---|---|
| <https://github.com/Livox-SDK/Livox-SDK2> | Livox non-repetitive-scanning LiDAR SDK |
| <https://github.com/ouster-lidar/ouster-ros> | Ouster ROS driver |
| <https://github.com/ros-drivers/velodyne> | Velodyne ROS driver — long-lived, still worth reading for ROS conventions |

---

## 4. Flight stacks — where rangefinders actually get used

If you are putting a ranging module on an aircraft, do not write the integration from scratch. Both
major open-source stacks already have a rangefinder abstraction, and both have absorbed years of
hardware-specific failure modes.

| Repository | Note |
|---|---|
| <https://github.com/PX4/PX4-Autopilot> | `src/drivers/distance_sensor/` — many modules, one interface |
| <https://github.com/ArduPilot/ardupilot> | `libraries/AP_RangeFinder/` — the same idea, different abstractions |
| <https://github.com/mavlink/mavlink> | The `DISTANCE_SENSOR` message — how a rangefinder's output reaches a ground station |

Reading two independent implementations of the same abstraction is a fast way to learn which parts of
*your* interface are real constraints and which are habits.

---

## 5. How to read a ranging module driver

Across all of the above, the same four questions decide whether a driver is usable:

1. **Does it distinguish "no answer" from "measurement failed"?** These have completely different
   causes — a cable versus a target — and a driver that returns one error code for both costs you an
   afternoon every time.
2. **Does it resynchronise on a corrupted frame, or does one bad byte poison the stream?** Look for a
   header-scan or a rolling buffer.
3. **Does it state its physical-layer assumptions, or silently guess them?** Parity, stop bits and
   logic levels are the usual silent guesses.
4. **Does it say what it does not know?** A driver whose documentation admits a gap is more reliable
   than one that reads as complete, because completeness in a hardware driver is usually a sign that
   something was assumed rather than measured.

Point 4 is the one that separates the good ones. Hardware documentation that never says "unknown" has
either tested everything or is hiding something, and in open source it is usually the latter.

---

## Contributing

Corrections are the most valuable contribution: if a link here has died, or a repository has been
superseded, open an issue on
[`erdilrf/erdilrf-drivers`](https://github.com/erdilrf/erdilrf-drivers/issues). Broken links and
wrong characterisations both count as bugs.

# Lightwall Hardware

This directory contains the hardware specifications, 3D models, and Bill of Materials (BOM) for the Lightwall project.

## Overview

The Lightwall is powered by an Apple Mac mini (M4 Pro) which coordinates 14 white dimmable LEDs and 12 prisms mounted on motors. The system uses a suite of Arduino Nano Every controllers for localized motor and LED control, with an Arduino Uno R4 WiFi for the radar sensor. The baud rate on the radar sensor is too fast for the Nano Every, hence the Uno. The sensors to the outside world are the radar sensor and a high-fidelity microphone. The Mac mini is mounted on a custom-built wooden frame, and the piece has no visible electronics.

## Bill of Materials (BOM)

| Part | Quantity |
| :--- | :--- |
| [#8 x 1/2" Wood Screws, Black, 400 Pcs](https://www.amazon.com/dp/B0BFL62Q2Q) | 1 |
| [12 VDC Power Supply](https://www.amazon.com/dp/B07GFC4VR3) | 2 |
| [5 VDC Power Supply](https://www.amazon.com/dp/B08744HB1X) | 2 |
| [5-Port USB Hub](https://www.amazon.com/dp/B0F5HSNDXF) | 5 |
| [AC Power Splitter](https://www.amazon.com/dp/B09K3R626Z) | 1 |
| [Arduino Nano Every](https://store-usa.arduino.cc/products/nano-every-with-headers) | 15 |
| [Arduino Nano Every Screw Mount](https://www.amazon.com/dp/B096XSH1D7) | 15 |
| [Arduino Uno R4 WiFi](https://store-usa.arduino.cc/products/uno-r4-wifi) | 1 |
| [Barrel Jack Power Extender - 3 ft](https://www.amazon.com/dp/B01N3WCHG5) | 26 |
| [Barrel Jack Splitter - 8 Way](https://www.amazon.com/dp/B0DBD5R98B) | 4 |
| [Constant Current Driver for LED](https://www.amazon.com/dp/B0C2ZXXTSD) | 12 |
| [Double-Sided Tape](https://www.amazon.com/dp/B0035LXTYU) | 1 |
| [Extension Cord - 6 ft, White](https://www.amazon.com/dp/B076K93FC4) | 1 |
| [Foam Core Board, 43 x 63 Inches](https://www.dickblick.com/products/white-foam-board/) | 1 |
| [Grounding Bar](https://www.amazon.com/dp/B0BWH6BC45) | 12 |
| [Heat Sink for LEDs](https://www.amazon.com/dp/B0DJK5B5L8) | 12 |
| [Heat Sink for Stepper Motor (4 per Motor)](https://www.amazon.com/dp/B0CFKGHWKZ) | 48 |
| [Hookup Wire Kit - 25 ft](https://www.amazon.com/dp/B0DNQC9HMV) | 2 |
| [LED Lens - 5 Degrees](https://www.amazon.com/dp/B0DRNBCHN7) | 12 |
| [LED Lens Holder](https://www.amazon.com/dp/B00LWU07FK) | 12 |
| [Logitech Blue Yeti Nano USB Microphone](https://www.amazon.com/dp/B07QLNYBG9) | 1 |
| [Mac mini - Apple M4 Pro Chip](https://www.apple.com/shop/buy-mac/mac-mini/apple-m4-pro-chip-with-12-core-cpu-16-core-gpu-24gb-memory-512gb) | 1 |
| [Mac Mini Mounting Bracket](https://www.amazon.com/dp/B0DPHLT5FH) | 1 |
| [Magnet Pairs](https://www.amazon.com/dp/B072KDBJWC) | 2 |
| [Natural White Watercolor Paper - Hot Press](https://www.dickblick.com/items/arches-natural-white-watercolor-paper-44-12-x-10-yds-hot-press-roll/) | 1 |
| [Optical Beam Splitter, 25mm Cube](https://www.amazon.com/dp/B0B1LJPMD7) | 12 |
| [Plastic Hanger Strap - 100 ft](https://www.amazon.com/dp/B0DNFBYVGL) | 1 |
| [Post Mount for Optical Beam Splitter](Prism%20Collar%20-%20Rectangular%20-%20Platter.stl) | 12 |
| [Rd-03D Radar Sensor](https://www.amazon.com/dp/B0D3CXVCFK) | 1 |
| [Set Screws - M4x4mm, 100 Pack](https://www.amazon.com/dp/B01N76F56R) | 1 |
| [Stepper Motor](https://www.sparkfun.com/stepper-motor-32-oz-in-200-steps-rev-1200mm-wire.html) | 12 |
| [Stepper Motor Driver Board](https://www.sparkfun.com/sparkfun-prodriver-stepper-motor-driver-tc78h670ftg.html) | 12 |
| [Thermal Glue](https://www.amazon.com/dp/B072MSXHJD) | 1 |
| [USB C Power Brick - 60W](https://www.amazon.com/dp/B0CYZ52VPX) | 2 |
| [USB C to C Cable - 6.6 ft](https://www.amazon.com/dp/B08D6NCQ1Z) | 5 |
| [USB C to Micro B Cable - 6 ft](https://www.amazon.com/dp/B09P13V1W8) | 16 |
| [White LED, 200 Lumen, 3W, 5V](https://www.amazon.com/dp/B092R3CQVX) | 12 |
| Wood Case | 1 |

## Fabrication

The `hardware` folder contains 3D models used for the assembly:
- [Lightwall.skp](Lightwall.skp): SketchUp model of the full assembly
- [Lightwall.stl](Lightwall.stl): STL model of the full assembly
- [Prism Collar - Rectangular - Platter.stl](Prism%20Collar%20-%20Rectangular%20-%20Platter.stl): Post mount for the optical beam splitters. Ordered from [Shapeways](https://www.shapeways.com/materials/pa12)
- [Board Mapping.jpg](Board%20Mapping.jpg): Physical diagram of the Arduino boards mapping to the stepper motor and LED drivers

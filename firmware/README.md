# Lightwall Firmware

This directory contains the source code and configuration for the microcontrollers that drive the Lightwall's physical components. These sketches are deployed to a network of Arduinos connected via USB to the Mac mini.

## Architecture

The system uses a distributed control architecture:
- **Arduino Nano Every**: Handles localized control of stepper motors and LED drivers.
- **Arduino Uno R4 WiFi**: Serves as the interface for the high-speed radar sensor.

## Libraries

The `libraries/` folder contains the necessary dependencies for the firmware. Notably:
- **RD03D**: This library is used to interface with the mmWave radar sensor. It comes from [Core Electronics](https://core-electronics.com.au/guides/detect-and-track-humans-with-mmwave-radar-on-an-arduino/).

## Hardware Mapping (`hwMap.json`)

The `hwMap.json` file is a critical component of the control system. It defines the mapping between the **logical address space** (how the software addresses a specific prism or LED) and the **physical devices** (which USB port and which specific Arduino pin corresponds to that hardware).

This mapping allows the Mac mini to send high-level commands to logical assemblies without needing to know the specific wiring details, making the system easier to maintain and reconfigure.

## Board Deployment

Each subdirectory in `boards/` corresponds to a specific physical controller in the installation.

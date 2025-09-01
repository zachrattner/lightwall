#include <Arduino.h>

#include <stdint.h>

typedef uint8_t uint8;
typedef uint16_t uint16;
typedef uint32_t uint32;

typedef int8_t int8;
typedef int16_t int16;
typedef int32_t int32;

#define FALSE 0
#define TRUE 1

#define NAME_MAX_LENGTH 8
#define COMMAND_MAX_LENGTH 16

typedef enum {
  COMMAND_INIT          = 0x00,
  COMMAND_NAME          = 0x01,
  COMMAND_READ_DISTANCE = 0x02,
  COMMAND_FOG           = 0x03,
  COMMAND_SET_LASER     = 0x04,
  COMMAND_SET_MOTOR     = 0x05,
  COMMAND_UNKNOWN       = 0xff
} command_t;

typedef enum {
  STATUS_OK = 0x00,
  STATUS__COMMUNICATION_TIMEOUT = 0x01,
  STATUS__UNKNOWN = 0xff
} status_t;

typedef enum {
  LASER_ADDRESS_A1 = 0x00,
  LASER_ADDRESS_A3 = 0x01,
  LASER_ADDRESS_A5 = 0x02,
  LASER_ADDRESS_B6 = 0x03,
  LASER_ADDRESS_C0 = 0x04,
  LASER_ADDRESS_D6 = 0x05,
  LASER_ADDRESS_E0 = 0x06,
  LASER_ADDRESS_F6 = 0x07,
  LASER_ADDRESS_G1 = 0x08,
  LASER_ADDRESS_G3 = 0x09,
  LASER_ADDRESS_G5 = 0x0a,
  LASER_ADDRESS_UNKNOWN = 0xff
} laser_address_t;

typedef enum {
  MOTOR_ADDRESS_B1 = 0x00,
  MOTOR_ADDRESS_B3 = 0x01,
  MOTOR_ADDRESS_B5 = 0x02,
  MOTOR_ADDRESS_D1 = 0x03,
  MOTOR_ADDRESS_D3 = 0x04,
  MOTOR_ADDRESS_D5 = 0x05,
  MOTOR_ADDRESS_F1 = 0x06,
  MOTOR_ADDRESS_F3 = 0x07,
  MOTOR_ADDRESS_F5 = 0x08,
  MOTOR_ADDRESS_UNKNOWN = 0xff
} motor_address_t;

typedef struct {
  command_t command;
} command_init_t;

typedef struct {
  status_t status;
  uint32 timestamp;
} response_init_t;

typedef struct {
  command_t command;
} command_name_t;

typedef struct {
  status_t status;
  uint32 timestamp;
  char name[NAME_MAX_LENGTH];
} response_name_t;

typedef struct {
  command_t command;
} command_read_distance_t;

typedef struct {
  status_t status;
  uint32 timestamp;
  uint16 distance;
} response_read_distance_t;

typedef struct {
  command_t command;
  uint8 duration_sec;
} command_fog_t;

typedef struct {
  status_t status;
  uint32 timestamp;
} response_fog_t;

typedef struct {
  command_t command;
  laser_address_t laser_address;
  uint8 brightness;
  uint16 transition_time_ms;
} command_set_laser_t;

typedef struct {
  status_t status;
  uint32 timestamp;
} response_set_laser_t;

typedef struct {
  command_t command;
  motor_address_t motor_address;
  uint8 mode;
  uint16 payload;
  uint16 transition_time_ms;
} command_set_motor_t;

typedef struct {
  status_t status;
  uint32 timestamp;
} response_set_motor_t;

uint8 cmd[COMMAND_MAX_LENGTH];
void setup() {
  
}

void loop() {

}
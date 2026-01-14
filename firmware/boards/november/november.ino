#include <Arduino.h>
#include "SparkFun_ProDriver_TC78H670FTG_Arduino_Library.h"
#include <avr/io.h>
#include <avr/interrupt.h>

// Wiring (SparkFun defaults):
//   D8  -> STBY  (active HIGH to run; LOW = standby)
//   D7  -> EN    (active HIGH enable)
//   D6  -> MODE0
//   D5  -> MODE1 (also SET_EN in variable mode; we keep fixed mode here)
//   D4  -> MODE2 (CLK)
//   D3  -> MODE3 (CW/CCW)
//   D2  -> ERR   (active LOW)
// Provide motor VM power per board docs. Set hardware slide switch to USER.

#define COMMAND_READY_SEQUENCE   "READY"
#define SERIAL_BAUD_RATE         115200
#define BOOTUP_DELAY_MS          2000
#define NAME_BUFFER_SIZE         10
#define DATA_TIMEOUT_MS          1000 
#define COMMAND_BUFFER_SIZE      64

static const char name[NAME_BUFFER_SIZE] = "NOVEMBER";
static char cmd_buf[COMMAND_BUFFER_SIZE];

static bool	   is_serial_overflow = false;
static char	   cmd_current_byte   = NULL;
static uint8_t cmd_len            = 0;

// Limit power consumption by capping current
#define MOTOR_CURRENT_LIMIT 64

// Motor parameters
// Driver board: https://www.sparkfun.com/sparkfun-prodriver-stepper-motor-driver-tc78h670ftg.html
// Motor: https://www.sparkfun.com/stepper-motor-32-oz-in-200-steps-rev-1200mm-wire.html
#define BASE_FULL_STEPS_PER_ROTATION 200
#define MICROSTEP_FACTOR 1
#define STEPS_PER_ROTATION (BASE_FULL_STEPS_PER_ROTATION * MICROSTEP_FACTOR)

#define ACTION_NAME_STR     "NAME"
#define ACTION_ROTATE_STR   "ROT"
#define ACTION_STEP_STR     "STP"
#define ACTION_POSITION_STR "POS"
#define ACTION_STOP_STR     "STOP"

typedef enum {
  ACTION_NAME,
  ACTION_ROTATE,
  ACTION_STEP,
  ACTION_POSITION,
  ACTION_STOP,
  ACTION_INVALID = 0xff
} action_t;

#define DIRECTION_CW_STR  "CW"
#define DIRECTION_CCW_STR "CCW"

typedef enum {
  DIRECTION_CW,
  DIRECTION_CCW,
  DIRECTION_INVALID = 0xff
} direction_t;

typedef struct {
  action_t     action;
  direction_t  direction;
  unsigned int arg1;
  unsigned int arg2;
} serial_cmd_t;

static serial_cmd_t serial_cmd;

typedef enum {
  MOTION_NONE,
  MOTION_ROTATE_CONTINUOUS,
  MOTION_STEP_FINITE
} motion_mode_t;

static volatile motion_mode_t g_motion_mode           = MOTION_NONE;
static volatile direction_t   g_motion_direction      = DIRECTION_CW;
static volatile uint32_t      g_motion_steps_remaining = 0;
static volatile uint16_t      g_step_interval_ms      = 0;   // ms between steps
static volatile uint16_t      g_step_elapsed_ms       = 0;   // ms accumulated since last step
static volatile uint16_t      g_current_position_steps = 0;   // 0..STEPS_PER_ROTATION-1

PRODRIVER motor_driver;

static action_t parse_action_token(const String &tok) {
  if (tok.equalsIgnoreCase(ACTION_NAME_STR)) {
    return ACTION_NAME;
  }
  if (tok.equalsIgnoreCase(ACTION_ROTATE_STR)) {
    return ACTION_ROTATE;
  }
  if (tok.equalsIgnoreCase(ACTION_STEP_STR)) {
    return ACTION_STEP;
  }
  if (tok.equalsIgnoreCase(ACTION_POSITION_STR)) {
    return ACTION_POSITION;
  }
  if (tok.equalsIgnoreCase(ACTION_STOP_STR)) {
    return ACTION_STOP;
  }
  return ACTION_INVALID;
}

static direction_t parse_direction_token(const String &tok) {
  if (tok.equalsIgnoreCase(DIRECTION_CW_STR)) {
    return DIRECTION_CW;
  }
  if (tok.equalsIgnoreCase(DIRECTION_CCW_STR)) {
    return DIRECTION_CCW;
  }
  return DIRECTION_INVALID;
}

bool parse_cmd(const String &line, serial_cmd_t* cmd) {
  cmd->action    = ACTION_INVALID;
  cmd->direction = DIRECTION_INVALID;
  cmd->arg1      = 0;
  cmd->arg2      = 0;

  String s = line;
  s.trim();

  if (s.length() == 0) {
    return false;
  }

  // action
  int p1 = s.indexOf(' ');
  if (p1 < 0) {
    String actionTok = s;
    actionTok.trim();
    cmd->action = parse_action_token(actionTok);
    return true;
  }

  String actionTok = s.substring(0, p1);
  actionTok.trim();
  cmd->action = parse_action_token(actionTok);

  s = s.substring(p1 + 1);
  s.trim();

  if (s.length() == 0) {
    return true;
  }

  // direction
  int p2 = s.indexOf(' ');
  if (p2 < 0) {
    String dirTok = s;
    dirTok.trim();
    cmd->direction = parse_direction_token(dirTok);
    return true;
  }

  String dirTok = s.substring(0, p2);
  dirTok.trim();
  cmd->direction = parse_direction_token(dirTok);

  s = s.substring(p2 + 1);
  s.trim();

  if (s.length() == 0) {
    return true;
  }

  // arg1
  int p3 = s.indexOf(' ');
  if (p3 < 0) {
    cmd->arg1 = (unsigned int)s.toInt();
    return true;
  }

  String arg1Tok = s.substring(0, p3);
  arg1Tok.trim();
  cmd->arg1 = (unsigned int)arg1Tok.toInt();

  s = s.substring(p3 + 1);
  s.trim();

  if (s.length() == 0) {
    return true;
  }

  // arg2
  cmd->arg2 = (unsigned int)s.toInt();
  return true;
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  uint32_t t0 = millis();
  while (!Serial && (millis() - t0 < BOOTUP_DELAY_MS)) { }

  memset(&serial_cmd, 0, sizeof(serial_cmd_t));
  memset(&cmd_buf, 0, COMMAND_BUFFER_SIZE);

  // Set up motor
  motor_driver.settings.controlMode        = PRODRIVER_MODE_SERIAL;
  motor_driver.settings.stepResolutionMode = PRODRIVER_STEP_RESOLUTION_FIXED_FULL;
  motor_driver.begin();
  motor_driver.setCurrentLimit(MOTOR_CURRENT_LIMIT);
  motor_driver.sendSerialCommand();

  // Configure TCB0 for a 1 kHz interrupt (1 ms tick) on the Nano Every
  TCB0.CTRLA = 0;                              // disable while configuring
  TCB0.CTRLB = TCB_CNTMODE_INT_gc;             // periodic interrupt mode
  TCB0.CCMP  = 7999;                           // 8000 counts at 8 MHz = 1 ms
  TCB0.INTFLAGS = TCB_CAPT_bm;                 // clear any pending interrupt
  TCB0.INTCTRL  = TCB_CAPT_bm;                 // enable interrupt
  TCB0.CTRLA    = TCB_CLKSEL_CLKDIV2_gc | TCB_ENABLE_bm; // 16 MHz / 2 = 8 MHz, enable

  // Signal readiness
  Serial.println(COMMAND_READY_SEQUENCE);
}

ISR(TCB0_INT_vect) {
  // Clear interrupt flag
  TCB0.INTFLAGS = TCB_CAPT_bm;

  if (g_motion_mode == MOTION_NONE) {
    return;
  }
  if (g_step_interval_ms == 0) {
    return;
  }

  // 1 ms has passed
  g_step_elapsed_ms++;
  if (g_step_elapsed_ms < g_step_interval_ms) {
    return;
  }
  g_step_elapsed_ms = 0;

  bool ccw_bit = (g_motion_direction == DIRECTION_CCW);

  // Issue one step via serial each tick when due
  motor_driver.stepSerial(1, ccw_bit, 0);

  // Update absolute position in steps (0..STEPS_PER_ROTATION-1)
  if (g_motion_direction == DIRECTION_CW) {
    uint16_t pos = g_current_position_steps + 1;
    if (pos >= STEPS_PER_ROTATION) {
      pos = 0;
    }
    g_current_position_steps = pos;
  } else if (g_motion_direction == DIRECTION_CCW) {
    uint16_t pos = g_current_position_steps;
    if (pos == 0) {
      pos = STEPS_PER_ROTATION - 1;
    } else {
      pos -= 1;
    }
    g_current_position_steps = pos;
  }

  if (g_motion_mode == MOTION_STEP_FINITE && g_motion_steps_remaining > 0) {
    g_motion_steps_remaining--;
    if (g_motion_steps_remaining == 0) {
      g_motion_mode = MOTION_NONE;
    }
  }
}

void handle_rotate_cmd(direction_t direction, unsigned int rpm) {
  if (rpm > 100) {
    rpm = 100;
  }
  if (rpm == 0) {
    return;
  }

  // steps per minute, then ms per step
  unsigned long steps_per_minute = (unsigned long)rpm * (unsigned long)STEPS_PER_ROTATION;
  if (steps_per_minute == 0) {
    return;
  }

  unsigned long ms_per_step = 60000UL / steps_per_minute; // 60 s * 1000 / steps_per_minute
  if (ms_per_step == 0) {
    ms_per_step = 1; // cap to fastest we can schedule
  }
  if (ms_per_step > 65535UL) {
    ms_per_step = 65535UL;
  }

  noInterrupts();
  g_motion_direction       = direction;
  g_motion_mode            = MOTION_ROTATE_CONTINUOUS;
  g_motion_steps_remaining = 0;           // unused for continuous
  g_step_interval_ms       = (uint16_t)ms_per_step;
  g_step_elapsed_ms        = 0;
  interrupts();
}

void handle_step_cmd(direction_t direction, unsigned int steps, unsigned int duration_ms) {
  if ((steps == 0) || (duration_ms == 0)) {
    return;
  }

  unsigned long ms_per_step = (unsigned long)duration_ms / (unsigned long)steps;
  if (ms_per_step == 0) {
    ms_per_step = 1; // at least 1 ms between steps
  }
  if (ms_per_step > 65535UL) {
    ms_per_step = 65535UL;
  }

  noInterrupts();
  g_motion_direction       = direction;
  g_motion_mode            = MOTION_STEP_FINITE;
  g_motion_steps_remaining = (uint32_t)steps;
  g_step_interval_ms       = (uint16_t)ms_per_step;
  g_step_elapsed_ms        = 0;
  interrupts();
}

void handle_position_cmd(direction_t direction, unsigned int position_deg, unsigned int duration_ms) {
  // Map degrees (0..359 etc.) to target step in [0, STEPS_PER_ROTATION-1]
  unsigned int deg = position_deg % 360u;
  unsigned int target_step = (unsigned long)deg * (unsigned long)STEPS_PER_ROTATION / 360ul;
  if (target_step >= STEPS_PER_ROTATION) {
    target_step = STEPS_PER_ROTATION - 1;
  }

  // Default direction if not specified
  direction_t dir = direction;
  if (dir == DIRECTION_INVALID) {
    dir = DIRECTION_CW;
  }

  // Snapshot current position atomically
  uint16_t current_step;
  noInterrupts();
  current_step = g_current_position_steps;
  interrupts();

  // Compute how many steps to move in the requested direction to reach target
  unsigned int steps_to_move = 0;
  if (dir == DIRECTION_CW) {
    if (target_step >= current_step) {
      steps_to_move = target_step - current_step;
    } else {
      steps_to_move = (STEPS_PER_ROTATION - current_step) + target_step;
    }
  } else { // DIRECTION_CCW
    if (current_step >= target_step) {
      steps_to_move = current_step - target_step;
    } else {
      steps_to_move = current_step + (STEPS_PER_ROTATION - target_step);
    }
  }

  if (steps_to_move == 0 || duration_ms == 0) {
    return; // already at position or no duration specified
  }

  handle_step_cmd(dir, steps_to_move, duration_ms);
}

void loop() {
  while (Serial.available() > 0) {
    cmd_current_byte = (char) Serial.read();

    // checks for end of command string
    if ((cmd_current_byte == '\n') || (cmd_current_byte == '\r')) {
      is_serial_overflow = false;
      if (cmd_len) {
        cmd_buf[cmd_len] = '\0';
        String cmd_str = String(cmd_buf);
        parse_cmd(cmd_str, &serial_cmd);

        switch (serial_cmd.action) {
          case ACTION_NAME:
            Serial.println(name);
            break;

          case ACTION_ROTATE:
            handle_rotate_cmd(serial_cmd.direction, serial_cmd.arg1);
            break;

          case ACTION_STEP:
            handle_step_cmd(serial_cmd.direction, serial_cmd.arg1, serial_cmd.arg2);
            break;

          case ACTION_POSITION:
            handle_position_cmd(serial_cmd.direction, serial_cmd.arg1, serial_cmd.arg2);
            break;

          case ACTION_STOP:
            noInterrupts();
            g_motion_mode            = MOTION_NONE;
            g_motion_steps_remaining = 0;
            g_step_interval_ms       = 0;
            g_step_elapsed_ms        = 0;
            interrupts();
            break;

          default:
            Serial.print("ERR: Unrecognized action: ");
            Serial.println(cmd_str);
        }
        cmd_len = 0;
      }
    }
    else {
      if (!is_serial_overflow) {
        if (cmd_len < sizeof(cmd_buf)-1) {
          cmd_buf[cmd_len++] = cmd_current_byte;
        }
        else {
          cmd_len = 0;
          is_serial_overflow = true;
          Serial.println("ERR: overflow");
        }
      }
      else {
        // fall here to bypass adding bytes to the buffer
        // until we set next EOL byte
        continue;
      }
    }
  }
}
// Self-contained, non-blocking stepper controller for SparkFun ProDriver TC78H670FTG
// Target: Arduino Nano Every (ATmega4809)
// Serial protocol (115200 baud):
//   ACTION DIRECTION ARG1 [ARG2]
//   ACTION: ROT | STP | POS  (plus HALT, STAT)
//   DIRECTION: CW | CCW
//   Examples:
//     ROT CW 50
//     STP CCW 200 2000
//     POS CW 90 1500
//
// Implementation:
// - Uses TCB0 interrupt at 10 kHz (100 µs) to schedule step pulses.
// - Directly toggles TC78H670FTG pins (CLK = MODE2, DIR = MODE3) in CLOCK-IN mode.
// - No external library; pin behavior mirrors SparkFun driver internals.
// - Direction HIGH is achieved by setting the pin to INPUT so the board’s pull-up drives HIGH.
//   Direction LOW uses OUTPUT-LOW. Same trick for CLK rising edge.
//
// Wiring (SparkFun defaults):
//   D8  -> STBY  (active HIGH to run; LOW = standby)
//   D7  -> EN    (active HIGH enable)
//   D6  -> MODE0
//   D5  -> MODE1 (also SET_EN in variable mode; we keep fixed mode here)
//   D4  -> MODE2 (CLK)
//   D3  -> MODE3 (CW/CCW)
//   D2  -> ERR   (active LOW)
// Provide motor VM power per board docs. Set hardware slide switch to USER.

#include <Arduino.h>
#include <avr/io.h>
#include <avr/interrupt.h>

#define CMD_BUFFER_LENGTH 64
#define NAME_MAX_LENGTH 8
#define SERIAL_BAUD 115200
#define COMMAND_READY_SEQUENCE "READY"

static const char name[NAME_MAX_LENGTH] = "alpha";
static char cmd_buffer[CMD_BUFFER_LENGTH] = "";
static uint8_t cmd_buffer_length;

static inline bool is_newline(char c)
{
  return ((c == '\n') || (c == '\r'));
}

static void serial_start()
{
  Serial.begin(SERIAL_BAUD);
  while (!Serial)
  {
    ;
  }
  Serial.println(COMMAND_READY_SEQUENCE);
}

// Forward declaration of motor command handler
static void handle_command(const String &action, const String &direction, const String &arg1, const String &arg2);

static void serial_process_cmd()
{
  // Ensure NUL-terminated
  cmd_buffer[CMD_BUFFER_LENGTH - 1] = '\0';

  if (strcasecmp(cmd_buffer, "NAME") == 0)
  {
    Serial.println(name);
    return;
  }

  // Treat any other line as a motor command: ACTION DIRECTION ARG1 [ARG2]
  String line(cmd_buffer);
  line.trim();
  if (line.length() == 0)
    return;

  // Tokenize
  String action, direction, a1, a2;
  int i1 = line.indexOf(' ');
  if (i1 < 0)
  {
    action = line;
  }
  else
  {
    action = line.substring(0, i1);
    int i2 = line.indexOf(' ', i1 + 1);
    if (i2 < 0)
    {
      direction = line.substring(i1 + 1);
    }
    else
    {
      direction = line.substring(i1 + 1, i2);
      int i3 = line.indexOf(' ', i2 + 1);
      if (i3 < 0)
      {
        a1 = line.substring(i2 + 1);
      }
      else
      {
        a1 = line.substring(i2 + 1, i3);
        a2 = line.substring(i3 + 1);
      }
    }
  }
  action.trim();
  direction.trim();
  a1.trim();
  a2.trim();

  if (action.length() == 0)
    return;
  handle_command(action, direction, a1, a2);
}

static void serial_read_char()
{
  while (Serial.available() > 0)
  {
    char c = (char)Serial.read();

    if (is_newline(c))
    {
      if (cmd_buffer_length > 0)
      {
        cmd_buffer[cmd_buffer_length] = '\0';
        while ((cmd_buffer_length > 0) && (cmd_buffer[cmd_buffer_length - 1] == ' ' || cmd_buffer[cmd_buffer_length - 1] == '\t'))
        {
          cmd_buffer[--cmd_buffer_length] = '\0';
        }
        serial_process_cmd();
      }
      cmd_buffer_length = 0;
    }
    else
    {
      if (cmd_buffer_length < (sizeof(cmd_buffer) - 1))
      {
        cmd_buffer[cmd_buffer_length++] = c;
      }
      else
      {
        cmd_buffer_length = 0;
        Serial.println("ERR: Overflow");
      }
    }
  }
}

// ===== Pin map (SparkFun ProDriver default Arduino pins) =====
static const uint8_t PIN_STBY = 8;
static const uint8_t PIN_EN = 7;
static const uint8_t PIN_MODE0 = 6; // UP/DW in variable mode
static const uint8_t PIN_MODE1 = 5; // SET_EN in variable mode
static const uint8_t PIN_MODE2 = 4; // CLK
static const uint8_t PIN_MODE3 = 3; // CW/CCW (DIR)
static const uint8_t PIN_ERR = 2;   // ERR (active LOW)

// ===== Step resolution boot configuration (datasheet page 8) =====
// These values are encoded as a 4-bit pattern which the SparkFun lib maps to MODE[3:0]
// by using INPUT (HIGH via pullup) for bit=1 and OUTPUT-LOW for bit=0.
#define PRODRIVER_STEP_RESOLUTION_FIXED_FULL 8 // 1:1 full-step (simple & deterministic)

static const uint8_t STEP_MODE_BOOT = PRODRIVER_STEP_RESOLUTION_FIXED_FULL;

// ===== Motion constants =====
static const uint16_t BASE_FULL_STEPS_PER_REV = 200; // set for your motor
static const uint16_t MICROSTEP_FACTOR = 1;          // matches FIXED_FULL
static const uint16_t STEPS_PER_REV = BASE_FULL_STEPS_PER_REV * MICROSTEP_FACTOR;

// ===== Scheduler state =====
enum MotionMode : uint8_t
{
  MODE_IDLE = 0,
  MODE_ROTATE,
  MODE_STEPS,
  MODE_POSITION
};

volatile uint32_t tick_100us = 0; // increments every 100µs
volatile bool tick_fired = false;

static MotionMode mode = MODE_IDLE;
static uint8_t dirParam = 0; // 0=CW (HIGH on DIR), 1=CCW (LOW on DIR)
static uint32_t nextStepAtTick = 0;
static uint32_t stepIntervalTicks = 0; // 100 µs ticks per step
static int32_t stepsRemaining = 0;     // used by STP/POS
static int32_t currentStepIndex = 0;   // [0..STEPS_PER_REV-1]

// ===== Utilities =====
static inline bool errorOK() { return digitalRead(PIN_ERR) == HIGH; } // HIGH = OK

static inline void enterStandby() { digitalWrite(PIN_STBY, LOW); }
static inline void exitStandby() { digitalWrite(PIN_STBY, HIGH); }
static inline void enableDrv() { digitalWrite(PIN_EN, HIGH); }
static inline void disableDrv() { digitalWrite(PIN_EN, LOW); }

// Configure MODE pins for the chosen boot step mode (CLOCK-IN)
static void controlModeSelect(uint8_t modeBits)
{
  // For each bit 0..3: 1 -> INPUT (board pull-up drives HIGH), 0 -> OUTPUT LOW
  auto setModePin = [](uint8_t pin, bool highViaPullup)
  {
    if (highViaPullup)
    {
      pinMode(pin, INPUT);
    } // float HIGH via external pullup to ~3.3V
    else
    {
      pinMode(pin, OUTPUT);
      digitalWrite(pin, LOW);
    }
  };
  setModePin(PIN_MODE0, bitRead(modeBits, 0));
  setModePin(PIN_MODE1, bitRead(modeBits, 1));
  setModePin(PIN_MODE2, bitRead(modeBits, 2));
  setModePin(PIN_MODE3, bitRead(modeBits, 3));
  delayMicroseconds(1); // TmodeSU >= 1 µs
  exitStandby();
  delayMicroseconds(100); // TmodeHO >= 100 µs
}

// Set direction pin (MODE3). HIGH is via pull-up.
static inline void setDirection(uint8_t dir /*0=CW,1=CCW*/)
{
  dirParam = dir;
  if (dir == 0)
  { // CW -> HIGH via pullup
    pinMode(PIN_MODE3, INPUT);
  }
  else
  { // CCW -> LOW
    pinMode(PIN_MODE3, OUTPUT);
    digitalWrite(PIN_MODE3, LOW);
  }
}

// Emit one CLK rising edge on MODE2 using pull-up trick
static inline void pulseClockEdge()
{
  pinMode(PIN_MODE2, OUTPUT);
  digitalWrite(PIN_MODE2, LOW);
  delayMicroseconds(1);      // balance low width; error check ~2 µs in SparkFun impl
  pinMode(PIN_MODE2, INPUT); // rising edge occurs as pin floats HIGH
}

// ===== Timer: TCB0 @ 10 kHz =====
static inline void timer_init_10kHz()
{
  cli();
  TCB0.CTRLA = 0;                      // disable during config
  TCB0.CTRLB = TCB_CNTMODE_INT_gc;     // periodic interrupt mode
  TCB0.CCMP = (F_CPU / 10000UL) - 1UL; // 10 kHz period
  TCB0.INTFLAGS = TCB_CAPT_bm;         // clear
  TCB0.INTCTRL = TCB_CAPT_bm;          // enable
  TCB0.CTRLA = TCB_ENABLE_bm | TCB_CLKSEL_CLKDIV1_gc;
  sei();
}

ISR(TCB0_INT_vect)
{
  TCB0.INTFLAGS = TCB_CAPT_bm;
  tick_100us++;
  tick_fired = true;
}

// ===== Conversions =====
static inline uint32_t ms_to_ticks(uint32_t ms) { return ms * 10UL; }
static inline uint32_t us_to_ticks(uint32_t us) { return (us + 50UL) / 100UL; }
static inline uint32_t rpm_to_interval_ticks(float rpm)
{
  float sps = (rpm * (float)STEPS_PER_REV) / 60.0f;
  if (sps < 1.0f)
    sps = 1.0f;
  uint32_t period_us = (uint32_t)(1000000.0f / sps);
  return us_to_ticks(period_us);
}

static inline void stop_motion(const char *reason)
{
  mode = MODE_IDLE;
  stepsRemaining = 0;
  stepIntervalTicks = 0;
  Serial.print(F("STOP "));
  Serial.println(reason);
}

static inline void schedule_next_step_from_now()
{
  nextStepAtTick = tick_100us + stepIntervalTicks;
}

static inline void step_once_and_bookkeep()
{
  // One microstep: pulse clock and update position
  pulseClockEdge();
  if (dirParam == 0)
  { // CW
    currentStepIndex++;
    if (currentStepIndex >= STEPS_PER_REV)
      currentStepIndex -= STEPS_PER_REV;
  }
  else
  {
    currentStepIndex--;
    if (currentStepIndex < 0)
      currentStepIndex += STEPS_PER_REV;
  }
}

static inline int32_t degrees_to_index(int32_t degrees)
{
  if (degrees < 0)
    degrees = ((degrees % 360) + 360) % 360;
  degrees %= 360;
  int32_t idx = (int32_t)((((int64_t)degrees) * STEPS_PER_REV + 180) / 360);
  if (idx >= (int32_t)STEPS_PER_REV)
    idx = 0;
  return idx;
}

static inline int32_t steps_to_target_dir(int32_t targetIndex, bool dirCCW)
{
  if (!dirCCW)
  { // CW
    int32_t delta = targetIndex - currentStepIndex;
    if (delta < 0)
      delta += STEPS_PER_REV;
    return delta;
  }
  else
  {
    int32_t delta = currentStepIndex - targetIndex;
    if (delta < 0)
      delta += STEPS_PER_REV;
    return delta;
  }
}

// ===== Serial command parsing =====

static void handle_command(const String &action, const String &direction, const String &arg1, const String &arg2)
{
  // Direction
  if (ieq(direction, "CW"))
    setDirection(0);
  else if (ieq(direction, "CCW"))
    setDirection(1);
  else
  {
    Serial.println(F("ERR bad direction (use CW or CCW)"));
    return;
  }

  if (ieq(action, "ROT"))
  {
    if (arg1.length() == 0)
    {
      Serial.println(F("ERR ROT needs RPM"));
      return;
    }
    float rpm = arg1.toFloat();
    if (rpm <= 0.0f)
    {
      Serial.println(F("ERR RPM must be > 0"));
      return;
    }
    stepIntervalTicks = rpm_to_interval_ticks(rpm);
    mode = MODE_ROTATE;
    schedule_next_step_from_now();
    Serial.print(F("OK ROT dir="));
    Serial.print(direction);
    Serial.print(F(" rpm="));
    Serial.println(rpm, 3);
  }
  else if (ieq(action, "STP"))
  {
    if (arg1.length() == 0 || arg2.length() == 0)
    {
      Serial.println(F("ERR STP needs steps and ms"));
      return;
    }
    long steps = arg1.toInt();
    long ms = arg2.toInt();
    if (steps <= 0 || ms <= 0)
    {
      Serial.println(F("ERR steps and ms must be > 0"));
      return;
    }
    stepsRemaining = steps;
    stepIntervalTicks = ms_to_ticks(ms) / (uint32_t)steps;
    if (stepIntervalTicks == 0)
      stepIntervalTicks = 1;
    mode = MODE_STEPS;
    schedule_next_step_from_now();
    Serial.print(F("OK STP dir="));
    Serial.print(direction);
    Serial.print(F(" steps="));
    Serial.print(steps);
    Serial.print(F(" ms="));
    Serial.println(ms);
  }
  else if (ieq(action, "POS"))
  {
    if (arg1.length() == 0 || arg2.length() == 0)
    {
      Serial.println(F("ERR POS needs deg and ms"));
      return;
    }
    long deg = arg1.toInt();
    long ms = arg2.toInt();
    if (ms <= 0)
    {
      Serial.println(F("ERR ms must be > 0"));
      return;
    }
    int32_t targetIdx = degrees_to_index((int32_t)deg);
    int32_t stepsNeeded = steps_to_target_dir(targetIdx, dirParam == 1);
    if (stepsNeeded == 0)
    {
      stop_motion("already-at-position");
      return;
    }
    stepsRemaining = stepsNeeded;
    stepIntervalTicks = ms_to_ticks(ms) / (uint32_t)stepsNeeded;
    if (stepIntervalTicks == 0)
      stepIntervalTicks = 1;
    mode = MODE_POSITION;
    schedule_next_step_from_now();
    Serial.print(F("OK POS dir="));
    Serial.print(direction);
    Serial.print(F(" deg="));
    Serial.print(deg);
    Serial.print(F(" ms="));
    Serial.println(ms);
  }
  else if (ieq(action, "HALT"))
  {
    stop_motion("HALT");
  }
  else if (ieq(action, "STAT"))
  {
    Serial.print(F("MODE="));
    switch (mode)
    {
    case MODE_IDLE:
      Serial.print(F("IDLE"));
      break;
    case MODE_ROTATE:
      Serial.print(F("ROTATE"));
      break;
    case MODE_STEPS:
      Serial.print(F("STEPS"));
      break;
    case MODE_POSITION:
      Serial.print(F("POSITION"));
      break;
    }
    Serial.print(F(" dir="));
    Serial.print(dirParam == 0 ? F("CW") : F("CCW"));
    Serial.print(F(" nextTick="));
    Serial.print(nextStepAtTick);
    Serial.print(F(" intervalTicks="));
    Serial.print(stepIntervalTicks);
    Serial.print(F(" remain="));
    Serial.print(stepsRemaining);
    Serial.print(F(" idx="));
    Serial.print(currentStepIndex);
    Serial.print(F("/"));
    Serial.println(STEPS_PER_REV);
  }
  else
  {
    Serial.println(F("ERR unknown ACTION (use ROT/STP/POS or HALT/STAT)"));
  }
}

static inline bool ieq(const String &a, const char *b) { return a.equalsIgnoreCase(String(b)); }

void setup()
{
  memset(cmd_buffer, 0, CMD_BUFFER_LENGTH);
  cmd_buffer_length = 0;
  serial_start();

  // Base pin states
  pinMode(PIN_STBY, OUTPUT);
  enterStandby();
  pinMode(PIN_EN, OUTPUT);
  disableDrv();
  pinMode(PIN_ERR, INPUT);

  // Boot into CLOCK-IN with chosen step mode
  controlModeSelect(STEP_MODE_BOOT); // sets MODE pins and exits standby

  // Enable outputs
  enableDrv();

  // Initialize timer ISR
  timer_init_10kHz();

  // Default direction
  setDirection(0); // CW

  Serial.print(F("STEPS_PER_REV="));
  Serial.println(STEPS_PER_REV);
  Serial.println(F("Ready: ROT/STP/POS/HALT/STAT"));
}

void loop()
{
  serial_read_char();

  if (tick_fired)
  {
    noInterrupts();
    tick_fired = false;
    uint32_t now = tick_100us;
    interrupts();

    if (!errorOK())
    {
      stop_motion("ERR");
      disableDrv();
    }

    if (mode != MODE_IDLE && stepIntervalTicks > 0)
    {
      while ((int32_t)(now - nextStepAtTick) >= 0)
      {
        step_once_and_bookkeep();
        if (mode == MODE_STEPS || mode == MODE_POSITION)
        {
          stepsRemaining--;
          if (stepsRemaining <= 0)
          {
            stop_motion("done");
            break;
          }
        }
        nextStepAtTick += stepIntervalTicks;
      }
    }
  }
}
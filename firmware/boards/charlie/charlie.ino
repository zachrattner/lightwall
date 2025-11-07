// Nano Every (ATmega4809)
// 5-channel LED driver EN/PWM dimming for a white LED (active-low modules) using a fixed-rate 20 kHz software PWM carrier
// - ISR @ 20 kHz (TCB0 periodic)
// - 5-bit effective PWM (625 Hz visible PWM; ISR still 20 kHz)
// - Breathing: 10 ms per brightness step (0..255..0), reverses at endpoints
// - Direct port writes inside ISR (no digitalWrite in ISR)

#include <avr/io.h>
#include <avr/interrupt.h>
#include <Arduino.h>
#include <strings.h>

// board name
static const char name[8] = "CHARLIE"

// ---------------- Config ----------------
static const bool    ACTIVE_HIGH  = false;            // Set false for active-low LED driver EN/PWM (HIGH disables, LOW enables)
static const uint8_t LED_PINS[] = {3, 5, 6, 9, 11};   // Arduino pins wired to LED driver EN/PWM inputs
static const uint8_t NUM_LEDS     = sizeof(LED_PINS)/sizeof(LED_PINS[0]);

// Serial communication speed
static const uint32_t SERIAL_BAUD_RATE = 115200;

// 20 kHz carrier: 16 MHz / 20,000 = 800 counts
static const uint16_t TCB0_CMP = 800 - 1;

// Effective PWM resolution/frequency
// Keep 20 kHz ISR but use 5-bit software PWM so the visible PWM is 20 kHz / 32 = 625 Hz
static const uint8_t PWM_BITS = 5;                    // 5-bit (0..31)
static const uint8_t PWM_MAX  = (1u << PWM_BITS);     // 32
static const uint8_t PWM_MASK = PWM_MAX - 1;          // 0x1F
static const uint8_t MIN_DUTY5 = 1;                   // clamp tiny non-zero 8-bit duties to 1/32 so EN actually enables

// ---------------- State ----------------
volatile uint8_t duty[8];                 // duty per channel 0..255 (use first NUM_LEDS)
volatile uint8_t pwmPhase = 0;            // 0..31 (5-bit phase)

// Per-channel fade state (used by ISR every 1 ms)
volatile uint8_t  fade_start[8];        // starting brightness (0..255)
volatile uint8_t  fade_target[8];       // final brightness  (0..255)
volatile uint16_t fade_duration_ms[8];  // total ms (0 = immediate)
volatile uint16_t fade_elapsed_ms[8];   // ms elapsed so far
volatile int16_t  fade_step_q8[8];      // per-ms step in Q8.8 (signed)

// blink state for LEDs
volatile uint8_t  blink_active[NUM_LEDS];
volatile uint8_t  blink_original[NUM_LEDS];
volatile uint16_t blink_timer_ms[NUM_LEDS];

// Fast GPIO caches
volatile uint8_t* outReg[8];
uint8_t           bitMask[8];

// ISR-time 1 ms derivation: 20 kHz -> 20 ticks per ms
static const uint8_t TICKS_PER_MS = 20;

// non-blocking serial parser command buffer and variables
static bool	overflow = false;
static char	currentByte;
static char	cmdBuf[64];
static unit8_t	cmdLen = 0;

static void tcb0_init_20khz() {
  // Periodic interrupt mode
  TCB0.CTRLB = TCB_CNTMODE_INT_gc;
  TCB0.CCMP  = TCB0_CMP;
  TCB0.INTFLAGS = TCB_CAPT_bm;
  TCB0.INTCTRL  = TCB_CAPT_bm;
  // CLK/1 (16 MHz)
  TCB0.CTRLA = TCB_CLKSEL_CLKDIV1_gc | TCB_ENABLE_bm;
}

ISR(TCB0_INT_vect) {
  TCB0.INTFLAGS = TCB_CAPT_bm;

  // ----- 5-bit software PWM at 20 kHz carrier (625 Hz effective) -----
  uint8_t phase = pwmPhase;               // 0..31
  for (uint8_t i = 0; i < NUM_LEDS; ++i) {
    // Map 8-bit duty (0..255) to 5-bit (0..31); clamp very small non-zero duties so the LED driver reliably enables
    uint8_t d5 = duty[i] >> (8 - PWM_BITS); // fast divide
    if (d5 > 0 && d5 < MIN_DUTY5) d5 = MIN_DUTY5;

    bool on = (phase < d5);
    if (!ACTIVE_HIGH) on = !on;
    if (on)  *outReg[i] |=  bitMask[i];
    else     *outReg[i] &= ~bitMask[i];
  }
  // Wrap 0..31
  pwmPhase = (phase + 1) & PWM_MASK;

  // ----- Derive 1 ms and update brightness every 10 ms -----
  static uint8_t tick20 = 0;
  if (++tick20 >= TICKS_PER_MS) {
    tick20 = 0;

    for (uint8_t i = 0; i < NUM_LEDS; ++i) {
      uint16_t dur = fade_duration_ms[i];
      if (dur == 0) continue;   // no active fade

      uint16_t t = fade_elapsed_ms[i] + 1;
      fade_elapsed_ms[i] = t;

      int32_t vq8 = ((int32_t)fade_start[i] << 8) +
                    (int32_t)fade_step_q8[i] * (int32_t)t;
      int32_t v = vq8 >> 8;
      if (v < 0)   v = 0;
      if (v > 255) v = 255;
      duty[i] = (uint8_t)v;

      if (t >= dur) {
        duty[i] = fade_target[i];
        fade_duration_ms[i] = 0;
      }
    }

    for (uint8_t i = 0; i < NUM_LEDS; ++i) {
      if (blink_active[i]) {
        if (--blink_timer_ms[i] == 0) {
          duty[i] = blink_original[i];
        }
      }
    }
  }
}

static inline void schedule_fade(uint8_t idx, uint8_t target, uint16_t duration_ms) {
  if (idx >= NUM_LEDS) return;

  noInterrupts();

  uint8_t start = duty[idx];
  fade_start[idx]       = start;
  fade_target[idx]      = target;
  fade_elapsed_ms[idx]  = 0;
  fade_duration_ms[idx] = duration_ms;

  if (duration_ms == 0) {
    // Instant set
    duty[idx] = target;
    fade_step_q8[idx] = 0;
  } else {
    // Signed fixed-point step: ((target - start) << 8) / duration_ms
    int16_t delta = (int16_t)target - (int16_t)start;    // -255..+255
    fade_step_q8[idx] = (int16_t)(( (int32_t)delta << 8) / (int32_t)duration_ms);
  }

  interrupts();
}

static inline void blink_LED(uint8_t idx) {
  if (idx >= NUM_LEDS) return;

  noInterrupts();

  if (duty[idx] > 0) {
    blink_original[idx] = duty[idx]
    duty[idx] = 0;
  } else {
    blink_original[idx] = 0;
    duty[idx] = 255;
  }
  blink_timer_ms[idx] = 1000;	// duration in ms; currently fixed
  blink_active = 1;

  interrupts();
}

static void executeCommand(char* command)
{
  // trim leading whitespace (may or may not be necessary)
  while (*command == ' ' || *command == '\t') ++command;
  if (!*command) return;

  // tokenize
  char* tokens = strtok(command, " \t\r\n");
  if (!tokens) return;

  // execute name if NAME
  if (!strcasecmp(tokens, "NAME")) { Serial.println(name); return; }

  // execute set if SET
  if (!strcasecmp(tokens, "SET")) {
    char* i = strtok(nullptr, " \t\r\n");
    char* b = strtok(nullptr, " \t\r\n");
    char* d = strtok(nullptr, " \t\r\n");

    if (!i || !b || !d)
    { Serial.println("ERR: bad args"); return; }

    char* end = nullptr;

    // gets SET args validated; clamps all args except LED index
    long idx = strtol(i, &end, 10);
    if (end == i || *end != '\0') { Serial.println("ERR: bad args"); return; }
    if (idx < 0 || idx >= NUM_LEDS) { Serial.println("ERR: bad args"); return; }

    long bv  = strtol(b, &end, 10);
    if (end == b || *end != '\0') { Serial.println("ERR: bad value"); return; }
    if (bv < 0) { bv = 0; }
    if (bv > 255) { bv = 255; }

    long dur = strtol(d, &end, 10);
    if (end == d || *end != '\0') { Serial.println("ERR: bad args"); return; }
    if (dur < 0) { dur = 0; }
    if (dur > 60000) { dur = 60000; }

    schedule_fade((uint8_t)idx, (uint8_t)bv, (uint16_t)dur);

    Serial.print("OK ");  Serial.print((int)idx);
    Serial.print(' ');    Serial.print((int)bv);
    Serial.print(' ');    Serial.println((unsigned long)dur);

    return;
  }

  if (!strcasecmp(tokens, "BLINK")) {
    char* i = strtok(nullptr, " \t\r\n");

    if (!i)
    { Serial.println("ERR: bad args"); return; }

    char* end = nullptr;

    // gets SET args validated; clamps all args except LED index
    long idx = strtol(i, &end, 10);
    if (end == i || *end != '\0') { Serial.println("ERR: bad args"); return; }
    if (idx < 0 || idx >= NUM_LEDS) { Serial.println("ERR: bad args"); return; }

    blink_LED((uint8_t)idx);

    Serial.print("OK ");  Serial.println((int)idx);

    return;
  }
  Serial.println("ERR: unknown command");
}

void setup() {
  // begin serial
  Serial.begin(SERIAL_BAUD_RATE)
  
  // short wait for host connect
  uint32_t t0 = millis()
  while (!Serial && (millis() - t0 < 2000)) { /* wait for host up to 2s */ }
  
  // return ready signal to host
  Serial.println("READY");

  // Prepare pins and cache fast GPIO pointers/masks
  for (uint8_t i = 0; i < NUM_LEDS; ++i) {
    uint8_t pin = LED_PINS[i];
    pinMode(pin, OUTPUT);

    // Start safely OFF: for active-low EN, drive HIGH to keep LED off
    if (ACTIVE_HIGH) digitalWrite(pin, LOW);
    else             digitalWrite(pin, HIGH);

    duty[i] = 0;

    // Resolve port and OUT register pointer for this Arduino pin
    uint8_t port = digitalPinToPort(pin);
    outReg[i]    = portOutputRegister(port);
    bitMask[i]   = digitalPinToBitMask(pin);
  }

  tcb0_init_20khz();
  sei();
}

void loop() {
  // CPU free for other work; avoid Serial prints inside ISR.
  while (Serial.available() > 0) {
    currentByte = (char)Serial.read();

    // checks for end of command string
    if (currentByte == '\n' || currentByte == '\r') {
      overflow = false;
      if (cmdLen) {
        cmdBuf[cmdLen] = '\0';
        executeCommand(cmdBuf);
        cmdLen = 0;
      }
    }
    else {
      if (!overflow) {
        if (cmdLen < sizeof(cmdBuf)-1) {
          cmdBuf[cmdLen++] = currentByte;
        } else {
          cmdLen = 0;
          overflow = true;
          Serial.println("ERR: overflow");
        }
      } else {
        // fall here to bypass adding bytes to the buffer
        // until we set next EOL byte
        continue;
      }
    }
  }
}

// Nano Every (ATmega4809)
// 5-channel LED driver EN/PWM dimming for a white LED (active-low modules) using a fixed-rate 20 kHz software PWM carrier
// - ISR @ 20 kHz (TCB0 periodic)
// - 5-bit effective PWM (625 Hz visible PWM; ISR still 20 kHz)
// - Breathing: 10 ms per brightness step (0..255..0), reverses at endpoints
// - Direct port writes inside ISR (no digitalWrite in ISR)

#include <avr/io.h>
#include <avr/interrupt.h>
#include <Arduino.h>

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

// Breathing timing
static const uint8_t  MS_PER_STEP = 10;   // hold per step
static const int8_t   STEP_DELTA  = +1;   // increment per step

// ---------------- State ----------------
volatile uint8_t duty[8];                 // duty per channel 0..255 (use first NUM_LEDS)
volatile uint8_t pwmPhase = 0;            // 0..31 (5-bit phase)
volatile uint16_t ms_accum = 0;           // derived ms counter

// Fast GPIO caches
volatile uint8_t* outReg[8];
uint8_t           bitMask[8];

// ISR-time 1 ms derivation: 20 kHz -> 20 ticks per ms
static const uint8_t TICKS_PER_MS = 20;

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
    ms_accum++;

    if (ms_accum % MS_PER_STEP == 0) {
      static uint8_t level = 0;
      static int8_t  dir   = +1;

      level = level + dir;
      if (level == 0 || level == 255) dir = -dir;

      // apply same brightness to all LED channels (customize per-channel if desired)
      for (uint8_t i = 0; i < NUM_LEDS; ++i) duty[i] = level;
    }
  }
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
}

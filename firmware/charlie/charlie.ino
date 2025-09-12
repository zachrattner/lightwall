// Nano Every (ATmega4809)
// Multi-channel TTL laser dimming via TCB0 ISR (software PWM)
// - PWM carrier: 8 kHz (ISR @ 8 kHz)
// - Resolution: 8-bit (0..255) → full PWM frame ~32 ms
// - Brightness update (breathing): every 10 ms
//
// Wiring per channel: laser yellow -> one of pins in LASER_PINS[], black -> GND, red -> +5V.
// If your laser is active-low, set ACTIVE_HIGH = false.

#include <avr/io.h>
#include <avr/interrupt.h>

// ---------------- Config ----------------
static const bool    ACTIVE_HIGH   = true;   // set false if your TTL is active-low
static const uint8_t LASER_PINS[]  = {3, 5, 6, 9, 11};   // up to 5 channels here
static const uint8_t NUM_LASERS    = sizeof(LASER_PINS) / sizeof(LASER_PINS[0]);

// PWM carrier settings
// We’ll run TCB0 at /1 (16 MHz). For 8 kHz: 16e6 / 8000 = 2000 counts.
static const uint16_t TCB0_CMP     = 2000 - 1; // 8 kHz periodic interrupt

// Breathing update cadence
static const uint16_t BREATH_MS    = 10;   // hold per step
static const int8_t   STEP_DELTA   = +1;   // increment per 10 ms tick

// ---------------- State ----------------
volatile uint8_t duty[8];          // per-channel duty 0..255 (use first NUM_LASERS)
volatile int8_t  dir = +1;         // breathing direction
volatile uint8_t pwmPhase = 0;     // 0..255 phase for software PWM
volatile uint16_t msCounter = 0;   // 1 ms tick counter via ISR accumulation

// We derive ~1 ms from the 8 kHz ISR: 1000us / 125us = 8 ticks
static const uint8_t TICKS_PER_MS = 8;

// ---------------- Timer: TCB0 @ 8 kHz ----------------
// Periodic Interrupt mode
static void tcb0_init_8khz() {
  // Set mode = Periodic Interrupt
  TCB0.CTRLB = TCB_CNTMODE_INT_gc;

  // Set period for 8 kHz
  TCB0.CCMP = TCB0_CMP;

  // Clear pending and enable interrupt
  TCB0.INTFLAGS = TCB_CAPT_bm;
  TCB0.INTCTRL  = TCB_CAPT_bm;

  // Start TCB0 with CLK/1 (16 MHz)
  TCB0.CTRLA = TCB_CLKSEL_CLKDIV1_gc | TCB_ENABLE_bm;
}

ISR(TCB0_INT_vect) {
  // Ack interrupt
  TCB0.INTFLAGS = TCB_CAPT_bm;

  // --- 8-bit software PWM ---
  uint8_t phase = pwmPhase;
  // For each laser pin, output HIGH if phase < duty, else LOW
  for (uint8_t i = 0; i < NUM_LASERS; ++i) {
    bool on = (phase < duty[i]);
    if (!ACTIVE_HIGH) on = !on;
    digitalWrite(LASER_PINS[i], on ? HIGH : LOW);
  }
  pwmPhase = phase + 1;  // wraps 0..255 automatically

  // --- 1 ms and 10 ms scheduling (derived from 8 kHz ISR) ---
  // 8 ISR ticks ≈ 1 ms
  static uint8_t tick8 = 0;
  tick8++;
  if (tick8 >= TICKS_PER_MS) {
    tick8 = 0;
    msCounter++;

    // Every BREATH_MS, update breathing duties
    if (msCounter % BREATH_MS == 0) {
      // advance shared level 0..255..0
      static uint8_t level = 0;
      static int8_t  d     = +1;

      level = level + d;
      if (level == 0 || level == 255) d = -d;

      // write same level to all channels; customize per-channel if you like
      for (uint8_t i = 0; i < NUM_LASERS; ++i) {
        duty[i] = level;
      }
    }
  }
}

void setup() {
  // Prepare pins
  for (uint8_t i = 0; i < NUM_LASERS; ++i) {
    pinMode(LASER_PINS[i], OUTPUT);
    // Start safely off
    if (ACTIVE_HIGH) digitalWrite(LASER_PINS[i], LOW);
    else             digitalWrite(LASER_PINS[i], HIGH);
    duty[i] = 0;
  }

  tcb0_init_8khz();
  sei();
}

void loop() {
  // Main loop stays free for other work.
  // If you want to print current level occasionally, you can sample it here
  // (avoid Serial in the ISR).
}
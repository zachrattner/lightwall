// Nano Every (ATmega4809)
// 5-channel TTL laser dimming with jitter-free 20 kHz software PWM
// - ISR @ 20 kHz (TCB0 periodic)
// - 8-bit PWM (full frame ~12.8 ms)
// - Breathing: 10 ms per brightness step (0..255..0)
// - Uses direct port writes for clean edges (no digitalWrite in ISR)

#include <avr/io.h>
#include <avr/interrupt.h>
#include <Arduino.h>

// ---------------- Config ----------------
static const bool    ACTIVE_HIGH  = true;             // set false if your TTL input is active-low
static const uint8_t LASER_PINS[] = {3, 5, 6, 9, 11}; // change as needed
static const uint8_t NUM_LASERS   = sizeof(LASER_PINS)/sizeof(LASER_PINS[0]);

// Serial communication speed
static const uint32_t SERIAL_BAUD_RATE = 115200;

// 20 kHz carrier: 16 MHz / 20,000 = 800 counts
static const uint16_t TCB0_CMP = 800 - 1;

// Breathing timing
static const uint8_t  MS_PER_STEP = 10;   // hold per step
static const int8_t   STEP_DELTA  = +1;   // increment per step

// ---------------- State ----------------
volatile uint8_t duty[8];                 // duty per channel 0..255 (use first NUM_LASERS)
volatile uint8_t pwmPhase = 0;            // 0..255
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

  // ----- 8-bit software PWM at 20 kHz -----
  uint8_t phase = pwmPhase;
  for (uint8_t i = 0; i < NUM_LASERS; ++i) {
    bool on = (phase < duty[i]);
    if (!ACTIVE_HIGH) on = !on;
    if (on)  *outReg[i] |=  bitMask[i];
    else     *outReg[i] &= ~bitMask[i];
  }
  pwmPhase = phase + 1; // wraps naturally 255->0

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

      // same level to all channels (customize per-channel if desired)
      for (uint8_t i = 0; i < NUM_LASERS; ++i) duty[i] = level;
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
  for (uint8_t i = 0; i < NUM_LASERS; ++i) {
    uint8_t pin = LASER_PINS[i];
    pinMode(pin, OUTPUT);

    // Start safely OFF
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

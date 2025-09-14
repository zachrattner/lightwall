#include <Arduino.h>

#define CMD_BUFFER_LENGTH 64
#define NAME_MAX_LENGTH 8
#define SERIAL_BAUD 115200
#define COMMAND_READY_SEQUENCE "READY"

static const char name[NAME_MAX_LENGTH] = "delta";
static char cmd_buffer[CMD_BUFFER_LENGTH]= "";
static uint8_t cmd_buffer_length; 

static int32_t g_value = 12345;  // lives in RAM

static inline bool is_newline(char c) {
  return ((c == '\n') || (c == '\r'));
}

static void serial_start() {
  Serial.begin(SERIAL_BAUD);
  Serial.println(COMMAND_READY_SEQUENCE);
}

static void serial_process_cmd() {
  if (strcasecmp(cmd_buffer, "NAME") == 0) {
    Serial.println(name);
  }
  else {
    Serial.println("ERR: Unknown cmd");
  }
}

static void serial_read_char() {
  while (Serial.available() > 0) {
    char c = (char) Serial.read();

    if (is_newline(c)) {
      // End of line reached. Process command if we have any chars.
      if (cmd_buffer_length > 0) {
        cmd_buffer[cmd_buffer_length] = '\0';

        // Null out trailing whitespace
        while ( (cmd_buffer_length > 0) && 
               ((cmd_buffer[cmd_buffer_length - 1] == ' ') || 
                (cmd_buffer[cmd_buffer_length - 1] == '\t'))) {
          cmd_buffer[--cmd_buffer_length] = '\0';
        }

        serial_process_cmd();
      }

      // Reset buffer for next line
      cmd_buffer_length = 0;
    }
    else {
      if (cmd_buffer_length < (sizeof(cmd_buffer) - 1)) {
        cmd_buffer[cmd_buffer_length++] = c;
      }
      else {
        // Overflow: reset and report
        cmd_buffer_length = 0;
        Serial.println("ERR: Overflow");
      }
    }
  }
}

void setup() {
  memset(cmd_buffer, 0, CMD_BUFFER_LENGTH);
  cmd_buffer_length = 0;

  serial_start();
}

void loop() {
  serial_read_char(); 

  // Do other useful work here
}
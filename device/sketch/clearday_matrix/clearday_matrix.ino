// Clearday Home: LED matrix sketch for the Arduino UNO Q microcontroller.
//
// The Linux side (device/clearday_home) owns the network, bulb, keypad and
// audio. This sketch only draws the matrix. It registers one Bridge function,
// "matrix", which takes the whole command string, e.g. "matrix:sun",
// "matrix:cloud", "matrix:count:3", "matrix:dash" (and "matrix:mic").
//
// Bridge callbacks run outside loop(), so the handler only copies the command;
// loop() renders it. Boots showing the dash (Offline) until Linux says otherwise.
//
// Library APIs to confirm against the App Lab examples on the board:
//   Arduino_RouterBridge: Bridge.begin(), Bridge.provide(name, fn)
//   Arduino_LED_Matrix:   Arduino_LED_Matrix, begin(), draw(uint8_t[104])

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

#include "matrix_render.h"

Arduino_LED_Matrix matrix;

static const size_t CMD_MAX = 32;
static char pending[CMD_MAX];
static volatile bool hasPending = false;
static uint8_t frame[clearday::FRAME_SIZE];

void onMatrix(String cmd) {
  if (cmd.length() >= CMD_MAX) return;
  cmd.toCharArray(pending, CMD_MAX);
  hasPending = true;
}

void show(const char* cmd) {
  if (clearday::renderCommand(cmd, frame)) {
    matrix.draw(frame);
  }
}

void setup() {
  matrix.begin();
  show("matrix:dash");
  Bridge.begin();
  Bridge.provide("matrix", onMatrix);
}

void loop() {
  if (hasPending) {
    char cmd[CMD_MAX];
    memcpy(cmd, pending, CMD_MAX);
    hasPending = false;
    show(cmd);
  }
  delay(20);
}

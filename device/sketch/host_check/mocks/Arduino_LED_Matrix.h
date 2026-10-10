// Host-only stand-in for the UNO Q LED matrix library: keeps the last frame.
#pragma once
#include "Arduino.h"

class Arduino_LED_Matrix {
 public:
  uint8_t last[104] = {0};
  int draws = 0;
  void begin() {}
  void draw(uint8_t* frame) {
    memcpy(last, frame, sizeof(last));
    draws++;
  }
};

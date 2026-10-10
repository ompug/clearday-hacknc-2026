// Host-only stand-in for Arduino_RouterBridge: records the provided handler.
#pragma once
#include "Arduino.h"

struct MockBridge {
  void (*handler)(String) = nullptr;
  const char* name = nullptr;
  void begin() {}
  bool provide(const char* n, void (*fn)(String)) {
    name = n;
    handler = fn;
    return true;
  }
};
inline MockBridge Bridge;

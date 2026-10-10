// Host-only stand-in for the Arduino core: just enough for clearday_matrix.ino.
#pragma once
#include <stdint.h>
#include <string.h>
#include <string>

class String {
 public:
  String(const char* s = "") : s_(s) {}
  unsigned int length() const { return (unsigned int)s_.size(); }
  void toCharArray(char* buf, unsigned int size) const {
    strncpy(buf, s_.c_str(), size - 1);
    buf[size - 1] = '\0';
  }

 private:
  std::string s_;
};

inline void delay(unsigned long) {}

// Compiles the real sketch against host mocks and checks the bridge protocol.
#include <stdio.h>
#include <stdlib.h>

#include "Arduino.h"
#include "../clearday_matrix/clearday_matrix.ino"

static int failures = 0;
#define CHECK(cond)                                         \
  do {                                                      \
    if (!(cond)) {                                          \
      fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); \
      failures++;                                           \
    }                                                       \
  } while (0)

static int lit() {
  int n = 0;
  for (int i = 0; i < 104; i++) n += matrix.last[i];
  return n;
}

static void send(const char* cmd) {
  Bridge.handler(String(cmd));
  loop();
}

static void print(const char* label) {
  printf("%s\n", label);
  for (int r = 0; r < 8; r++) {
    for (int c = 0; c < 13; c++) putchar(matrix.last[r * 13 + c] ? '#' : '.');
    putchar('\n');
  }
}

static bool iconWellFormed(const char* const icon[clearday::ROWS]) {
  for (int r = 0; r < clearday::ROWS; r++)
    if (strlen(icon[r]) != clearday::COLS) return false;
  return true;
}

int main() {
  CHECK(clearday::FRAME_SIZE == 104);
  CHECK(iconWellFormed(clearday::ICON_SUN) && iconWellFormed(clearday::ICON_CLOUD));
  CHECK(iconWellFormed(clearday::ICON_DASH) && iconWellFormed(clearday::ICON_MIC));

  setup();
  CHECK(Bridge.handler != nullptr && strcmp(Bridge.name, "matrix") == 0);
  CHECK(matrix.draws == 1 && lit() > 0);  // boots on the dash (Offline)
  print("matrix:dash (boot)");

  const char* ok[] = {"matrix:sun", "matrix:cloud", "matrix:mic", "matrix:count:0",
                      "matrix:count:3", "matrix:count:42", "matrix:count:99"};
  for (const char* cmd : ok) {
    int before = matrix.draws;
    send(cmd);
    CHECK(matrix.draws == before + 1);
    CHECK(lit() > 0);
    print(cmd);
  }

  const char* bad[] = {"matrix:count:100", "matrix:count:", "matrix:count:-1", "matrix:rent",
                       "sun", "", "matrix:count:3x", "matrix:this-command-is-way-too-long-for-the-buffer"};
  for (const char* cmd : bad) {
    int before = matrix.draws;
    send(cmd);
    CHECK(matrix.draws == before);
  }

  if (failures) {
    fprintf(stderr, "%d check(s) failed\n", failures);
    return 1;
  }
  printf("sketch host check: OK\n");
  return 0;
}

// Clearday Home LED matrix: pure frame rendering, no Arduino dependencies.
// Compiled on the board by clearday_matrix.ino and on a laptop by host_check/.
//
// The UNO Q matrix is 13 columns x 8 rows. A frame is ROWS*COLS bytes,
// row-major, 1 = LED on, 0 = off.
//
// Commands (docs/04-clearday-home-hardware.md, bridge protocol):
//   matrix:sun  matrix:cloud  matrix:count:<0-99>  matrix:dash  matrix:mic
#pragma once

#include <stdint.h>
#include <string.h>

namespace clearday {

const uint8_t ROWS = 8;
const uint8_t COLS = 13;
const uint16_t FRAME_SIZE = ROWS * COLS;

// Icons as text art: '#' on, anything else off. Original artwork.
static const char* const ICON_SUN[ROWS] = {
  "......#......",
  "..#..###..#..",
  "....#####....",
  "##.#######.##",
  "....#####....",
  "..#..###..#..",
  "......#......",
  ".............",
};

static const char* const ICON_CLOUD[ROWS] = {
  ".............",
  "....###......",
  "...#####.##..",
  ".##########..",
  "############.",
  "############.",
  ".##########..",
  ".............",
};

static const char* const ICON_DASH[ROWS] = {
  ".............",
  ".............",
  ".............",
  "...#######...",
  "...#######...",
  ".............",
  ".............",
  ".............",
};

static const char* const ICON_MIC[ROWS] = {
  ".....###.....",
  ".....###.....",
  "...#.###.#...",
  "...#.###.#...",
  "....#...#....",
  ".....###.....",
  "......#......",
  "....#####....",
};

// 3x5 digits, each row a 3-bit mask (bit 2 = left column).
static const uint8_t DIGITS[10][5] = {
  {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {7, 1, 7, 4, 7}, {7, 1, 7, 1, 7}, {5, 5, 7, 1, 1},
  {7, 4, 7, 1, 7}, {7, 4, 7, 5, 7}, {7, 1, 2, 2, 2}, {7, 5, 7, 5, 7}, {7, 5, 7, 1, 7},
};

inline void clearFrame(uint8_t* frame) { memset(frame, 0, FRAME_SIZE); }

inline void drawIcon(uint8_t* frame, const char* const icon[ROWS]) {
  for (uint8_t r = 0; r < ROWS; r++) {
    for (uint8_t c = 0; c < COLS; c++) {
      frame[r * COLS + c] = icon[r][c] == '#' ? 1 : 0;
    }
  }
}

inline void drawDigit(uint8_t* frame, uint8_t digit, uint8_t left, uint8_t top) {
  for (uint8_t r = 0; r < 5; r++) {
    for (uint8_t c = 0; c < 3; c++) {
      if (DIGITS[digit][r] & (4 >> c)) frame[(top + r) * COLS + left + c] = 1;
    }
  }
}

inline void drawCount(uint8_t* frame, uint8_t n) {
  clearFrame(frame);
  if (n > 99) n = 99;
  if (n < 10) {
    drawDigit(frame, n, 5, 1);
  } else {
    drawDigit(frame, n / 10, 3, 1);
    drawDigit(frame, n % 10, 7, 1);
  }
}

// Parses "0".."99" exactly; returns -1 otherwise.
inline int parseCount(const char* s) {
  size_t len = strlen(s);
  if (len < 1 || len > 2) return -1;
  int n = 0;
  for (size_t i = 0; i < len; i++) {
    if (s[i] < '0' || s[i] > '9') return -1;
    n = n * 10 + (s[i] - '0');
  }
  return n;
}

// Renders a bridge command into `frame`. Returns false (frame untouched)
// for anything that is not a known command.
inline bool renderCommand(const char* cmd, uint8_t* frame) {
  const char* prefix = "matrix:";
  if (strncmp(cmd, prefix, 7) != 0) return false;
  const char* arg = cmd + 7;
  if (strcmp(arg, "sun") == 0) { drawIcon(frame, ICON_SUN); return true; }
  if (strcmp(arg, "cloud") == 0) { drawIcon(frame, ICON_CLOUD); return true; }
  if (strcmp(arg, "dash") == 0) { drawIcon(frame, ICON_DASH); return true; }
  if (strcmp(arg, "mic") == 0) { drawIcon(frame, ICON_MIC); return true; }
  if (strncmp(arg, "count:", 6) == 0) {
    int n = parseCount(arg + 6);
    if (n < 0) return false;
    drawCount(frame, (uint8_t)n);
    return true;
  }
  return false;
}

}  // namespace clearday

#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    ULVA_BUTTON_SCAN_MS = 10,
    ULVA_BUTTON_DEBOUNCE_MS = 30,
    ULVA_BUTTON_MAX_SAMPLE_GAP_MS = 20,
};

typedef enum {
    ULVA_BUTTON_INVALID = -1,
    ULVA_BUTTON_NONE = 0,
    ULVA_BUTTON_UP,
    ULVA_BUTTON_OK,
    ULVA_BUTTON_DOWN,
} ulva_button_t;

typedef struct {
    ulva_button_t previous;
    ulva_button_t current;
} ulva_button_change_t;

typedef struct {
    ulva_button_t stable;
    ulva_button_t candidate;
    uint64_t candidate_since_ms;
    uint64_t last_sample_ms;
    bool has_sample;
} ulva_buttons_t;

// Calibrated millivolts for the button ladder (R12 10k, R13 4.7k, R14 10k).
// INVALID covers the gaps; it is never interpreted as a button press.
ulva_button_t ulva_button_decode_mv(int mv);
const char *ulva_button_name(ulva_button_t button);
void ulva_buttons_init(ulva_buttons_t *buttons);

// Call from one task, normally every 10ms, with a monotonic timestamp.
// Pass sample_valid=false on any ADC/calibration error; mv is then ignored.
// Returns a change only after 30ms of consecutive matching samples. A gap
// greater than 20ms restarts debounce. A persistent INVALID state cancels a
// held button; temporary invalid samples only restart the candidate timer.
// A button held at startup produces a press after the same debounce interval.
bool ulva_buttons_update(ulva_buttons_t *buttons, bool sample_valid, int mv,
                         uint64_t now_ms, ulva_button_change_t *change);

#ifdef __cplusplus
}
#endif

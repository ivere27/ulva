#include "ulva_buttons.h"

ulva_button_t ulva_button_decode_mv(int mv)
{
    // Small negative readings can result from calibration near ground.
    if (mv >= -50 && mv <= 250) return ULVA_BUTTON_UP;
    if (mv >= 800 && mv <= 1300) return ULVA_BUTTON_OK;
    if (mv >= 1650 && mv <= 2300) return ULVA_BUTTON_DOWN;
    if (mv >= 2850 && mv <= 3600) return ULVA_BUTTON_NONE;
    return ULVA_BUTTON_INVALID;
}

const char *ulva_button_name(ulva_button_t button)
{
    switch (button) {
    case ULVA_BUTTON_NONE: return "NONE";
    case ULVA_BUTTON_UP: return "UP";
    case ULVA_BUTTON_OK: return "OK";
    case ULVA_BUTTON_DOWN: return "DOWN";
    default: return "INVALID";
    }
}

void ulva_buttons_init(ulva_buttons_t *buttons)
{
    *buttons = (ulva_buttons_t) {
        .stable = ULVA_BUTTON_NONE,
        .candidate = ULVA_BUTTON_INVALID,
    };
}

bool ulva_buttons_update(ulva_buttons_t *buttons, bool sample_valid, int mv,
                         uint64_t now_ms, ulva_button_change_t *change)
{
    const ulva_button_t sample = sample_valid ? ulva_button_decode_mv(mv)
                                             : ULVA_BUTTON_INVALID;
    const bool gap = !buttons->has_sample || now_ms < buttons->last_sample_ms ||
        now_ms - buttons->last_sample_ms > ULVA_BUTTON_MAX_SAMPLE_GAP_MS;
    buttons->has_sample = true;
    buttons->last_sample_ms = now_ms;
    if (gap || sample != buttons->candidate) {
        buttons->candidate = sample;
        buttons->candidate_since_ms = now_ms;
        return false;
    }
    if (sample == buttons->stable ||
        now_ms - buttons->candidate_since_ms < ULVA_BUTTON_DEBOUNCE_MS) {
        return false;
    }
    *change = (ulva_button_change_t) {
        .previous = buttons->stable,
        .current = sample,
    };
    buttons->stable = sample;
    return true;
}

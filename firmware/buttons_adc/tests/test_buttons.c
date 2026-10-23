#include <assert.h>
#include <stdio.h>
#include "ulva_buttons.h"

static ulva_buttons_t state;
static ulva_button_change_t event;
static bool sample(int mv, unsigned long long ms)
{
    return ulva_buttons_update(&state, true, mv, ms, &event);
}

int main(void)
{
    const struct { int mv; ulva_button_t button; } cases[] = {
        {-51,ULVA_BUTTON_INVALID},{-50,ULVA_BUTTON_UP},{0,ULVA_BUTTON_UP},
        {250,ULVA_BUTTON_UP},{251,ULVA_BUTTON_INVALID},
        {799,ULVA_BUTTON_INVALID},{800,ULVA_BUTTON_OK},{1055,ULVA_BUTTON_OK},
        {1300,ULVA_BUTTON_OK},{1301,ULVA_BUTTON_INVALID},
        {1649,ULVA_BUTTON_INVALID},{1650,ULVA_BUTTON_DOWN},{1964,ULVA_BUTTON_DOWN},
        {2300,ULVA_BUTTON_DOWN},{2301,ULVA_BUTTON_INVALID},
        {2849,ULVA_BUTTON_INVALID},{2850,ULVA_BUTTON_NONE},{3300,ULVA_BUTTON_NONE},
        {3600,ULVA_BUTTON_NONE},{3601,ULVA_BUTTON_INVALID},
    };
    for (unsigned i=0; i<sizeof(cases)/sizeof(cases[0]); ++i)
        assert(ulva_button_decode_mv(cases[i].mv) == cases[i].button);

    // An initially held button is accepted at 30ms, not on the first sample.
    ulva_buttons_init(&state);
    assert(!sample(0,0)); assert(!sample(0,10)); assert(!sample(0,20));
    assert(!sample(0,29)); assert(sample(0,30));
    assert(event.previous==ULVA_BUTTON_NONE && event.current==ULVA_BUTTON_UP);
    assert(!sample(0,40)); assert(!sample(0,50)); // one press while held

    // Contact bounce restarts the full debounce period, including release.
    assert(!sample(3300,60)); assert(!sample(0,70));
    assert(!sample(3300,80)); assert(!sample(3300,90)); assert(!sample(3300,100));
    assert(sample(3300,110));
    assert(event.previous==ULVA_BUTTON_UP && event.current==ULVA_BUTTON_NONE);

    // Invalid voltage gaps cannot bridge two runs of a valid candidate.
    assert(!sample(1055,120)); assert(!sample(1055,130));
    assert(!sample(1500,140)); assert(!sample(1055,150));
    assert(!sample(1055,160)); assert(!sample(1055,170)); assert(sample(1055,180));
    assert(event.current==ULVA_BUTTON_OK);

    // Moving straight to a different ladder tap releases the old button.
    assert(!sample(1964,190)); assert(!sample(1964,200)); assert(!sample(1964,210));
    assert(sample(1964,220));
    assert(event.previous==ULVA_BUTTON_OK && event.current==ULVA_BUTTON_DOWN);

    // Failed ADC reads with a stale/zero value must never look like UP.
    for (unsigned t=230;t<260;t+=10)
        assert(!ulva_buttons_update(&state,false,0,t,&event));
    assert(ulva_buttons_update(&state,false,0,260,&event));
    assert(event.previous==ULVA_BUTTON_DOWN && event.current==ULVA_BUTTON_INVALID);
    assert(!sample(3300,270)); assert(!sample(3300,280)); assert(!sample(3300,290));
    assert(sample(3300,300)); assert(event.current==ULVA_BUTTON_NONE);

    // A delayed task cannot turn two distant samples into a stable press.
    assert(!sample(1055,310)); assert(!sample(1055,1000));
    assert(!sample(1055,1010)); assert(!sample(1055,1020)); assert(sample(1055,1030));
    assert(event.current==ULVA_BUTTON_OK);
    // Also tolerate a caller resetting its clock without unsigned underflow.
    assert(!sample(1964,5)); assert(!sample(1964,15)); assert(!sample(1964,25));
    assert(sample(1964,35)); assert(event.current==ULVA_BUTTON_DOWN);
    puts("PASS: voltage windows, startup, bounce, hold, release, tap changes, errors, gaps and clock reset");
    return 0;
}

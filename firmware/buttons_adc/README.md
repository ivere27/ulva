# Button ADC example

This standalone ESP-IDF application reads UP, OK and DOWN on ESP32-C5
GPIO1/ADC1_CH0. It uses R12=10 kΩ, R13=4.7 kΩ, R14=10 kΩ and C15=100 nF
on the [Ulva carrier](../../docs/hardware.md).

One calibrated ADC sample is read every 10 ms. A state change is reported
after 30 ms of stability, with FreeRTOS sleeping between samples. The example
implements button input only.

## Build and run

Use ESP-IDF v5.5.1. From the repository root:

```sh
cd firmware/buttons_adc
idf.py set-target esp32c5
idf.py menuconfig
idf.py build
idf.py -p /dev/ttyACM0 flash monitor
```

Set the connected board's Flash capacity and console path in `menuconfig`,
and replace the serial port as needed. Defaults use the standard IDF partition
configuration and do not use PSRAM.

## Host unit tests

Run the button decode unit tests on the host machine without ESP-IDF or hardware:

```sh
cmake -S firmware/buttons_adc/tests -B build/buttons-tests
cmake --build build/buttons-tests
ctest --test-dir build/buttons-tests --output-on-failure
```

## Use the component

Copy `components/ulva_buttons/` into an ESP-IDF application and pass an existing
ADC1 oneshot handle to `ulva_buttons_adc_init()`. Buttons use ADC1_CH0;
the board's DIP input uses CH5 and voltage monitor uses CH4. Share one ADC1
handle, use 12 dB attenuation and disable internal pulls. Handle calibration
initialization failure; do not substitute an approximate raw conversion.

Feed calibrated millivolts and a monotonic millisecond timestamp to
`ulva_buttons_update()` from one task. Pass `sample_valid=false` on an ADC
error. Change events contain previous and current states: NONE releases and
INVALID cancels. A button held at startup uses the same debounce interval.
Invalid readings lasting 30 ms cancel a press; sample gaps over 20 ms restart
the stability interval. Simultaneous presses prioritize UP, then OK, then DOWN.

Keep callbacks short and queue slow work to other tasks. Long-press/repeat
behavior and button wake from deep sleep are not provided. Initialization and
cleanup must not run concurrently with reads. The component owns its
calibration handle, not the ADC1 handle; do not use ADC1 continuous/DMA mode
at the same time.

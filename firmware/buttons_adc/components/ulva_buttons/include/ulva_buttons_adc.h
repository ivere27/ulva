#pragma once

#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_oneshot.h"
#include "ulva_buttons.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    adc_oneshot_unit_handle_t unit;
    adc_cali_handle_t calibration;
} ulva_buttons_adc_t;

// Pass an existing ADC_UNIT_1 oneshot handle. The caller owns its lifetime.
// GPIO6/DIP can use channel5 of this SAME handle; do not allocate ADC1 twice.
// init/deinit must not run concurrently with reads. Use a zero-initialized
// context and deinit it before reuse. Requires ESP32-C5 and eFuse calibration.
esp_err_t ulva_buttons_adc_init(ulva_buttons_adc_t *adc,
                               adc_oneshot_unit_handle_t adc1);
esp_err_t ulva_buttons_adc_read_mv(ulva_buttons_adc_t *adc, int *mv);
esp_err_t ulva_buttons_adc_deinit(ulva_buttons_adc_t *adc);

#ifdef __cplusplus
}
#endif

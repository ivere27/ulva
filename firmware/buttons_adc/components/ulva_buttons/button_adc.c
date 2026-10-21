#include "ulva_buttons_adc.h"
#include "driver/gpio.h"
#include "esp_adc/adc_cali_scheme.h"
#include "sdkconfig.h"

#if !CONFIG_IDF_TARGET_ESP32C5
#error "The GPIO1/ADC1_CH0 button ladder is designed for ESP32-C5."
#endif

esp_err_t ulva_buttons_adc_init(ulva_buttons_adc_t *adc,
                               adc_oneshot_unit_handle_t adc1)
{
    if (!adc || !adc1 || adc->calibration || adc->unit) return ESP_ERR_INVALID_ARG;
    const adc_oneshot_chan_cfg_t channel = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    esp_err_t err = adc_oneshot_config_channel(adc1, ADC_CHANNEL_0, &channel);
    if (err != ESP_OK) return err;
    err = gpio_pullup_dis(GPIO_NUM_1);
    if (err != ESP_OK) return err;
    err = gpio_pulldown_dis(GPIO_NUM_1);
    if (err != ESP_OK) return err;
    const adc_cali_curve_fitting_config_t calibration = {
        .unit_id = ADC_UNIT_1,
        .chan = ADC_CHANNEL_0,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    err = adc_cali_create_scheme_curve_fitting(&calibration, &adc->calibration);
    // No raw*3300/4095 fallback: voltage windows require calibrated readings.
    if (err != ESP_OK) return err;
    adc->unit = adc1;
    return ESP_OK;
}

esp_err_t ulva_buttons_adc_read_mv(ulva_buttons_adc_t *adc, int *mv)
{
    if (!adc || !adc->unit || !adc->calibration || !mv) return ESP_ERR_INVALID_ARG;
    int raw;
    esp_err_t err = adc_oneshot_read(adc->unit, ADC_CHANNEL_0, &raw);
    if (err != ESP_OK) return err;
    return adc_cali_raw_to_voltage(adc->calibration, raw, mv);
}

esp_err_t ulva_buttons_adc_deinit(ulva_buttons_adc_t *adc)
{
    if (!adc || !adc->calibration) return ESP_ERR_INVALID_ARG;
    esp_err_t err = adc_cali_delete_scheme_curve_fitting(adc->calibration);
    if (err == ESP_OK) *adc = (ulva_buttons_adc_t){0};
    return err;
}

#include "ulva_buttons_adc.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "buttons";
static ulva_buttons_adc_t adc;

static void button_changed(const ulva_button_change_t *change, int mv)
{
    // Replace these logs with application UI events. Keep this callback short;
    // queue slow display/network work in another task.
    if (change->current == ULVA_BUTTON_INVALID) {
        ESP_LOGW(TAG, "input invalid; cancel %s", ulva_button_name(change->previous));
        return;
    }
    if (change->previous > ULVA_BUTTON_NONE) {
        ESP_LOGI(TAG, "release %s", ulva_button_name(change->previous));
    }
    if (change->current > ULVA_BUTTON_NONE) {
        ESP_LOGI(TAG, "press %s (%d mV)", ulva_button_name(change->current), mv);
    }
}

static void button_task(void *arg)
{
    (void)arg;
    ulva_buttons_t buttons;
    ulva_buttons_init(&buttons);
    const TickType_t period = pdMS_TO_TICKS(ULVA_BUTTON_SCAN_MS);
    configASSERT(period > 0);
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        // Sleeping between scans lets other tasks run and the CPU enter idle.
        vTaskDelayUntil(&wake, period);
        int mv = 0;
        const esp_err_t err = ulva_buttons_adc_read_mv(&adc, &mv);
        const uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);
        ulva_button_change_t change;
        if (ulva_buttons_update(&buttons, err == ESP_OK, mv, now_ms, &change)) {
            button_changed(&change, mv);
        }
        // After a delayed scan, skip missed periods instead of busy catch-up.
        const TickType_t finished = xTaskGetTickCount();
        if ((TickType_t)(finished - wake) >= period) wake = finished;
    }
}

void app_main(void)
{
    adc_oneshot_unit_handle_t adc1;
    const adc_oneshot_unit_init_cfg_t unit = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit, &adc1));
    // In the controller firmware, read the GPIO6 DIP at boot through adc1,
    // then pass this same handle to the buttons component.
    ESP_ERROR_CHECK(ulva_buttons_adc_init(&adc, adc1));
    BaseType_t created = xTaskCreate(button_task, "buttons", 3072, NULL, 2, NULL);
    ESP_ERROR_CHECK(created == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
}

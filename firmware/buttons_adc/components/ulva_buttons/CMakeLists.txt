idf_component_register(SRCS "button_decode.c" "button_adc.c"
                       INCLUDE_DIRS "include"
                       REQUIRES esp_adc esp_driver_gpio)

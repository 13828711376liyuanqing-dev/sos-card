/**
 *****************************************************************************************
 *
 * @file gpio28_test.c
 *
 * @brief GPIO28 Test for ETA69631 Charging IC.
 *
 *****************************************************************************************
 * @attention
 *  #####Copyright (c) 2024
 *  All rights reserved.
 *
 *****************************************************************************************
 */

#include "user_app.h"
#include "user_periph_setup.h"
#include "transport_scheduler.h"
#include "gr_includes.h"
#include "app_log.h"
#include "app_io.h"
#include "app_i2c.h"
#include "app_gpiote.h"
#include "board_SK.h"

/**
 *****************************************************************************************
 * @brief Test GPIO28 configuration for ETA69631 SDA.
 * @return true if GPIO28 is configured correctly, false otherwise.
 *****************************************************************************************
 */
bool test_gpio28_config(void)
{
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;
    app_io_pin_state_t pin_state;
    uint16_t ret;
    
    APP_LOG_INFO("Testing GPIO28 configuration for ETA69631 SDA");
    
    /* Test 1: Configure GPIO28 as output to test basic functionality */
    io_init.pin = APP_IO_PIN_28;
    io_init.mode = APP_IO_MODE_OUTPUT;
    io_init.pull = APP_IO_NOPULL;
    io_init.mux = APP_IO_MUX_0;
    
    /* Try GPIOB first (most likely for GPIO28) */
    ret = app_io_init(APP_IO_TYPE_GPIOB, &io_init);
    if (ret == APP_DRV_SUCCESS)
    {
        APP_LOG_INFO("GPIO28 configured as GPIOB_PIN_12 (APP_IO_TYPE_GPIOB)");
        
        /* Test write operation */
        app_io_write_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_28, APP_IO_PIN_SET);
        app_io_read_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_28, &pin_state);
        APP_LOG_INFO("GPIO28 write test: pin state = %d", pin_state);
        
        app_io_write_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_28, APP_IO_PIN_RESET);
        app_io_read_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_28, &pin_state);
        APP_LOG_INFO("GPIO28 write test: pin state = %d", pin_state);
        
        /* Deinit for I2C use */
        app_io_deinit(APP_IO_TYPE_GPIOB, APP_IO_PIN_28);
        return true;
    }
    
    /* Try GPIOA if GPIOB fails */
    ret = app_io_init(APP_IO_TYPE_GPIOA, &io_init);
    if (ret == APP_DRV_SUCCESS)
    {
        APP_LOG_INFO("GPIO28 configured as GPIOA (APP_IO_TYPE_GPIOA)");
        
        /* Test write operation */
        app_io_write_pin(APP_IO_TYPE_GPIOA, APP_IO_PIN_28, APP_IO_PIN_SET);
        app_io_read_pin(APP_IO_TYPE_GPIOA, APP_IO_PIN_28, &pin_state);
        APP_LOG_INFO("GPIO28 write test: pin state = %d", pin_state);
        
        app_io_write_pin(APP_IO_TYPE_GPIOA, APP_IO_PIN_28, APP_IO_PIN_RESET);
        app_io_read_pin(APP_IO_TYPE_GPIOA, APP_IO_PIN_28, &pin_state);
        APP_LOG_INFO("GPIO28 write test: pin state = %d", pin_state);
        
        /* Deinit for I2C use */
        app_io_deinit(APP_IO_TYPE_GPIOA, APP_IO_PIN_28);
        return true;
    }
    
    APP_LOG_ERROR("Failed to configure GPIO28 as either GPIOA or GPIOB");
    return false;
}

/**
 *****************************************************************************************
 * @brief Test AON_GPIO4 and AON_GPIO5 configuration.
 * @return true if AON GPIOs are configured correctly, false otherwise.
 *****************************************************************************************
 */
bool test_aon_gpio_config(void)
{
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;
    app_io_pin_state_t pin_state;
    uint16_t ret;
    
    APP_LOG_INFO("Testing AON_GPIO4 (SCL) and AON_GPIO5 (INT) configuration");
    
    /* Test AON_GPIO4 (SCL) */
    io_init.pin = APP_IO_PIN_4;
    io_init.mode = APP_IO_MODE_OUTPUT;
    io_init.pull = APP_IO_NOPULL;
    io_init.mux = APP_IO_MUX_0;
    
    ret = app_io_init(APP_IO_TYPE_AON, &io_init);
    if (ret != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("Failed to configure AON_GPIO4");
        return false;
    }
    
    app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_4, APP_IO_PIN_SET);
    app_io_read_pin(APP_IO_TYPE_AON, APP_IO_PIN_4, &pin_state);
    APP_LOG_INFO("AON_GPIO4 test: pin state = %d", pin_state);
    
    /* Test AON_GPIO5 (INT) */
    io_init.pin = APP_IO_PIN_5;
    io_init.mode = APP_IO_MODE_INPUT;
    io_init.pull = APP_IO_PULLUP;
    io_init.mux = APP_IO_MUX_0;
    
    ret = app_io_init(APP_IO_TYPE_AON, &io_init);
    if (ret != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("Failed to configure AON_GPIO5");
        app_io_deinit(APP_IO_TYPE_AON, APP_IO_PIN_4);
        return false;
    }
    
    app_io_read_pin(APP_IO_TYPE_AON, APP_IO_PIN_5, &pin_state);
    APP_LOG_INFO("AON_GPIO5 test: pin state = %d", pin_state);
    
    /* Cleanup */
    app_io_deinit(APP_IO_TYPE_AON, APP_IO_PIN_4);
    app_io_deinit(APP_IO_TYPE_AON, APP_IO_PIN_5);
    
    return true;
}

/**
 *****************************************************************************************
 * @brief Run complete GPIO test for ETA69631.
 *****************************************************************************************
 */
void run_gpio_test_for_eta69631(void)
{
    APP_LOG_INFO("=== Starting GPIO Test for ETA69631 Charging IC ===");
    
    bool gpio28_ok = test_gpio28_config();
    bool aon_gpio_ok = test_aon_gpio_config();
    
    if (gpio28_ok && aon_gpio_ok)
    {
        APP_LOG_INFO("=== GPIO Test PASSED ===");
        APP_LOG_INFO("GPIO28: OK (configured as normal GPIO)");
        APP_LOG_INFO("AON_GPIO4 (SCL): OK");
        APP_LOG_INFO("AON_GPIO5 (INT): OK");
    }
    else
    {
        APP_LOG_ERROR("=== GPIO Test FAILED ===");
        if (!gpio28_ok) APP_LOG_ERROR("GPIO28 test failed");
        if (!aon_gpio_ok) APP_LOG_ERROR("AON GPIO test failed");
    }
    
    APP_LOG_INFO("=== GPIO Test Complete ===");
}
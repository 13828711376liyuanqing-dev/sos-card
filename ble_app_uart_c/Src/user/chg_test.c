/**
 *****************************************************************************************
 *
 * @file chg_test.c
 *
 * @brief ETA69631 Charging IC Test Functions.
 *
 *****************************************************************************************
 * @attention
 *  #####Copyright (c) 2024
 *  All rights reserved.
 *
 *****************************************************************************************
 */

#include "eta69631.h"
#include "app_log.h"
#include <stdio.h>

/**
 *****************************************************************************************
 * @brief Test ETA69631 initialization.
 *****************************************************************************************
 */
void chg_test_init(void)
{
    APP_LOG_INFO("=== ETA69631 Initialization Test ===");
    
    if (eta69631_init())
    {
        APP_LOG_INFO("ETA69631 initialization PASSED");
    }
    else
    {
        APP_LOG_ERROR("ETA69631 initialization FAILED");
    }
}

/**
 *****************************************************************************************
 * @brief Test ETA69631 register read/write.
 *****************************************************************************************
 */
void chg_test_reg_access(void)
{
    uint8_t reg_value;
    
    APP_LOG_INFO("=== ETA69631 Register Access Test ===");
    
    /* Test reading IC ID register */
    if (eta69631_read_reg(ETA69631_REG_IC_ID, &reg_value))
    {
        APP_LOG_INFO("IC ID Register: 0x%02X", reg_value);
    }
    else
    {
        APP_LOG_ERROR("Failed to read IC ID register");
    }
    
    /* Test reading system status */
    eta69631_status_t status;
    if (eta69631_get_status(&status))
    {
        APP_LOG_INFO("System Status: CHRG=0x%02X, VBUS=0x%02X, PG=%d", 
                   status.chrg_status, status.vbus_status, status.pg_stat);
    }
    else
    {
        APP_LOG_ERROR("Failed to read system status");
    }
}

/**
 *****************************************************************************************
 * @brief Test ETA69631 battery information.
 *****************************************************************************************
 */
void chg_test_battery_info(void)
{
    APP_LOG_INFO("=== ETA69631 Battery Information Test ===");
    
    eta69631_battery_info_t battery_info;
    if (eta69631_get_battery_info(&battery_info))
    {
        APP_LOG_INFO("Battery Voltage: %dmV", battery_info.bat_voltage);
        APP_LOG_INFO("System Voltage: %dmV", battery_info.sys_voltage);
        APP_LOG_INFO("Charge Current: %dmA", battery_info.charge_current);
    }
    else
    {
        APP_LOG_ERROR("Failed to get battery information");
    }
}

/**
 *****************************************************************************************
 * @brief Test ETA69631 fault status.
 *****************************************************************************************
 */
void chg_test_fault_status(void)
{
    APP_LOG_INFO("=== ETA69631 Fault Status Test ===");
    
    eta69631_fault_t fault;
    if (eta69631_get_fault(&fault))
    {
        if (fault.watchdog_fault)
            APP_LOG_WARNING("Watchdog Fault");
        if (fault.boost_fault)
            APP_LOG_WARNING("Boost Fault");
        if (fault.chrg_fault != ETA69631_FAULT_CHRG_NORMAL)
            APP_LOG_WARNING("Charge Fault: 0x%02X", fault.chrg_fault);
        if (fault.bat_fault != ETA69631_FAULT_BAT_NORMAL)
            APP_LOG_WARNING("Battery Fault: 0x%02X", fault.bat_fault);
        if (fault.ntc_fault != ETA69631_FAULT_NTC_NORMAL)
            APP_LOG_WARNING("NTC Fault: 0x%02X", fault.ntc_fault);
        
        if (!fault.watchdog_fault && !fault.boost_fault &&
            fault.chrg_fault == ETA69631_FAULT_CHRG_NORMAL &&
            fault.bat_fault == ETA69631_FAULT_BAT_NORMAL &&
            fault.ntc_fault == ETA69631_FAULT_NTC_NORMAL)
        {
            APP_LOG_INFO("No faults detected");
        }
    }
    else
    {
        APP_LOG_ERROR("Failed to get fault status");
    }
}

/**
 *****************************************************************************************
 * @brief Test ETA69631 charging control.
 *****************************************************************************************
 */
void chg_test_charging_control(void)
{
    APP_LOG_INFO("=== ETA69631 Charging Control Test ===");
    
    /* Check current charging status */
    const char* status_str = eta69631_get_chrg_status_string();
    APP_LOG_INFO("Current Charging Status: %s", status_str);
    
    /* Check if charging is done */
    if (eta69631_is_charging_done())
    {
        APP_LOG_INFO("Charging is complete");
    }
    else
    {
        APP_LOG_INFO("Charging is in progress or not started");
    }
    
    /* Check power good status */
    if (eta69631_is_power_good())
    {
        APP_LOG_INFO("Power is good");
    }
    else
    {
        APP_LOG_WARNING("Power is not good");
    }
}

/**
 *****************************************************************************************
 * @brief Test ETA69631 configuration.
 *****************************************************************************************
 */
void chg_test_configuration(void)
{
    APP_LOG_INFO("=== ETA69631 Configuration Test ===");
    
    /* Test setting charge current */
    if (eta69631_set_charge_current(1000))  /* 1000mA */
    {
        APP_LOG_INFO("Set charge current to 1000mA");
    }
    else
    {
        APP_LOG_ERROR("Failed to set charge current");
    }
    
    /* Test setting charge voltage */
    if (eta69631_set_charge_voltage(4200))  /* 4.2V */
    {
        APP_LOG_INFO("Set charge voltage to 4200mV");
    }
    else
    {
        APP_LOG_ERROR("Failed to set charge voltage");
    }
    
    /* Test setting input current limit */
    if (eta69631_set_input_current_limit(2000))  /* 2000mA */
    {
        APP_LOG_INFO("Set input current limit to 2000mA");
    }
    else
    {
        APP_LOG_ERROR("Failed to set input current limit");
    }
}

/**
 *****************************************************************************************
 * @brief Run all ETA69631 tests.
 *****************************************************************************************
 */
void chg_test_run_all(void)
{
    APP_LOG_INFO("=========================================");
    APP_LOG_INFO("  ETA69631 Charging IC Comprehensive Test");
    APP_LOG_INFO("=========================================");
    
    chg_test_init();
    chg_test_reg_access();
    chg_test_battery_info();
    chg_test_fault_status();
    chg_test_charging_control();
    chg_test_configuration();
    
    /* Print final status */
    eta69631_print_status();
    
    APP_LOG_INFO("=========================================");
    APP_LOG_INFO("  ETA69631 Test Complete");
    APP_LOG_INFO("=========================================");
}

/**
 *****************************************************************************************
 * @brief Print ETA69631 status information periodically.
 * @param interval_ms: Interval in milliseconds between prints.
 *****************************************************************************************
 */
void chg_test_monitor(uint32_t interval_ms)
{
    static uint32_t last_print_time = 0;
    static uint32_t current_time = 0;
    
    current_time += 100; /* Assuming called every 100ms */
    
    if (current_time - last_print_time >= interval_ms)
    {
        last_print_time = current_time;
        
        eta69631_status_t status;
        eta69631_battery_info_t battery_info;
        
        if (eta69631_get_status(&status) && eta69631_get_battery_info(&battery_info))
        {
            APP_LOG_INFO("[CHG Monitor] Status: %s, Battery: %dmV, System: %dmV, Charge: %dmA",
                       eta69631_get_chrg_status_string(),
                       battery_info.bat_voltage,
                       battery_info.sys_voltage,
                       battery_info.charge_current);
        }
    }
}

/**
 *****************************************************************************************
 * @brief Handle SOS button press for charging IC test.
 *****************************************************************************************
 */
void chg_test_sos_handler(void)
{
    static uint8_t test_mode = 0;
    
    test_mode++;
    if (test_mode > 3) test_mode = 0;
    
    switch (test_mode)
    {
        case 0:
            APP_LOG_INFO("Charging IC Test: Disabled");
            break;
        case 1:
            APP_LOG_INFO("Charging IC Test: Print Status");
            eta69631_print_status();
            break;
        case 2:
            APP_LOG_INFO("Charging IC Test: Battery Info");
            chg_test_battery_info();
            break;
        case 3:
            APP_LOG_INFO("Charging IC Test: Full Test");
            chg_test_run_all();
            break;
    }
}

/**
 *****************************************************************************************
 *
 * @file eta69631.c
 *
 * @brief ETA69631 Charging IC Driver Implementation.
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
#include "scatter_common.h"
#include "flash_scatter_config.h"
#include "patch.h"
#include "app_log.h"
#include "app_io.h"
#include "app_i2c.h"
#include "app_gpiote.h"
#include "board_SK.h"
#include "eta69631.h"
#include <string.h>

/*
 * DEFINES
 *****************************************************************************************
 */

/* I2C Configuration - Final configuration based on your information:
   GPIO28: CHG_SDA (I2C SDA)
   AON_GPIO4: CHG_SCL (I2C SCL)
   AON_GPIO5: CHG_INT (Interrupt) */
#define ETA69631_I2C_SDA_GPIO_TYPE  ETA69631_I2C_SDA_TYPE
#define ETA69631_I2C_SDA_GPIO_PIN   ETA69631_I2C_SDA_PIN
#define ETA69631_I2C_SDA_GPIO_MUX   APP_IO_MUX_0  /* Normal GPIO uses MUX_0 */

#define ETA69631_I2C_SCL_GPIO_TYPE  ETA69631_I2C_SCL_TYPE
#define ETA69631_I2C_SCL_GPIO_PIN   ETA69631_I2C_SCL_PIN
#define ETA69631_I2C_SCL_GPIO_MUX   APP_IO_MUX_0  /* AON GPIO通常使用MUX_0 */

/* Interrupt pin for CHRG/STDBY status - Using AON GPIO5 as CHG_INT */
#define ETA69631_INT_GPIO_TYPE      ETA69631_INT_TYPE
#define ETA69631_INT_GPIO_PIN       ETA69631_INT_PIN
#define ETA69631_INT_GPIO_MUX       APP_IO_MUX_0  /* AON GPIO通常使用MUX_0 */

#define ETA69631_I2C_ID             APP_I2C_ID_1
#define ETA69631_I2C_SPEED          I2C_SPEED_400K

/* Default configuration values */
#define ETA69631_DEFAULT_CHRG_CURRENT  1000    /* 1000mA */
#define ETA69631_DEFAULT_CHRG_VOLTAGE  4200    /* 4.2V */
#define ETA69631_DEFAULT_INPUT_CURRENT 2000    /* 2000mA */

/* Voltage and current conversion factors */
#define ETA69631_VBAT_STEP           80       /* 80mV per bit */
#define ETA69631_VSYS_STEP           80       /* 80mV per bit */
#define ETA69631_ICHG_STEP           64       /* 64mA per bit */

/* Register value to mA conversion */
#define ETA69631_ICHG_REG_TO_MA(reg) ((reg * ETA69631_ICHG_STEP) + 64)
#define ETA69631_MA_TO_ICHG_REG(ma)  (((ma - 64) + (ETA69631_ICHG_STEP/2)) / ETA69631_ICHG_STEP)

/*
 * LOCAL VARIABLE DEFINITIONS
 *****************************************************************************************
 */

static app_i2c_params_t s_eta69631_i2c_params = {
    .id = ETA69631_I2C_ID,
    .role = APP_I2C_ROLE_MASTER,
    .pin_cfg = {
        .scl = {
            .type = ETA69631_I2C_SCL_GPIO_TYPE,
            .mux = ETA69631_I2C_SCL_GPIO_MUX,
            .pin = ETA69631_I2C_SCL_GPIO_PIN,
            .pull = APP_IO_PULLUP,
        },
        .sda = {
            .type = ETA69631_I2C_SDA_GPIO_TYPE,
            .mux = ETA69631_I2C_SDA_GPIO_MUX,
            .pin = ETA69631_I2C_SDA_GPIO_PIN,
            .pull = APP_IO_PULLUP,
        },
    },
    .dma_cfg = {
#if (APP_DRIVER_CHIP_TYPE == APP_DRIVER_GR5332X) || (APP_DRIVER_CHIP_TYPE == APP_DRIVER_GR551X)
        .tx_dma_instance = DMA0,
        .rx_dma_instance = DMA0,
#else
        .tx_dma_instance = DMA1,
        .rx_dma_instance = DMA1,
#endif
        .tx_dma_channel = DMA_Channel0,
        .rx_dma_channel = DMA_Channel1,
    },
    .init = {
        .speed = ETA69631_I2C_SPEED,
        .own_address = 0x00,
        .addressing_mode = I2C_ADDRESSINGMODE_7BIT,
        .general_call_mode = I2C_GENERALCALL_DISABLE,
    },
};

static bool s_eta69631_initialized = false;
static volatile bool s_eta69631_int_triggered = false;
static eta69631_status_t s_last_status = {0};
static eta69631_fault_t s_last_fault = {0};

/*
 * LOCAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */

/**
 *****************************************************************************************
 * @brief I2C event handler.
 * @param[in] p_evt: Pointer to I2C event.
 *****************************************************************************************
 */
static void eta69631_i2c_evt_handler(app_i2c_evt_t *p_evt)
{
    /* Currently not used, but required for I2C initialization */
    (void)p_evt;
}

/**
 *****************************************************************************************
 * @brief GPIO interrupt handler for CHRG/STDBY status.
 * @param[in] p_evt: Pointer to GPIO event.
 *****************************************************************************************
 */
static void eta69631_gpio_evt_handler(app_io_evt_t *p_evt)
{
    if (p_evt->pin == ETA69631_INT_GPIO_PIN)
    {
        s_eta69631_int_triggered = true;
        APP_LOG_DEBUG("ETA69631 interrupt triggered");
    }
}

/**
 *****************************************************************************************
 * @brief Configure GPIO interrupt for CHRG/STDBY status.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
static bool eta69631_gpio_int_init(void)
{
    app_io_init_t io_init;
    app_io_pin_state_t pin_state;
    uint16_t ret;
    
    /* Initialize io_init structure */
    io_init.pin = ETA69631_INT_GPIO_PIN;
    io_init.mode = APP_IO_MODE_IT_BOTH_EDGE;
    io_init.pull = APP_IO_PULLUP;
    io_init.mux = ETA69631_INT_GPIO_MUX;
    io_init.mux = ETA69631_INT_GPIO_MUX;
    
    ret = app_io_init(ETA69631_INT_GPIO_TYPE, &io_init);
    if (ret != APP_DRV_SUCCESS)
    {
        APP_LOG_ERROR("Failed to init ETA69631 interrupt pin");
        return false;
    }
    
    /* Read initial pin state */
    pin_state = app_io_read_pin(ETA69631_INT_GPIO_TYPE, ETA69631_INT_GPIO_PIN);
    APP_LOG_DEBUG("ETA69631 INT pin initial state: %d", pin_state);
    
    return true;
}

/**
 *****************************************************************************************
 * @brief Configure GPIOTE for interrupt.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
static bool eta69631_gpiote_init(void)
{
    app_gpiote_param_t gpiote_param = {
        .type = ETA69631_INT_GPIO_TYPE,
        .pin = ETA69631_INT_GPIO_PIN,
        .mode = APP_IO_MODE_IT_BOTH_EDGE,
        .pull = APP_IO_PULLUP,
        .io_evt_cb = eta69631_gpio_evt_handler,
    };
    
    app_gpiote_init(&gpiote_param, 1);
    return true;
}

/**
 *****************************************************************************************
 * @brief Read multiple registers from ETA69631.
 * @param[in] reg: Starting register address.
 * @param[out] p_data: Pointer to buffer for read data.
 * @param[in] length: Number of bytes to read.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
static bool eta69631_read_regs(uint8_t reg, uint8_t *p_data, uint8_t length)
{
    sdk_err_t error_code;
    
    if (!s_eta69631_initialized)
    {
        /* Don't log error here - let the caller decide */
        return false;
    }
    
    error_code = app_i2c_mem_read_sync(ETA69631_I2C_ID, 
                                       ETA69631_I2C_ADDR, 
                                       reg, 
                                       I2C_MEMADD_SIZE_8BIT, 
                                       p_data, 
                                       length, 
                                       1000);  /* 1 second timeout */
    
    if (error_code != SDK_SUCCESS)
    {
        /* Don't log error here - let the caller decide */
        return false;
    }
    
    return true;
}

/**
 *****************************************************************************************
 * @brief Write multiple registers to ETA69631.
 * @param[in] reg: Starting register address.
 * @param[in] p_data: Pointer to data to write.
 * @param[in] length: Number of bytes to write.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
static bool eta69631_write_regs(uint8_t reg, uint8_t *p_data, uint8_t length)
{
    sdk_err_t error_code;
    
    if (!s_eta69631_initialized)
    {
        /* Don't log error here - let the caller decide */
        return false;
    }
    
    error_code = app_i2c_mem_write_sync(ETA69631_I2C_ID, 
                                        ETA69631_I2C_ADDR, 
                                        reg, 
                                        I2C_MEMADD_SIZE_8BIT, 
                                        p_data, 
                                        length, 
                                        1000);  /* 1 second timeout */
    
    if (error_code != SDK_SUCCESS)
    {
        /* Don't log error here - let the caller decide */
        return false;
    }
    
    return true;
}

/**
 *****************************************************************************************
 * @brief Convert register value to battery voltage (mV).
 * @param[in] reg_value: Register value.
 * @return Battery voltage in mV.
 *****************************************************************************************
 */
static uint16_t eta69631_reg_to_bat_voltage(uint8_t reg_value)
{
    return (reg_value * ETA69631_VBAT_STEP);
}

/**
 *****************************************************************************************
 * @brief Convert register value to system voltage (mV).
 * @param[in] reg_value: Register value.
 * @return System voltage in mV.
 *****************************************************************************************
 */
static uint16_t eta69631_reg_to_sys_voltage(uint8_t reg_value)
{
    return (reg_value * ETA69631_VSYS_STEP);
}

/**
 *****************************************************************************************
 * @brief Convert register value to charge current (mA).
 * @param[in] reg_value: Register value.
 * @return Charge current in mA.
 *****************************************************************************************
 */
static uint16_t eta69631_reg_to_chrg_current(uint8_t reg_value)
{
    return ETA69631_ICHG_REG_TO_MA(reg_value);
}

/*
 * GLOBAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */

bool eta69631_init(void)
{
    sdk_err_t error_code;
    uint8_t reg_value;
    
    if (s_eta69631_initialized)
    {
        APP_LOG_WARNING("ETA69631 already initialized");
        return true;
    }
    
    APP_LOG_INFO("=== ETA69631 Initialization Start ===");
    
    /* Initialize I2C */
    APP_LOG_INFO("1. Initializing I2C interface...");
    error_code = app_i2c_init(&s_eta69631_i2c_params, eta69631_i2c_evt_handler);
    if (error_code != SDK_SUCCESS)
    {
        APP_LOG_ERROR("Failed to init ETA69631 I2C: 0x%02X", error_code);
        return false;
    }
    APP_LOG_INFO("  I2C initialized successfully");
    
    /* Temporarily set initialized flag to allow read_regs to work */
    s_eta69631_initialized = true;
    
    /* Small delay to ensure I2C is ready */
    // app_delay_ms(10);
    
    /* Check if device is present by reading IC ID */
    APP_LOG_INFO("2. Checking device presence...");
    if (!eta69631_read_reg(ETA69631_REG_IC_ID, &reg_value))
    {
        APP_LOG_ERROR("ETA69631 not detected on I2C bus");
        APP_LOG_ERROR("Please check:");
        APP_LOG_ERROR("  - I2C connections (SDA/SCL)");
        APP_LOG_ERROR("  - Power supply to ETA69631");
        APP_LOG_ERROR("  - I2C address (0x%02X)", ETA69631_I2C_ADDR);
        app_i2c_deinit(ETA69631_I2C_ID);
        s_eta69631_initialized = false;  /* Reset flag if device not found */
        return false;
    }
    
    APP_LOG_INFO("  ETA69631 detected, IC ID: 0x%02X", reg_value);
    
    /* Initialize GPIO interrupt for CHRG/STDBY status */
    APP_LOG_INFO("3. Initializing interrupt GPIO...");
    if (!eta69631_gpio_int_init())
    {
        APP_LOG_WARNING("Failed to init ETA69631 GPIO interrupt");
        /* Continue anyway, interrupt is optional */
    }
    else
    {
        APP_LOG_INFO("  GPIO interrupt initialized");
    }
    
    /* Initialize GPIOTE for interrupt */
    if (!eta69631_gpiote_init())
    {
        APP_LOG_WARNING("Failed to init ETA69631 GPIOTE");
    }
    
    /* Configure default settings */
    bool success = true;
    
    /* Set input current limit */
    success &= eta69631_set_input_current_limit(ETA69631_DEFAULT_INPUT_CURRENT);
    
    /* Set charge current */
    success &= eta69631_set_charge_current(ETA69631_DEFAULT_CHRG_CURRENT);
    
    /* Set charge voltage */
    success &= eta69631_set_charge_voltage(ETA69631_DEFAULT_CHRG_VOLTAGE);
    
    /* Enable charging */
    success &= eta69631_enable_charging(true);
    
    /* Clear any pending faults */
    eta69631_get_fault(&s_last_fault);
    
    /* Read initial status */
    eta69631_get_status(&s_last_status);
    
    if (success)
    {
        s_eta69631_initialized = true;
        APP_LOG_INFO("4. Configuring default settings...");
        APP_LOG_INFO("  Input current: %dmA", ETA69631_DEFAULT_INPUT_CURRENT);
        APP_LOG_INFO("  Charge current: %dmA", ETA69631_DEFAULT_CHRG_CURRENT);
        APP_LOG_INFO("  Charge voltage: %.2fV", ETA69631_DEFAULT_CHRG_VOLTAGE / 1000.0);
        
        /* Read initial status */
        eta69631_get_status(&s_last_status);
        
        APP_LOG_INFO("=== ETA69631 Initialization Complete ===");
        APP_LOG_INFO("ETA69631 initialized successfully");
        eta69631_print_status();
    }
    else
    {
        APP_LOG_ERROR("=== ETA69631 Initialization Failed ===");
        APP_LOG_ERROR("ETA69631 initialization failed");
        s_eta69631_initialized = false;
    }
    
    return success;
}

void eta69631_deinit(void)
{
    if (!s_eta69631_initialized)
    {
        return;
    }
    
    /* Disable charging before deinit */
    eta69631_enable_charging(false);
    
    /* Deinitialize I2C */
    app_i2c_deinit(ETA69631_I2C_ID);
    
    s_eta69631_initialized = false;
    APP_LOG_INFO("ETA69631 deinitialized");
}

bool eta69631_read_reg(uint8_t reg, uint8_t *p_data)
{
    return eta69631_read_regs(reg, p_data, 1);
}

bool eta69631_write_reg(uint8_t reg, uint8_t data)
{
    return eta69631_write_regs(reg, &data, 1);
}

bool eta69631_update_reg(uint8_t reg, uint8_t mask, uint8_t data)
{
    uint8_t reg_value;
    
    if (!eta69631_read_reg(reg, &reg_value))
    {
        return false;
    }
    
    reg_value = (reg_value & ~mask) | (data & mask);
    
    return eta69631_write_reg(reg, reg_value);
}

bool eta69631_get_status(eta69631_status_t *p_status)
{
    uint8_t reg_value;
    
    if (!p_status)
    {
        return false;
    }
    
    if (!eta69631_read_reg(ETA69631_REG_SYS_STATUS, &reg_value))
    {
        return false;
    }
    
    p_status->vbus_status = reg_value & ETA69631_VBUS_STAT_MASK;
    p_status->chrg_status = reg_value & ETA69631_CHRG_STAT_MASK;
    p_status->pg_stat = (reg_value & ETA69631_PG_STAT) != 0;
    p_status->therm_stat = (reg_value & ETA69631_THERM_STAT) != 0;
    p_status->vsys_stat = (reg_value & ETA69631_VSYS_STAT) != 0;
    p_status->vbat_stat = (reg_value & ETA69631_VBAT_STAT) != 0;
    
    /* Update last status */
    memcpy(&s_last_status, p_status, sizeof(eta69631_status_t));
    
    return true;
}

bool eta69631_get_fault(eta69631_fault_t *p_fault)
{
    uint8_t reg_value;
    
    if (!p_fault)
    {
        return false;
    }
    
    if (!eta69631_read_reg(ETA69631_REG_NEW_FAULT, &reg_value))
    {
        return false;
    }
    
    p_fault->watchdog_fault = (reg_value & ETA69631_FAULT_WATCHDOG) != 0;
    p_fault->boost_fault = (reg_value & ETA69631_FAULT_BOOST) != 0;
    p_fault->chrg_fault = reg_value & ETA69631_FAULT_CHRG_MASK;
    p_fault->bat_fault = reg_value & ETA69631_FAULT_BAT_MASK;
    p_fault->ntc_fault = reg_value & ETA69631_FAULT_NTC_MASK;
    
    /* Update last fault */
    memcpy(&s_last_fault, p_fault, sizeof(eta69631_fault_t));
    
    return true;
}

bool eta69631_get_battery_info(eta69631_battery_info_t *p_info)
{
    uint8_t reg_values[3];
    
    if (!p_info)
    {
        return false;
    }
    
    /* Read battery voltage, system voltage, and charge current registers */
    if (!eta69631_read_regs(ETA69631_REG_BATVOLT, reg_values, 3))
    {
        return false;
    }
    
    p_info->bat_voltage = eta69631_reg_to_bat_voltage(reg_values[0]);
    p_info->sys_voltage = eta69631_reg_to_sys_voltage(reg_values[1]);
    
    /* Read charge current from CHG_CTRL0 register */
    uint8_t chrg_ctrl0;
    if (!eta69631_read_reg(ETA69631_REG_CHG_CTRL0, &chrg_ctrl0))
    {
        return false;
    }
    
    p_info->charge_current = eta69631_reg_to_chrg_current(chrg_ctrl0 & ETA69631_ICHG_MASK);
    
    return true;
}

bool eta69631_set_charge_current(uint16_t current_ma)
{
    uint8_t reg_value;
    
    /* Limit to valid range: 64-5056mA */
    if (current_ma < 64) current_ma = 64;
    if (current_ma > 5056) current_ma = 5056;
    
    /* Convert to register value */
    reg_value = ETA69631_MA_TO_ICHG_REG(current_ma);
    if (reg_value > 0x3F) reg_value = 0x3F;
    
    /* Set charge current (bits 7:2) */
    reg_value <<= 2;
    
    /* Keep other bits unchanged */
    uint8_t current_reg;
    if (!eta69631_read_reg(ETA69631_REG_CHG_CTRL0, &current_reg))
    {
        return false;
    }
    
    current_reg = (current_reg & 0x03) | reg_value;
    
    return eta69631_write_reg(ETA69631_REG_CHG_CTRL0, current_reg);
}

bool eta69631_set_charge_voltage(uint16_t voltage_mv)
{
    uint8_t reg_value;
    
    /* Limit to valid range: 3504-4624mV */
    if (voltage_mv < 3504) voltage_mv = 3504;
    if (voltage_mv > 4624) voltage_mv = 4624;
    
    /* Convert to register value: (Vreg - 3504) / 16 */
    reg_value = (voltage_mv - 3504) / 16;
    if (reg_value > 0x70) reg_value = 0x70;
    
    /* Set charge voltage (bits 7:3) */
    reg_value <<= 3;
    
    /* Keep other bits unchanged */
    uint8_t voltage_reg;
    if (!eta69631_read_reg(ETA69631_REG_CHG_CTRL1, &voltage_reg))
    {
        return false;
    }
    
    voltage_reg = (voltage_reg & 0x07) | reg_value;
    
    return eta69631_write_reg(ETA69631_REG_CHG_CTRL1, voltage_reg);
}

bool eta69631_set_input_current_limit(uint16_t current_ma)
{
    uint8_t reg_value;
    
    /* Limit to valid range: 100-3250mA */
    if (current_ma < 100) current_ma = 100;
    if (current_ma > 3250) current_ma = 3250;
    
    /* Convert to register value: (Iinlim - 100) / 50 */
    reg_value = (current_ma - 100) / 50;
    if (reg_value > 0x3F) reg_value = 0x3F;
    
    /* Set input current limit (bits 2:0) */
    reg_value &= 0x07;
    
    /* Keep other bits unchanged */
    uint8_t input_reg;
    if (!eta69631_read_reg(ETA69631_REG_INPUT_CTRL, &input_reg))
    {
        return false;
    }
    
    input_reg = (input_reg & 0xF8) | reg_value;
    
    return eta69631_write_reg(ETA69631_REG_INPUT_CTRL, input_reg);
}

bool eta69631_enable_charging(bool enable)
{
    uint8_t reg_value;
    
    if (!eta69631_read_reg(ETA69631_REG_PWR_CFG, &reg_value))
    {
        return false;
    }
    
    if (enable)
    {
        reg_value |= ETA69631_CHG_CONFIG;
    }
    else
    {
        reg_value &= ~ETA69631_CHG_CONFIG;
    }
    
    return eta69631_write_reg(ETA69631_REG_PWR_CFG, reg_value);
}

bool eta69631_is_charging_done(void)
{
    eta69631_status_t status;
    
    if (!eta69631_get_status(&status))
    {
        return false;
    }
    
    return (status.chrg_status == ETA69631_CHRG_CHARGE_DONE);
}

bool eta69631_is_power_good(void)
{
    eta69631_status_t status;
    
    if (!eta69631_get_status(&status))
    {
        return false;
    }
    
    return status.pg_stat;
}

const char* eta69631_get_chrg_status_string(void)
{
    switch (s_last_status.chrg_status)
    {
        case ETA69631_CHRG_NOT_CHARGING:
            return "Not Charging";
        case ETA69631_CHRG_PRE_CHARGE:
            return "Pre-Charge";
        case ETA69631_CHRG_FAST_CHARGE:
            return "Fast Charging";
        case ETA69631_CHRG_CHARGE_DONE:
            return "Charge Done";
        default:
            return "Unknown";
    }
}

void eta69631_int_handler(void)
{
    if (s_eta69631_int_triggered)
    {
        s_eta69631_int_triggered = false;
        
        /* Update status */
        eta69631_get_status(&s_last_status);
        
        /* Check for faults */
        eta69631_fault_t fault;
        if (eta69631_get_fault(&fault))
        {
            if (fault.chrg_fault != ETA69631_FAULT_CHRG_NORMAL)
            {
                APP_LOG_WARNING("ETA69631 charge fault: 0x%02X", fault.chrg_fault);
            }
            if (fault.bat_fault != ETA69631_FAULT_BAT_NORMAL)
            {
                APP_LOG_WARNING("ETA69631 battery fault: 0x%02X", fault.bat_fault);
            }
            if (fault.ntc_fault != ETA69631_FAULT_NTC_NORMAL)
            {
                APP_LOG_WARNING("ETA69631 NTC fault: 0x%02X", fault.ntc_fault);
            }
        }
        
        /* Log status change */
        APP_LOG_INFO("ETA69631 status: %s", eta69631_get_chrg_status_string());
    }
}

void eta69631_process(void)
{
    static uint32_t last_update_time = 0;
    static uint8_t update_counter = 0;
    
    /* Process interrupt if triggered */
    eta69631_int_handler();
    
    /* Update status every 10 seconds */
    if (update_counter++ >= 100)  /* 100 * 100ms = 10 seconds */
    {
        update_counter = 0;
        
        eta69631_status_t status;
        if (eta69631_get_status(&status))
        {
            /* Check if status changed */
            if (memcmp(&status, &s_last_status, sizeof(eta69631_status_t)) != 0)
            {
                APP_LOG_INFO("ETA69631 status changed to: %s", eta69631_get_chrg_status_string());
                memcpy(&s_last_status, &status, sizeof(eta69631_status_t));
            }
        }
        
        /* Get battery info every minute */
        if (++last_update_time >= 6)  /* 6 * 10 seconds = 1 minute */
        {
            last_update_time = 0;
            
            eta69631_battery_info_t battery_info;
            if (eta69631_get_battery_info(&battery_info))
            {
                APP_LOG_INFO("Battery: %dmV, System: %dmV, Charge: %dmA",
                           battery_info.bat_voltage,
                           battery_info.sys_voltage,
                           battery_info.charge_current);
            }
        }
    }
}

void eta69631_print_status(void)
{
    eta69631_status_t status;
    eta69631_fault_t fault;
    eta69631_battery_info_t battery_info;
    
    if (!eta69631_get_status(&status))
    {
        APP_LOG_ERROR("Failed to get ETA69631 status");
        return;
    }
    
    eta69631_get_fault(&fault);
    
    APP_LOG_INFO("=== ETA69631 Status ===");
    APP_LOG_INFO("Charging Status: %s", eta69631_get_chrg_status_string());
    APP_LOG_INFO("Power Good: %s", status.pg_stat ? "Yes" : "No");
    APP_LOG_INFO("Thermal Regulation: %s", status.therm_stat ? "Active" : "Inactive");
    APP_LOG_INFO("System Voltage OK: %s", status.vsys_stat ? "Yes" : "No");
    APP_LOG_INFO("Battery Voltage OK: %s", status.vbat_stat ? "Yes" : "No");
    
    /* VBUS status */
    const char* vbus_status = "Unknown";
    switch (status.vbus_status)
    {
        case ETA69631_VBUS_UNKNOWN:
            vbus_status = "Unknown";
            break;
        case ETA69631_VBUS_USB_HOST:
            vbus_status = "USB Host";
            break;
        case ETA69631_VBUS_ADAPTER:
            vbus_status = "Adapter";
            break;
        case ETA69631_VBUS_OTG:
            vbus_status = "OTG";
            break;
    }
    APP_LOG_INFO("VBUS Status: %s", vbus_status);
    
    /* Fault status */
    if (fault.watchdog_fault) APP_LOG_WARNING("Watchdog Fault");
    if (fault.boost_fault) APP_LOG_WARNING("Boost Fault");
    
    if (fault.chrg_fault != ETA69631_FAULT_CHRG_NORMAL)
    {
        APP_LOG_WARNING("Charge Fault: 0x%02X", fault.chrg_fault);
    }
    
    if (fault.bat_fault != ETA69631_FAULT_BAT_NORMAL)
    {
        APP_LOG_WARNING("Battery Fault: 0x%02X", fault.bat_fault);
    }
    
    if (fault.ntc_fault != ETA69631_FAULT_NTC_NORMAL)
    {
        APP_LOG_WARNING("NTC Fault: 0x%02X", fault.ntc_fault);
    }
    
    /* Battery information */
    if (eta69631_get_battery_info(&battery_info))
    {
        APP_LOG_INFO("Battery Voltage: %dmV", battery_info.bat_voltage);
        APP_LOG_INFO("System Voltage: %dmV", battery_info.sys_voltage);
        APP_LOG_INFO("Charge Current: %dmA", battery_info.charge_current);
    }
    
    APP_LOG_INFO("=======================");
}

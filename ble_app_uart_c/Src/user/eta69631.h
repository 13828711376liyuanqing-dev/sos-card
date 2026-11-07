/**
 *****************************************************************************************
 *
 * @file eta69631.h
 *
 * @brief ETA69631 Charging IC Driver Header File.
 *
 *****************************************************************************************
 * @attention
 *  #####Copyright (c) 2024
 *  All rights reserved.
 *
 *  ETA69631 - Single Cell Li-Ion Battery Charger with Power Path Management
 *  I2C Interface: Standard (100kHz) / Fast (400kHz) mode
 *  I2C Address: 0x6A (7-bit) / 0xD4 (write) / 0xD5 (read)
 *
 *****************************************************************************************
 */

#ifndef _ETA69631_H_
#define _ETA69631_H_

#include <stdint.h>
#include <stdbool.h>
#include "app_io.h"
#include "yp001_board_config.h"

/*
 * DEFINES
 *****************************************************************************************
 */

/* I2C Address */
#define ETA69631_I2C_ADDR           YP001_CHARGER_ADDRESS

/* Register Addresses */
#define ETA69631_REG_INPUT_CTRL     0x00    /* Input Source Control */
#define ETA69631_REG_PWR_CFG        0x01    /* Power-On Configuration */
#define ETA69631_REG_CHG_CTRL0      0x02    /* Charge Current Control */
#define ETA69631_REG_CHG_CTRL1      0x03    /* Charge Voltage Control */
#define ETA69631_REG_CHG_CTRL2      0x04    /* Charge Termination/Timer Control */
#define ETA69631_REG_BOOST_CTRL     0x05    /* Boost Voltage/Thermal Regulation */
#define ETA69631_REG_MISC_CTRL      0x06    /* Misc Operation Control */
#define ETA69631_REG_SYS_STATUS     0x07    /* System Status */
#define ETA69631_REG_NEW_FAULT      0x08    /* New Fault Register */
#define ETA69631_REG_VINDPM         0x09    /* VINDPM Settings */
#define ETA69631_REG_BATVOLT        0x0A    /* Battery Voltage Register */
#define ETA69631_REG_SYSVOLT        0x0B    /* System Voltage Register */
#define ETA69631_REG_NTC_STATUS     0x0C    /* NTC Status Register */
#define ETA69631_REG_IC_ID          0x0D    /* IC Identification Register */

/* Input Source Control Register (0x00) */
#define ETA69631_EN_HIZ             0x80    /* Enable HIZ mode */
#define ETA69631_VINDPM_MASK        0x78    /* VINDPM mask */
#define ETA69631_IINLIM_MASK        0x07    /* Input current limit mask */

/* Power-On Configuration Register (0x01) */
#define ETA69631_REG_RESET          0x80    /* Register reset */
#define ETA69631_WD_RESET           0x40    /* Watchdog timer reset */
#define ETA69631_OTG_CONFIG         0x20    /* OTG configuration */
#define ETA69631_CHG_CONFIG         0x10    /* Charger configuration */
#define ETA69631_SYS_MIN_MASK       0x0E    /* Minimum system voltage mask */
#define ETA69631_WD_MASK            0x01    /* Watchdog timer mask */

/* Charge Current Control Register (0x02) */
#define ETA69631_ICHG_MASK          0xFC    /* Charge current mask */
#define ETA69631_HIZ_EN             0x02    /* HIZ enable */
#define ETA69631_EN_TERM            0x01    /* Enable termination */

/* Charge Voltage Control Register (0x03) */
#define ETA69631_VREG_MASK          0xF8    /* Charge voltage mask */
#define ETA69631_BATLOWV            0x04    /* Battery low voltage */
#define ETA69631_VRECHG             0x01    /* Recharge threshold */

/* Charge Termination/Timer Control Register (0x04) */
#define ETA69631_EN_TIMER           0x80    /* Enable charging timer */
#define ETA69631_CHG_TIMER_MASK     0x60    /* Charging timer mask */
#define ETA69631_TMR2X_EN           0x08    /* Timer 2x enable */
#define ETA69631_BATFET_DIS         0x04    /* BATFET disable */
#define ETA69631_JEITA_ISET         0x01    /* JEITA current setting */

/* Boost Voltage/Thermal Regulation Register (0x05) */
#define ETA69631_BOOSTV_MASK        0xF0    /* Boost voltage mask */
#define ETA69631_TREG_MASK          0x03    /* Thermal regulation mask */

/* Misc Operation Control Register (0x06) */
#define ETA69631_INT_MASK_BAT_FAULT 0x80    /* Battery fault interrupt mask */
#define ETA69631_INT_MASK_CHRG_FAULT 0x40   /* Charge fault interrupt mask */
#define ETA69631_OTG_PIN_POL        0x20    /* OTG pin polarity */
#define ETA69631_OTG_PIN_EN         0x10    /* OTG pin enable */
#define ETA69631_INT_MASK_STAT      0x08    /* Status interrupt mask */
#define ETA69631_INT_MASK_OTG       0x04    /* OTG interrupt mask */
#define ETA69631_INT_MASK_IN        0x02    /* Input interrupt mask */
#define ETA69631_INT_MASK_IIN       0x01    /* IIN interrupt mask */

/* System Status Register (0x07) */
#define ETA69631_VBUS_STAT_MASK     0xC0    /* VBUS status mask */
#define ETA69631_CHRG_STAT_MASK     0x30    /* Charging status mask */
#define ETA69631_PG_STAT            0x08    /* Power good status */
#define ETA69631_THERM_STAT         0x04    /* Thermal regulation status */
#define ETA69631_VSYS_STAT          0x02    /* System voltage status */
#define ETA69631_VBAT_STAT          0x01    /* Battery voltage status */

/* Charging Status */
#define ETA69631_CHRG_NOT_CHARGING  0x00
#define ETA69631_CHRG_PRE_CHARGE    0x10
#define ETA69631_CHRG_FAST_CHARGE   0x20
#define ETA69631_CHRG_CHARGE_DONE   0x30

/* VBUS Status */
#define ETA69631_VBUS_UNKNOWN       0x00
#define ETA69631_VBUS_USB_HOST      0x40
#define ETA69631_VBUS_ADAPTER       0x80
#define ETA69631_VBUS_OTG           0xC0

/* New Fault Register (0x08) */
#define ETA69631_FAULT_WATCHDOG     0x80    /* Watchdog fault */
#define ETA69631_FAULT_BOOST        0x40    /* Boost fault */
#define ETA69631_FAULT_CHRG_MASK    0x30    /* Charge fault mask */
#define ETA69631_FAULT_BAT_MASK     0x0C    /* Battery fault mask */
#define ETA69631_FAULT_NTC_MASK     0x03    /* NTC fault mask */

/* Charge Fault */
#define ETA69631_FAULT_CHRG_NORMAL  0x00
#define ETA69631_FAULT_CHRG_INPUT   0x10
#define ETA69631_FAULT_CHRG_THERMAL 0x20
#define ETA69631_FAULT_CHRG_TIMEOUT 0x30

/* Battery Fault */
#define ETA69631_FAULT_BAT_NORMAL   0x00
#define ETA69631_FAULT_BAT_OVP      0x08

/* NTC Fault */
#define ETA69631_FAULT_NTC_NORMAL   0x00
#define ETA69631_FAULT_NTC_COLD     0x01
#define ETA69631_FAULT_NTC_HOT      0x02

#define ETA69631_I2C_SDA_PIN        YP001_CHARGER_SDA_PIN
#define ETA69631_I2C_SCL_PIN        YP001_CHARGER_SCL_PIN
#define ETA69631_INT_PIN            YP001_CHARGER_INT_PIN
#define ETA69631_I2C_SDA_TYPE       YP001_CHARGER_I2C_TYPE
#define ETA69631_I2C_SCL_TYPE       YP001_CHARGER_I2C_TYPE
#define ETA69631_INT_TYPE           YP001_CHARGER_INT_TYPE
#define ETA69631_I2C_ID             APP_I2C_ID_4
#define ETA69631_I2C_SPEED          I2C_SPEED_400K

/*
 * STRUCTURES
 *****************************************************************************************
 */

typedef struct {
    uint8_t vbus_status;        /* VBUS status */
    uint8_t chrg_status;        /* Charging status */
    bool pg_stat;               /* Power good status */
    bool therm_stat;            /* Thermal regulation status */
    bool vsys_stat;             /* System voltage status */
    bool vbat_stat;             /* Battery voltage status */
} eta69631_status_t;

typedef struct {
    uint8_t chrg_fault;         /* Charge fault */
    uint8_t bat_fault;          /* Battery fault */
    uint8_t ntc_fault;          /* NTC fault */
    bool watchdog_fault;        /* Watchdog fault */
    bool boost_fault;           /* Boost fault */
} eta69631_fault_t;

typedef struct {
    uint16_t bat_voltage;       /* Battery voltage in mV */
    uint16_t sys_voltage;       /* System voltage in mV */
    uint16_t charge_current;    /* Charge current in mA */
} eta69631_battery_info_t;

/*
 * GLOBAL FUNCTION DECLARATION
 *****************************************************************************************
 */

/**
 *****************************************************************************************
 * @brief Initialize ETA69631 charging IC.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_init(void);

/**
 *****************************************************************************************
 * @brief Deinitialize ETA69631 charging IC.
 *****************************************************************************************
 */
void eta69631_deinit(void);

/**
 *****************************************************************************************
 * @brief Read a register from ETA69631.
 * @param[in] reg: Register address.
 * @param[out] p_data: Pointer to store read data.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_read_reg(uint8_t reg, uint8_t *p_data);

/**
 *****************************************************************************************
 * @brief Write a register to ETA69631.
 * @param[in] reg: Register address.
 * @param[in] data: Data to write.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_write_reg(uint8_t reg, uint8_t data);

/**
 *****************************************************************************************
 * @brief Update a register with mask.
 * @param[in] reg: Register address.
 * @param[in] mask: Mask for bits to update.
 * @param[in] data: Data to write.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_update_reg(uint8_t reg, uint8_t mask, uint8_t data);

/**
 *****************************************************************************************
 * @brief Get system status.
 * @param[out] p_status: Pointer to status structure.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_get_status(eta69631_status_t *p_status);

/**
 *****************************************************************************************
 * @brief Get fault status.
 * @param[out] p_fault: Pointer to fault structure.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_get_fault(eta69631_fault_t *p_fault);

/**
 *****************************************************************************************
 * @brief Get battery information.
 * @param[out] p_info: Pointer to battery info structure.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_get_battery_info(eta69631_battery_info_t *p_info);

/**
 *****************************************************************************************
 * @brief Set charge current.
 * @param[in] current_ma: Charge current in mA (0-5056mA).
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_set_charge_current(uint16_t current_ma);

/**
 *****************************************************************************************
 * @brief Set charge voltage.
 * @param[in] voltage_mv: Charge voltage in mV (3504-4624mV).
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_set_charge_voltage(uint16_t voltage_mv);

/**
 *****************************************************************************************
 * @brief Set input current limit.
 * @param[in] current_ma: Input current limit in mA (100-3250mA).
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_set_input_current_limit(uint16_t current_ma);

/**
 *****************************************************************************************
 * @brief Enable or disable charging.
 * @param[in] enable: true to enable, false to disable.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
bool eta69631_enable_charging(bool enable);

/**
 *****************************************************************************************
 * @brief Check if charging is complete.
 * @return true if charging is done, false otherwise.
 *****************************************************************************************
 */
bool eta69631_is_charging_done(void);

/**
 *****************************************************************************************
 * @brief Check if power is good.
 * @return true if power good, false otherwise.
 *****************************************************************************************
 */
bool eta69631_is_power_good(void);

/**
 *****************************************************************************************
 * @brief Get charging status string.
 * @return String description of charging status.
 *****************************************************************************************
 */
const char* eta69631_get_chrg_status_string(void);

/**
 *****************************************************************************************
 * @brief Handle ETA69631 interrupt.
 * Call this function when INT pin triggers.
 *****************************************************************************************
 */
void eta69631_int_handler(void);

/**
 *****************************************************************************************
 * @brief Process ETA69631 in main loop.
 * Call this function periodically (e.g., every 100ms).
 *****************************************************************************************
 */
void eta69631_process(void);

/**
 *****************************************************************************************
 * @brief Print ETA69631 status information.
 *****************************************************************************************
 */
void eta69631_print_status(void);

#endif /* _ETA69631_H_ */

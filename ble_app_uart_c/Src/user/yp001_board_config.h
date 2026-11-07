#ifndef YP001_BOARD_CONFIG_H
#define YP001_BOARD_CONFIG_H

#include "app_io.h"

/* YP001_MB_SCH_A1_20260909, GR5526RGNIP/QFN68 board pin map. */
#define YP001_GPIO_GPIO_MUX          APP_IO_MUX_7
#define YP001_AON_GPIO_MUX           APP_IO_MUX_7
#define YP001_I2C_MUX_I2C4           APP_IO_MUX_0
#define YP001_I2C_MUX_I2C3           APP_IO_MUX_2

/* SAM | 2026-10-08 12:50 +08:00 | Drive U10 EN from GPIO9 because the
 * 20260911 schematic connects GPIO9/QFN13 to LDO_EN2 via R72. */
#define YP001_1V8_POWER_TYPE         APP_IO_TYPE_GPIOA
#define YP001_1V8_POWER_PIN          APP_IO_PIN_9

#define YP001_CAT1_POWER_TYPE        APP_IO_TYPE_GPIOA
#define YP001_CAT1_POWER_PIN         APP_IO_PIN_6  /* GPIO6 / pin 10 */
#define YP001_CAT1_POWER_ON          APP_IO_PIN_SET   /* Q1201 pulls Q2 gate low */
#define YP001_CAT1_POWER_OFF         APP_IO_PIN_RESET
#define YP001_CAT1_KEY_TYPE          APP_IO_TYPE_AON
#define YP001_CAT1_KEY_PIN           APP_IO_PIN_0  /* AON_GPIO0 / pin 38 */
#define YP001_CAT1_KEY_ASSERT        APP_IO_PIN_SET   /* Q4 inverts MCU to PWRKEY */
#define YP001_CAT1_KEY_RELEASE       APP_IO_PIN_RESET
/* gr55xx_hal_aon_gpio_ex.h: AON_GPIO_PIN2/3_MUX_UART4_TX/RX. */
#define YP001_CAT1_UART_HW_SUPPORTED 1
#define YP001_CAT1_UART_TYPE         APP_IO_TYPE_AON
#define YP001_CAT1_UART_TX_PIN       APP_IO_PIN_2  /* AON_GPIO2 / QFN40 */
#define YP001_CAT1_UART_RX_PIN       APP_IO_PIN_3  /* AON_GPIO3 / QFN41 */
#define YP001_CAT1_UART_MUX          APP_IO_MUX_0
/* SAM | 2026-10-10 18:07 +08:00 | Match Air780EGH UART1 for manual AT after USB flashing; no boot probe. */
#define YP001_CAT1_UART_BAUDRATE     460800U
#define YP001_DEBUG_UART_TYPE        APP_IO_TYPE_GPIOB
#define YP001_DEBUG_UART_TX_PIN      APP_IO_PIN_12 /* GPIO28 / QFN59, UART0 MUX2 */
#define YP001_DEBUG_UART_RX_PIN      APP_IO_PIN_13 /* GPIO29 / QFN60, UART0 MUX2 */
#define YP001_DEBUG_UART_MUX         APP_IO_MUX_2
#define YP001_DEBUG_UART_BAUDRATE    115200U

#define YP001_CHARGER_I2C_TYPE       APP_IO_TYPE_GPIOA
#define YP001_CHARGER_SCL_PIN        APP_IO_PIN_4  /* GPIO4 / pin 8, I2C4 */
#define YP001_CHARGER_SDA_PIN        APP_IO_PIN_5  /* GPIO5 / pin 9, I2C4 */
#define YP001_CHARGER_SCL_MUX        APP_IO_MUX_0
#define YP001_CHARGER_SDA_MUX        APP_IO_MUX_0
#define YP001_CHARGER_INT_TYPE       APP_IO_TYPE_AON
#define YP001_CHARGER_INT_PIN        APP_IO_PIN_5  /* AON_GPIO5 / pin 43 */

#define YP001_SENSOR_I2C_TYPE        APP_IO_TYPE_GPIOA
#define YP001_SENSOR_SCL_PIN         APP_IO_PIN_2  /* GPIO2 / pin 6, I2C0 */
#define YP001_SENSOR_SDA_PIN         APP_IO_PIN_3  /* GPIO3 / pin 7, I2C0 */
#define YP001_SENSOR_SCL_MUX         APP_IO_MUX_0
#define YP001_SENSOR_SDA_MUX         APP_IO_MUX_0
#define YP001_SENSOR_POWER_TYPE      APP_IO_TYPE_GPIOA
#define YP001_SENSOR_POWER_PIN       APP_IO_PIN_7  /* GPIO7 / pin 11 */
#define YP001_SENSOR_INT_TYPE        APP_IO_TYPE_AON
#define YP001_SENSOR_INT_PIN         APP_IO_PIN_7  /* AON_GPIO7 / pin 45 */

#define YP001_BATTERY_ADC_TYPE       APP_IO_TYPE_MSIO
#define YP001_BATTERY_ADC_PIN        APP_IO_PIN_1  /* MSIO_A1 / pin 36 */
#define YP001_BATTERY_SWITCH_TYPE    APP_IO_TYPE_GPIOB
#define YP001_BATTERY_SWITCH_PIN     APP_IO_PIN_7  /* GPIO23 / pin 54 */
#define YP001_CHARGER_NQON_TYPE      APP_IO_TYPE_GPIOB
#define YP001_CHARGER_NQON_PIN       APP_IO_PIN_4  /* GPIO20 / pin 51 */
#define YP001_CHARGER_NQON_ACTIVE    APP_IO_PIN_RESET
#define YP001_CHARGER_STAT_TYPE      APP_IO_TYPE_GPIOB
#define YP001_CHARGER_STAT_PIN       APP_IO_PIN_5  /* GPIO21 / pin 52 */
/* SAM | 2026-10-09 12:02 +08:00 | Use 7-bit 0x6B because ETA69631 V1.9
 * pp.21-22 specifies 8-bit write address 0xD6; J-Link read REG0B=0x3F. */
#define YP001_CHARGER_ADDRESS        0x6BU

#define YP001_LCD_POWER_TYPE         APP_IO_TYPE_GPIOA
#define YP001_LCD_POWER_PIN          APP_IO_PIN_10 /* GPIO10 / pin 14 */
#define YP001_LCD_BUSY_TYPE          APP_IO_TYPE_GPIOB
#define YP001_LCD_BUSY_PIN           APP_IO_PIN_8  /* GPIO24 / pin 55 */
#define YP001_LCD_RESET_TYPE         APP_IO_TYPE_GPIOB
#define YP001_LCD_RESET_PIN          APP_IO_PIN_9  /* GPIO25 / pin 56 */
#define YP001_LCD_DATA_TYPE          APP_IO_TYPE_GPIOB
#define YP001_LCD_DATA_PIN           APP_IO_PIN_14 /* GPIO30 / pin 61 */
#define YP001_LCD_CLK_TYPE           APP_IO_TYPE_GPIOB
#define YP001_LCD_CLK_PIN            APP_IO_PIN_15 /* GPIO31 / pin 62 */
#define YP001_LCD_RS_TYPE            APP_IO_TYPE_GPIOC
#define YP001_LCD_RS_PIN             APP_IO_PIN_0  /* GPIO32 / pin 63 */
#define YP001_LCD_CS_TYPE            APP_IO_TYPE_GPIOC
#define YP001_LCD_CS_PIN             APP_IO_PIN_1  /* GPIO33 / pin 64 */

#define YP001_MOTOR_POWER_TYPE       APP_IO_TYPE_GPIOB
#define YP001_MOTOR_I2C_TYPE         APP_IO_TYPE_GPIOA
#define YP001_MOTOR_SCL_PIN          APP_IO_PIN_11 /* GPIO11 / pin 16, I2C3 */
#define YP001_MOTOR_SDA_PIN          APP_IO_PIN_12 /* GPIO12 / pin 17, I2C3 */
#define YP001_MOTOR_I2C_MUX          YP001_I2C_MUX_I2C3
#define YP001_MOTOR_POWER_PIN        APP_IO_PIN_10 /* GPIO26 / pin 57 */
#define YP001_MOTOR_RESET_TYPE       APP_IO_TYPE_GPIOB
#define YP001_MOTOR_RESET_PIN        APP_IO_PIN_11 /* GPIO27 / pin 58 */
#define YP001_MOTOR_INT_TYPE         APP_IO_TYPE_AON
#define YP001_MOTOR_INT_PIN          APP_IO_PIN_6  /* AON_GPIO6 / pin 44 */

#define YP001_KEY1_TYPE              APP_IO_TYPE_AON
#define YP001_KEY1_PIN               APP_IO_PIN_1  /* AON_GPIO1 / pin 39 */
#define YP001_KEY2_TYPE              APP_IO_TYPE_AON
#define YP001_KEY2_PIN               APP_IO_PIN_4  /* AON_GPIO4 / pin 42 */

#define YP001_LED_RED_TYPE           APP_IO_TYPE_MSIO
#define YP001_LED_RED_PIN            APP_IO_PIN_3  /* MSIO_A3 / pin 34 */
#define YP001_LED_GREEN_TYPE         APP_IO_TYPE_MSIO
#define YP001_LED_GREEN_PIN          APP_IO_PIN_0  /* MSIO_A0 / pin 37 */
#define YP001_LED_BLUE_TYPE          APP_IO_TYPE_MSIO
#define YP001_LED_BLUE_PIN           APP_IO_PIN_2  /* MSIO_A2 / pin 35 */

#endif /* YP001_BOARD_CONFIG_H */

/* SAM | 2026-10-12 19:23 +08:00 | Preserve OTA power during boot and manual diagnostics because unknown installs must not be interrupted. */
#include "ota/yp001_ota.h"
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
#include "yp001_board_config.h"

volatile uint8_t sos_press = 0;

void app_io_event_handler(app_io_evt_t *p_evt);

const app_gpiote_param_t gpiote_param[] =
    {
    {YP001_KEY1_TYPE, YP001_KEY1_PIN, APP_IO_MODE_IT_FALLING, APP_IO_PULLUP, app_io_event_handler},
    {YP001_KEY2_TYPE, YP001_KEY2_PIN, APP_IO_MODE_IT_FALLING, APP_IO_PULLUP, app_io_event_handler},
};

void app_io_event_handler(app_io_evt_t *p_evt)
{
  app_io_pin_state_t pin_level = APP_IO_PIN_RESET;

  if ((p_evt->type == YP001_KEY1_TYPE && p_evt->pin == YP001_KEY1_PIN) ||
      (p_evt->type == YP001_KEY2_TYPE && p_evt->pin == YP001_KEY2_PIN))
  {
    sos_press = 1;
  }
}

#define LED1_ON() app_io_write_pin(YP001_LED_RED_TYPE, YP001_LED_RED_PIN, APP_IO_PIN_RESET)
#define LED1_OFF() app_io_write_pin(YP001_LED_RED_TYPE, YP001_LED_RED_PIN, APP_IO_PIN_SET)
#define LED2_ON() app_io_write_pin(YP001_LED_GREEN_TYPE, YP001_LED_GREEN_PIN, APP_IO_PIN_RESET)
#define LED2_OFF() app_io_write_pin(YP001_LED_GREEN_TYPE, YP001_LED_GREEN_PIN, APP_IO_PIN_SET)
#define LED3_ON() app_io_write_pin(YP001_LED_BLUE_TYPE, YP001_LED_BLUE_PIN, APP_IO_PIN_RESET)
#define LED3_OFF() app_io_write_pin(YP001_LED_BLUE_TYPE, YP001_LED_BLUE_PIN, APP_IO_PIN_SET)

void gpio_init(void)
{

  uint16_t ret;
  app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;
  app_io_pin_state_t pin_val;

  /* SAM | 2026-10-08 12:50 +08:00 | Keep GPIO9/LDO_EN2 high after boot
   * because U10 must supply 1.8 V before I2C; verify the rail on hardware. */
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_1V8_POWER_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_1V8_POWER_TYPE, &io_init);
  if (ret == APP_DRV_SUCCESS) {
    app_io_write_pin(YP001_1V8_POWER_TYPE, YP001_1V8_POWER_PIN, APP_IO_PIN_SET);
    delay_ms(10);
  }
  printf("[BOOT] GPIO9 LDO_EN2 requested HIGH, init=0x%04X\r\n", ret);

  // Sensor rail enable is active high; keep it off until the DA221 rail is checked.
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_SENSOR_POWER_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_SENSOR_POWER_TYPE, &io_init);

  app_io_write_pin(YP001_SENSOR_POWER_TYPE, YP001_SENSOR_POWER_PIN, APP_IO_PIN_RESET);

  // LCD_VCI_EN: GPIO10 drives U1005 EN through R84; keep the rail enabled.
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_LCD_POWER_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_LCD_POWER_TYPE, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LCD GPIO10 init failed: 0x%04X\r\n", ret);
  }
  else
  {
    app_io_write_pin(YP001_LCD_POWER_TYPE, YP001_LCD_POWER_PIN, APP_IO_PIN_SET);
  }

  // LED1 (MSIO_A3)
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_LED_RED_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_LED_RED_TYPE, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LED1 init failed.\r\n");
  }
  LED1_OFF();  // 初始关闭

  // LED2 (MSIO_A0)
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_LED_GREEN_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_LED_GREEN_TYPE, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LED2 init failed.\r\n");
  }
  LED2_OFF();  // 初始关闭

  // LED3 (MSIO_A2)
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_LED_BLUE_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_LED_BLUE_TYPE, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LED3 init failed.\r\n");
  }
  LED3_OFF();  // 初始关闭

  printf("LED init done\r\n");

  /* SAM | 2026-10-12 19:28 +08:00 | Skip GPIO reinitialization too because output setup can disturb installation power. */
  if (yp001_ota_power_change_allowed()) {
  // Air780EGH rail control: GPIO6 / VCC_4V2_4G_EN.
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_CAT1_POWER_PIN;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  ret = app_io_init(YP001_CAT1_POWER_TYPE, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("APP_GPIO_PIN1 init failed.\r\n");
  }
  /* GPIO6 high enables CAT1; VBUS may independently keep the rail on. */
  if (yp001_ota_power_change_allowed())
    app_io_write_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN, YP001_CAT1_POWER_OFF);


  }
  // powerkey
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = YP001_CAT1_KEY_PIN;
  io_init.mux = YP001_AON_GPIO_MUX;
  ret = app_io_init(APP_IO_TYPE_AON, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("APP_GPIO_PIN1 init failed.\r\n");
  }
  app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_RELEASE);

  // ETA69631 NQON is active low; leave charger configuration disabled at boot.
  io_init.pin = YP001_CHARGER_NQON_PIN;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pull = APP_IO_NOPULL;
  io_init.mux = YP001_GPIO_GPIO_MUX;
  app_io_init(YP001_CHARGER_NQON_TYPE, &io_init);
  app_io_write_pin(YP001_CHARGER_NQON_TYPE, YP001_CHARGER_NQON_PIN, APP_IO_PIN_SET);

  // SOS key S1.
  /* Keys are registered once by APP_KEY_INIT_Jkb after QP objects start. */
}

// 流水灯
void gpio_blink(void)
{
  static uint8_t state = 0;
  static uint8_t cnt = 0;

  if (cnt++ < 10)
  {
    return;
  }
  cnt = 0;
  switch (state)
  {
  case 0:
    LED1_ON();
    LED2_OFF();
    LED3_OFF();
    state = 1;
    break;
  case 1:
    LED1_OFF();
    LED2_ON();
    LED3_OFF();
    state = 2;
    break;
  case 2:
    LED1_OFF();
    LED2_OFF();
    LED3_ON();
    state = 0;
    break;
  default:
    break;
  }
}



static int cmd_cat1_power(int argc, char *argv[])
{
    if (!yp001_ota_power_change_allowed()) { printf("[OTA] power change denied\r\n"); return -1; }
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;

    if (argc < 2) 
    {
        printf("Usage: cat1_power [on|off|reset]\r\n");
        return -1;
    }

    /* ---------- OFF 操作 ---------- */
    if (strcmp(argv[1], "off") == 0) 
    {
        io_init.pin = YP001_CAT1_POWER_PIN;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_NOPULL;
        app_io_init(YP001_CAT1_POWER_TYPE, &io_init);
        if (yp001_ota_power_change_allowed())
    app_io_write_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN, YP001_CAT1_POWER_OFF);
        printf("CAT1 power OFF\r\n");
    }
    /* ---------- ON 操作 ---------- */
    else if (strcmp(argv[1], "on") == 0) 
    {
        io_init.pin = YP001_CAT1_POWER_PIN;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_NOPULL;
        app_io_init(YP001_CAT1_POWER_TYPE, &io_init);
        app_io_write_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN, YP001_CAT1_POWER_ON);

        /* AON 复位脉冲（保持原有时序） */
        io_init.pull = APP_IO_NOPULL;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pin = YP001_CAT1_KEY_PIN;
        io_init.mux = YP001_GPIO_GPIO_MUX;
        uint16_t ret = app_io_init(APP_IO_TYPE_AON, &io_init);
        if (ret != APP_DRV_SUCCESS)
        {
            printf("APP_GPIO_PIN1 init failed.\r\n");
        }
        app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_RELEASE);
        delay_ms(200);
        app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_ASSERT);
        delay_ms(1600);
        app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_RELEASE);
        printf("CAT1 power ON\r\n");
    }
    /* ---------- RESET 操作（新增） ---------- */
    else if (strcmp(argv[1], "reset") == 0) 
    {
        // 1. 执行下电（OFF 逻辑）
        io_init.pin = YP001_CAT1_POWER_PIN;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_NOPULL;
        app_io_init(YP001_CAT1_POWER_TYPE, &io_init);
        if (yp001_ota_power_change_allowed())
    app_io_write_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN, YP001_CAT1_POWER_OFF);
        printf("CAT1 power OFF (for reset)\r\n");

        // 2. 等待电源完全放电（根据模块手册调整延时）
        delay_ms(500);

        // 3. 执行上电（ON 逻辑）
        io_init.pin = YP001_CAT1_POWER_PIN;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_NOPULL;
        app_io_init(YP001_CAT1_POWER_TYPE, &io_init);
        app_io_write_pin(YP001_CAT1_POWER_TYPE, YP001_CAT1_POWER_PIN, YP001_CAT1_POWER_ON);

        io_init.pull = APP_IO_NOPULL;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pin = YP001_CAT1_KEY_PIN;
        io_init.mux = YP001_GPIO_GPIO_MUX;
        uint16_t ret = app_io_init(APP_IO_TYPE_AON, &io_init);
        if (ret != APP_DRV_SUCCESS)
        {
            printf("APP_GPIO_PIN1 init failed.\r\n");
        }
        app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_RELEASE);
        delay_ms(200);
        app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_ASSERT);
        delay_ms(1600);
        app_io_write_pin(YP001_CAT1_KEY_TYPE, YP001_CAT1_KEY_PIN, YP001_CAT1_KEY_RELEASE);
        printf("CAT1 power RESET complete\r\n");
    }
    else 
    {
        printf("Invalid argument. Usage: cat1_power [on|off|reset]\r\n");
        return -1;
    }
    
    return 0;
}

/* 更新注册命令描述，包含 reset 选项 */
//CLI_CMD_REGISTER("cat1_power", "cat1_power [on|off|reset]", cmd_cat1_power);

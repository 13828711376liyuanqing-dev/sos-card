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

volatile uint8_t sos_press = 0;

void app_io_event_handler(app_io_evt_t *p_evt);

const app_gpiote_param_t gpiote_param[] =
    {
        {APP_IO_TYPE_AON, APP_IO_PIN_1, APP_IO_MODE_IT_FALLING, APP_IO_PULLUP, app_io_event_handler},
};

void app_io_event_handler(app_io_evt_t *p_evt)
{
  app_io_pin_state_t pin_level = APP_IO_PIN_RESET;

  if (p_evt->pin == APP_IO_PIN_1)
  {
    sos_press = 1;
  }
}

#define LED1_ON() app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_3, APP_IO_PIN_RESET)
#define LED1_OFF() app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_3, APP_IO_PIN_SET)
#define LED2_ON() app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_4, APP_IO_PIN_RESET)
#define LED2_OFF() app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_4, APP_IO_PIN_SET)
#define LED3_ON() app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_2, APP_IO_PIN_RESET)
#define LED3_OFF() app_io_write_pin(APP_IO_TYPE_MSIO, APP_IO_PIN_2, APP_IO_PIN_SET)

void gpio_init(void)
{

  uint16_t ret;
  app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;
  app_io_pin_state_t pin_val;

  // LDO_EN2
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_0;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_GPIOB, &io_init);

  app_io_write_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_0, APP_IO_PIN_SET);

  // LDO_EN3
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_1;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_GPIOB, &io_init);

  app_io_write_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_1, APP_IO_PIN_SET);

  // LED1 (MSIO3)
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_3;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_MSIO, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LED1 init failed.\r\n");
  }
  LED1_OFF();  // 初始关闭

  // LED2 (MSIO4)
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_4;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_MSIO, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LED2 init failed.\r\n");
  }
  LED2_OFF();  // 初始关闭

  // LED3 (MSIO2)
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_2;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_MSIO, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("LED3 init failed.\r\n");
  }
  LED3_OFF();  // 初始关闭

  printf("LED init done\r\n");

  // 4G LDO  VCC_4V2_4G_EN
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_2;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_GPIOB, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("APP_GPIO_PIN1 init failed.\r\n");
  }
  app_io_write_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_2, APP_IO_PIN_SET);


  // powerkey
  io_init.pull = APP_IO_NOPULL;
  io_init.mode = APP_IO_MODE_OUTPUT;
  io_init.pin = APP_IO_PIN_0;
  io_init.mux = APP_IO_MUX;
  ret = app_io_init(APP_IO_TYPE_AON, &io_init);
  if (ret != APP_DRV_SUCCESS)
  {
    printf("APP_GPIO_PIN1 init failed.\r\n");
  }
  app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_SET);

  // sos key
  app_gpiote_init(gpiote_param, sizeof(gpiote_param) / sizeof(app_gpiote_param_t));
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
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;

    if (argc < 2) 
    {
        printf("Usage: cat1_power [on|off|reset]\r\n");
        return -1;
    }

    /* ---------- OFF 操作 ---------- */
    if (strcmp(argv[1], "off") == 0) 
    {
        io_init.pin = GPIO_PIN_2;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_PULLDOWN;
        app_io_init(APP_IO_TYPE_GPIOB, &io_init);
        app_io_write_pin(APP_IO_TYPE_GPIOB, GPIO_PIN_2, APP_IO_PIN_RESET);
        printf("CAT1 power OFF\r\n");
    }
    /* ---------- ON 操作 ---------- */
    else if (strcmp(argv[1], "on") == 0) 
    {
        io_init.pin = GPIO_PIN_2;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_PULLUP;
        app_io_init(APP_IO_TYPE_GPIOB, &io_init);
        app_io_write_pin(APP_IO_TYPE_GPIOB, GPIO_PIN_2, APP_IO_PIN_SET);

        /* AON 复位脉冲（保持原有时序） */
        io_init.pull = APP_IO_NOPULL;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pin = APP_IO_PIN_0;
        io_init.mux = APP_IO_MUX;
        uint16_t ret = app_io_init(APP_IO_TYPE_AON, &io_init);
        if (ret != APP_DRV_SUCCESS)
        {
            printf("APP_GPIO_PIN1 init failed.\r\n");
        }
        app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_SET);
        delay_ms(200);
        app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_RESET);
        delay_ms(200);
        app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_SET);
        printf("CAT1 power ON\r\n");
    }
    /* ---------- RESET 操作（新增） ---------- */
    else if (strcmp(argv[1], "reset") == 0) 
    {
        // 1. 执行下电（OFF 逻辑）
        io_init.pin = GPIO_PIN_2;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_PULLDOWN;
        app_io_init(APP_IO_TYPE_GPIOB, &io_init);
        app_io_write_pin(APP_IO_TYPE_GPIOB, GPIO_PIN_2, APP_IO_PIN_RESET);
        printf("CAT1 power OFF (for reset)\r\n");

        // 2. 等待电源完全放电（根据模块手册调整延时）
        delay_ms(500);

        // 3. 执行上电（ON 逻辑）
        io_init.pin = GPIO_PIN_2;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pull = APP_IO_PULLUP;
        app_io_init(APP_IO_TYPE_GPIOB, &io_init);
        app_io_write_pin(APP_IO_TYPE_GPIOB, GPIO_PIN_2, APP_IO_PIN_SET);

        io_init.pull = APP_IO_NOPULL;
        io_init.mode = APP_IO_MODE_OUTPUT;
        io_init.pin = APP_IO_PIN_0;
        io_init.mux = APP_IO_MUX;
        uint16_t ret = app_io_init(APP_IO_TYPE_AON, &io_init);
        if (ret != APP_DRV_SUCCESS)
        {
            printf("APP_GPIO_PIN1 init failed.\r\n");
        }
        app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_SET);
        delay_ms(200);
        app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_RESET);
        delay_ms(200);
        app_io_write_pin(APP_IO_TYPE_AON, APP_IO_PIN_0, APP_IO_PIN_SET);
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
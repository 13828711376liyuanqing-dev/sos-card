//#include "user_app.h"
//#include "user_periph_setup.h"
//#include "transport_scheduler.h"
//#include "gr_includes.h"
//#include "scatter_common.h"
//#include "flash_scatter_config.h"
//#include "patch.h"
//#include "app_log.h"
//#include "app_io.h"
//#include "app_i2c.h"
//#include "app_gpiote.h"
//#include "board_SK.h"

//#define TEST_I2C_0 1

//#if TEST_I2C_0 == 1

//#define I2C_SDA_GPIO_TYPE APP_IO_TYPE_GPIOA
//#define I2C_SDA_GPIO_PIN APP_IO_PIN_3
//#define I2C_SDA_GPIO_MUX APP_IO_MUX_0

//#define I2C_SCL_GPIO_TYPE APP_IO_TYPE_GPIOA
//#define I2C_SCL_GPIO_PIN APP_IO_PIN_2
//#define I2C_SCL_GPIO_MUX APP_IO_MUX_0

//#define I2C_ID APP_I2C_ID_0

//#else

//#define I2C_SDA_GPIO_TYPE APP_IO_TYPE_GPIOA
//#define I2C_SDA_GPIO_PIN APP_IO_PIN_7
//#define I2C_SDA_GPIO_MUX APP_IO_MUX_0

//#define I2C_SCL_GPIO_TYPE APP_IO_TYPE_GPIOA
//#define I2C_SCL_GPIO_PIN APP_IO_PIN_6
//#define I2C_SCL_GPIO_MUX APP_IO_MUX_0

//#define I2C_ID APP_I2C_ID_3

//#endif

//static app_i2c_params_t da221_params = {
//    .id = I2C_ID,
//    .role = APP_I2C_ROLE_MASTER,
//    .pin_cfg = {
//        .scl = {
//            .type = I2C_SCL_GPIO_TYPE,
//            .mux = I2C_SCL_GPIO_MUX,
//            .pin = I2C_SCL_GPIO_PIN,
//            .pull = APP_IO_PULLUP,
//        },
//        .sda = {
//            .type = I2C_SDA_GPIO_TYPE,
//            .mux = I2C_SDA_GPIO_MUX,
//            .pin = I2C_SDA_GPIO_PIN,
//            .pull = APP_IO_PULLUP,
//        },
//    },
//    .dma_cfg = {
//#if (APP_DRIVER_CHIP_TYPE == APP_DRIVER_GR5332X) || (APP_DRIVER_CHIP_TYPE == APP_DRIVER_GR551X)
//        .tx_dma_instance = DMA0,
//        .rx_dma_instance = DMA0,
//#else
//        .tx_dma_instance = DMA1,
//        .rx_dma_instance = DMA1,
//#endif
//        .tx_dma_channel = DMA_Channel0,
//        .rx_dma_channel = DMA_Channel1,
//    },
//    .init = {
//        .speed = I2C_SPEED_100K,
//        .own_address = 0x00,
//        .addressing_mode = I2C_ADDRESSINGMODE_7BIT,
//        .general_call_mode = I2C_GENERALCALL_DISABLE,
//    },
//};

//uint8_t da221Addr = 0x27;
//uint8_t soft_reset[] = {0x00, 0x24};   // 软件复位地址
//uint8_t chipid_addr[] = {0x01};        // 芯片ID地址
//uint8_t rangeaddr[] = {0x0f, 0x00};    // 设置加速度量程，默认2g
//uint8_t int_set1_reg[] = {0x16, 0x87}; // 设置x,y,z发生变化时，产生中断
//uint8_t int_set2_reg[] = {0x17, 0x10}; // 使能新数据中断，数据变化时，产生中断，本程序不设置
//uint8_t int_map1_reg[] = {0x19, 0x04}; // 运动的时候，产生中断
//uint8_t int_map2_reg[] = {0x1a, 0x01};

//uint8_t active_dur_addr[] = {0x27, 0x01}; // 设置激活时间，默认0x01
//uint8_t active_ths_addr[] = {0x28, 0x33}; // 设置激活阈值，灵敏度最高
//uint8_t odr_addr[] = {0x10, 0x08};        // 设置采样率 100Hz
//uint8_t mode_addr[] = {0x11, 0x00};       // 设置正常模式
//uint8_t int_latch_addr[] = {0x21, 0x01};  // 设置中断锁存

//uint8_t x_lsb_reg[] = {0x02}; // X轴LSB寄存器地址
//uint8_t x_msb_reg[] = {0x03}; // X轴MSB寄存器地址
//uint8_t y_lsb_reg[] = {0x04}; // Y轴LSB寄存器地址
//uint8_t y_msb_reg[] = {0x05}; // Y轴MSB寄存器地址
//uint8_t z_lsb_reg[] = {0x06}; // Z轴LSB寄存器地址
//uint8_t z_msb_reg[] = {0x07}; // Z轴MSB寄存器地址

//uint8_t x_accel;
//uint8_t y_accel;
//uint8_t z_accel;

//uint16_t i2c_write(uint8_t *data, uint8_t len)
//{
//    uint16_t ret = 0;
//    ret = app_i2c_transmit_sync(I2C_ID, da221Addr, data, len, 50);
//    return ret;
//}

//uint16_t i2c_read(uint8_t *buffer, uint16_t len)
//{
//    uint16_t ret = 0;
//    ret = app_i2c_receive_sync(I2C_ID, da221Addr, buffer, len, 50);
//    return ret;
//}

//volatile uint8_t da221_int = 0;

//static void app_io_event_handler(app_io_evt_t *p_evt)
//{
//    app_io_pin_state_t pin_level = APP_IO_PIN_RESET;

//    if (p_evt->pin == APP_IO_PIN_3)
//    {
//        printf("DA221 interrupt triggered\r\n");
//        da221_int = 1;
//    }
//}

//const app_gpiote_param_t gpiote_param_da221[] =
//{
//    {APP_IO_TYPE_GPIOB, APP_IO_PIN_3, APP_IO_MODE_IT_RISING, APP_IO_PULLDOWN, app_io_event_handler},
//};

//uint8_t da221_init(void)
//{
//    app_i2c_init(&da221_params, NULL);
//    uint16_t i2c_ret = 0;
//    i2c_ret = i2c_write(soft_reset, 2);
//    delay_ms(50);
//    // 读id
//    i2c_ret = i2c_write(chipid_addr, 1);
//    delay_ms(50);
//    uint8_t buf[10] = {0};
//    i2c_read(buf, 1);

//    printf("DA221 Chip ID: 0x%02x\r\n", buf[0]);
//    if (buf[0] != 0x13)
//    {
//        printf("DA221 chip ID mismatch\r\n");
//        return 1;
//    }

//    app_gpiote_init(gpiote_param_da221, sizeof(gpiote_param_da221) / sizeof(app_gpiote_param_t));

//    i2c_write(rangeaddr, 2); // 设置加速度量程，默认2g
//    delay_ms(5);
//    i2c_write(int_set1_reg, 2); // 设置x,y,z发生变化时，产生中断
//    delay_ms(5);
//    i2c_write(int_map1_reg, 2); // 运动的时候，产生中断
//    delay_ms(5);
//    i2c_write(active_dur_addr, 2); // 设置激活时间，默认0x00
//    delay_ms(5);
//    i2c_write(active_ths_addr, 2); // 设置激活阈值
//    delay_ms(5);
//    i2c_write(mode_addr, 2); // 设置模式

//    uint8_t x038[] = {0x38, 0x03};
//    i2c_write(x038, 2); // 设置x轴阈值
//    uint8_t x039[] = {0x39, 0x09};
//    i2c_write(x039, 2); // 设置y轴阈值
//    uint8_t x03A[] = {0x3A, 0x06};
//    i2c_write(x03A, 2); // 设置z轴阈值
//    uint8_t x03B[] = {0x3B, 0x06};
//    i2c_write(x03B, 2); // 设置z轴阈值

//    // i2c.send(i2cId, da221Addr, { 0x38, 0x03 }, 1)
//    // i2c.send(i2cId, da221Addr, { 0x39, 0x09 }, 1)
//    // i2c.send(i2cId, da221Addr, { 0x3A, 0x06 }, 1)
//    // i2c.send(i2cId, da221Addr, { 0x3B, 0x06 }, 1)



//    delay_ms(5);
//    i2c_write(odr_addr, 2); // 设置采样率
//    delay_ms(5);
//    i2c_write(int_latch_addr, 2); // 设置中断锁存 中断一旦触发将保持，直到手动清除
//    delay_ms(5);
//    return 0;
//}


//uint8_t da221_read_xyz(void)
//{
//    i2c_write(x_lsb_reg, 1); // 设置模式
//    uint8_t buf[6] = {0};
//    i2c_read(buf, 6);
//    int16_t x = (int16_t)((buf[1] << 4) | buf[0] >> 4);
//    int16_t y = (int16_t)((buf[3] << 4) | buf[2] >> 4);
//    int16_t z = (int16_t)((buf[5] << 4) | buf[4] >> 4);

//    if(x > 2047)
//    {
//        x -= 4096;
//    }
//    if(y > 2047)
//    {
//        y -= 4096;
//    }
//    if(z > 2047)
//    {
//        z -= 4096;
//    }

//    printf("X: %d, Y: %d, Z: %d\r\n", x, y, z);
//    return 0;
//}
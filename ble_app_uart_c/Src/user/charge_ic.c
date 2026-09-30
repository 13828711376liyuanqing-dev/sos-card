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
#include "app_adc.h"
#include "app_adc_dma.h"
#include "board_SK.h"
#include "gr55xx_hal_adc.h"
#include "gr55xx_ll_adc.h"


#define I2C_SDA_GPIO_TYPE APP_IO_TYPE_GPIOB
#define I2C_SDA_GPIO_PIN APP_IO_PIN_12
#define I2C_SDA_GPIO_MUX APP_IO_MUX_5

#define I2C_SCL_GPIO_TYPE APP_IO_TYPE_AON
#define I2C_SCL_GPIO_PIN APP_IO_PIN_4
#define I2C_SCL_GPIO_MUX APP_IO_MUX_2

#define I2C_ID APP_I2C_ID_0

// 电池电压检测引脚定义
#define ADC_BAT_TYPE APP_IO_TYPE_MSIO
#define ADC_BAT_PIN  APP_IO_PIN_1    // MSIO1 (电池分压点)
#define ADC_BAT_MUX  APP_IO_MUX_7
#define EN_BATM_TYPE APP_IO_TYPE_MSIO
#define EN_BATM_PIN  APP_IO_PIN_5    // MSIO5

// 电池分压比: 33K / (100K + 33K) = 33/133 ≈ 0.248
#define BAT_DIVIDER_RATIO  0.248f


static app_i2c_params_t charge_ic_params = {
    .id = I2C_ID,
    .role = APP_I2C_ROLE_MASTER,
    .pin_cfg = {
        .scl = {
            .type = I2C_SCL_GPIO_TYPE,
            .mux = I2C_SCL_GPIO_MUX,
            .pin = I2C_SCL_GPIO_PIN,
            .pull = APP_IO_PULLUP,
        },
        .sda = {
            .type = I2C_SDA_GPIO_TYPE,
            .mux = I2C_SDA_GPIO_MUX,
            .pin = I2C_SDA_GPIO_PIN,
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
        .speed = I2C_SPEED_100K,
        .own_address = 0x00,
        .addressing_mode = I2C_ADDRESSINGMODE_7BIT,
        .general_call_mode = I2C_GENERALCALL_DISABLE,
    },
};

#define CHARGE_IC_ADDR 0x6B
#define CHARGE_IC_ID 0x3F

static uint16_t i2c_write(uint8_t *data, uint8_t len)
{
    uint16_t ret = 0;
    ret = app_i2c_transmit_sync(I2C_ID, CHARGE_IC_ADDR, data, len, 50);
    return ret;
}

static uint16_t i2c_read(uint8_t *buffer, uint16_t len)
{
    uint16_t ret = 0;
    ret = app_i2c_receive_sync(I2C_ID, CHARGE_IC_ADDR, buffer, len, 50);
    return ret;
}

volatile uint8_t charge_ic_int = 0;

// 充电参数设置
// VREG范围: 4.07V~4.7V, 步进10mV, REG04[7:2] = (voltage_mv - 3840) / 10
// ICHG范围: 0~3820mA, 步进20mA, REG02[7:2] = current_ma / 20

#define CHARGE_VOLTAGE_DEFAULT  0x26  // 4.2V (REG04[7:2]=00100110)
#define CHARGE_CURRENT_DEFAULT  0xC0  // 960mA (REG02[7:2]=11000000)

// ADC相关变量 - 使用HAL层直接控制
static adc_handle_t adc_bat_handle = {0};
static uint16_t adc_bat_buffer[4];
static double adc_voltage[4];
static volatile uint8_t adc_conv_done = 0;

static void app_io_event_handler(app_io_evt_t *p_evt)
{
    if (p_evt->pin == APP_IO_PIN_5)
    {
        charge_ic_int = 1;
    }
}

const app_gpiote_param_t gpiote_param_charge_ic[] =
{
    {APP_IO_TYPE_AON, APP_IO_PIN_5, APP_IO_MODE_IT_FALLING, APP_IO_PULLDOWN, app_io_event_handler},
};

// 读取电池电压 (mV) - 使用HAL层直接控制
uint16_t charge_ic_read_battery_voltage(void)
{
    hal_status_t hal_ret;
    uint16_t adc_raw = 0;
    double vbat = 0;

    // 开启MOS进行电池检测 (EN_BATM=LOW)
    app_io_write_pin(EN_BATM_TYPE, EN_BATM_PIN, APP_IO_PIN_RESET);
    delay_ms(50);

    // 初始化MSIO1为模拟输入
    app_io_init_t io_init = {
        .pin = APP_ADC_N_INPUT_PIN,
        .mux = APP_IO_MUX_7,
        .pull = APP_IO_NOPULL,
        .mode = APP_IO_MODE_ANALOG
    };
    app_io_init(APP_IO_TYPE_MSIO, &io_init);

    // 配置ADC
    adc_bat_handle.init.channel_n  = ADC_INPUT_SRC_IO1;
    adc_bat_handle.init.channel_p  = ADC_INPUT_SRC_IO1;
    adc_bat_handle.init.input_mode = ADC_INPUT_SINGLE;
    adc_bat_handle.init.ref_source = ADC_REF_SRC_BUF_INT;
    adc_bat_handle.init.ref_value   = ADC_REF_VALUE_1P6;
    adc_bat_handle.init.clock       = ADC_CLK_1M;

    hal_ret = hal_adc_init(&adc_bat_handle);

    memset(adc_bat_buffer, 0, sizeof(adc_bat_buffer));
    hal_ret = hal_adc_poll_for_conversion(&adc_bat_handle, adc_bat_buffer, 4);
    
    // 使用4次采样的平均值
    adc_raw = (adc_bat_buffer[0] + adc_bat_buffer[1] + adc_bat_buffer[2] + adc_bat_buffer[3]) / 4;
    
    printf("ADC raw: %u,%u,%u,%u, avg=%u\r\n", 
           adc_bat_buffer[0], adc_bat_buffer[1], adc_bat_buffer[2], adc_bat_buffer[3], adc_raw);

    hal_adc_deinit(&adc_bat_handle);

    // 关闭电池检测MOS
    app_io_write_pin(EN_BATM_TYPE, EN_BATM_PIN, APP_IO_PIN_SET);

    // 计算电池电压: Vbat = (adc_raw / 4095) * 1.6V / 分压比
    double vbat_adc = ((double)adc_raw / 4095.0) * 1.6;
    vbat = vbat_adc / BAT_DIVIDER_RATIO;
    
    printf("Battery Voltage: %.3fV\r\n", vbat);

    return (uint16_t)(vbat * 1000);  // 返回mV
}

uint8_t charge_ic_init(void)
{
    uint16_t ret;
    app_io_init_t io_init = APP_IO_DEFAULT_CONFIG;
    app_io_pin_state_t pin_val;

    // 先把使能脚拉高  GPIO20_NQON
    io_init.pull = APP_IO_NOPULL;
    io_init.mode = APP_IO_MODE_OUTPUT;
    io_init.pin = APP_IO_PIN_4;
    io_init.mux = APP_IO_MUX;
    ret = app_io_init(APP_IO_TYPE_GPIOB, &io_init);
    app_io_write_pin(APP_IO_TYPE_GPIOB, APP_IO_PIN_4, APP_IO_PIN_SET);

    // 初始化EN_BATM引脚 (默认关闭电池检测MOS)
    io_init.pull = APP_IO_NOPULL;
    io_init.mode = APP_IO_MODE_OUTPUT;
    io_init.pin = EN_BATM_PIN;
    io_init.mux = APP_IO_MUX;
    ret = app_io_init(EN_BATM_TYPE, &io_init);
    app_io_write_pin(EN_BATM_TYPE, EN_BATM_PIN, APP_IO_PIN_SET);  // 默认高电平关闭

    // 注意：不要预先初始化MSIO0/MSIO1为模拟输入！
    // app_adc_init内部会自己配置这些引脚，预先初始化可能导致冲突

    app_i2c_init(&charge_ic_params, NULL);

    uint16_t i2c_ret = 0;

    // 读取芯片ID
    uint8_t reg_0b = 0x0B;
    uint8_t data = 0;
    i2c_ret = i2c_write(&reg_0b, 1);
    i2c_read(&data, 1);

    data = data & 0x7F; // 取低7位

    if (data != CHARGE_IC_ID)
    {
        printf("charge ic id error, read: 0x%02X\r\n", data);
        return 1;
    }
    printf("charge ic id: 0x%02X\r\n", data);

    // 检查VLDO状态 - 读取REG0A
    reg_0b = 0x0A;
    i2c_write(&reg_0b, 1);
    i2c_read(&data, 1);
    printf("VLDO Status: %s\r\n", (data & 0x80) ? "OK" : "Not Ready");

    // 检查Power Good状态
    reg_0b = 0x08;
    i2c_write(&reg_0b, 1);
    i2c_read(&data, 1);
    printf("Power Good: %s\r\n", (data & 0x04) ? "Yes" : "No");

    // 读取REG00 - 确认充电配置
    reg_0b = 0x00;
    i2c_write(&reg_0b, 1);
    i2c_read(&data, 1);
    printf("HIZ Mode: %s\r\n", (data & 0x80) ? "ON" : "OFF");
    uint8_t iindpm = (data >> 2) & 0x1F;
    printf("Input Current Limit: %umA\r\n", 100 + iindpm * 100);

    // 读取REG02 - 充电电流配置
    reg_0b = 0x02;
    i2c_write(&reg_0b, 1);
    i2c_read(&data, 1);
    uint8_t ichg = (data >> 2) & 0x7F;
    printf("Fast Charge Current: %umA\r\n", ichg * 20);

    // 读取REG04 - 充电电压配置
    reg_0b = 0x04;
    i2c_write(&reg_0b, 1);
    i2c_read(&data, 1);
    uint8_t vreg = (data >> 2) & 0x3F;
    printf("Charge Voltage: %umV\r\n", 3840 + vreg * 10);

    app_gpiote_init(gpiote_param_charge_ic, sizeof(gpiote_param_charge_ic) / sizeof(app_gpiote_param_t));

    return 0;
}

void charge_ic_read_status(void)
{
    uint8_t reg_addr;
    uint8_t data;

    // 读取REG08 - 状态寄存器
    reg_addr = 0x08;
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    // VBUS_STAT[2:0]
    uint8_t vbus_stat = (data >> 5) & 0x07;
    // CHRG_STAT[1:0]
    uint8_t chrg_stat = (data >> 3) & 0x03;
    // PG_STAT
    uint8_t pg_stat = (data >> 2) & 0x01;
    // THERM_STAT
    uint8_t therm_stat = (data >> 1) & 0x01;
    // VSYS_STAT
    uint8_t vsys_stat = data & 0x01;

    printf("--- Charge IC Status ---\r\n");
    printf("VBUS: ");
    switch(vbus_stat)
    {
        case 0: printf("No Input\r\n"); break;
        case 1: printf("USB Host SDP\r\n"); break;
        case 2: printf("USB CDP(1.5A)\r\n"); break;
        case 3: printf("USB DCP(2.4A)\r\n"); break;
        case 5: printf("Unknown Adapter(500mA)\r\n"); break;
        case 6: printf("Non-Standard Adapter\r\n"); break;
        case 7: printf("OTG\r\n"); break;
        default: printf("Unknown\r\n"); break;
    }

    printf("CHG: ");
    switch(chrg_stat)
    {
        case 0: printf("Not Charging\r\n"); break;
        case 1: printf("Pre-charge\r\n"); break;
        case 2: printf("Fast Charging\r\n"); break;
        case 3: printf("Charge Done\r\n"); break;
        default: printf("Unknown\r\n"); break;
    }

    printf("PG: %s\r\n", pg_stat ? "Good" : "Bad");
    printf("Thermal Reg: %s\r\n", therm_stat ? "Yes" : "No");
    printf("VSYS Min: %s\r\n", vsys_stat ? "In Regulation" : "Not In Regulation");

    // 读取REG09 - 故障寄存器
    reg_addr = 0x09;
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    uint8_t watchdog_fault = (data >> 6) & 0x01;
    uint8_t boost_fault = (data >> 5) & 0x01;
    uint8_t chrg_fault = (data >> 3) & 0x03;
    uint8_t bat_fault = (data >> 2) & 0x01;
    uint8_t ntc_fault = data & 0x07;

    printf("Watchdog Fault: %s\r\n", watchdog_fault ? "Expired" : "Normal");
    printf("Boost Fault: %s\r\n", boost_fault ? "Yes" : "No");
    printf("BAT Fault: %s\r\n", bat_fault ? "OVP" : "Normal");

    if(ntc_fault != 0)
    {
        printf("NTC Fault: ");
        switch(ntc_fault)
        {
            case 2: printf("Warm\r\n"); break;
            case 3: printf("Cool\r\n"); break;
            case 5: printf("Cold\r\n"); break;
            case 6: printf("Hot\r\n"); break;
            default: printf("0x%02X\r\n", ntc_fault); break;
        }
    }
    else
    {
        printf("NTC: Normal\r\n");
    }

    // 读取REG0A - VBUS和DPM状态
    reg_addr = 0x0A;
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    uint8_t vbus_gd = (data >> 7) & 0x01;
    uint8_t vindpm_stat = (data >> 6) & 0x01;
    uint8_t iindpm_stat = (data >> 5) & 0x01;
    uint8_t cv_stat = (data >> 4) & 0x01;

    printf("VBUS GD: %s\r\n", vbus_gd ? "Attached" : "Not Attached");
    printf("VINDPM: %s\r\n", vindpm_stat ? "In Regulation" : "Normal");
    printf("IINDPM: %s\r\n", iindpm_stat ? "In Regulation" : "Normal");
    printf("CV Mode: %s\r\n", cv_stat ? "Yes" : "No");

    // 读取REG0E - ADC值 (包含TS引脚电压)
    reg_addr = 0x0E;
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    // TSR 温度ADC值 (低6位)
    uint8_t tsr_value = data & 0x3F;
    // 根据ADC值判断温度等级 (值越高=温度越低，因为热敏电阻高温低阻分压低)
    printf("Battery Temp: ");
    if (tsr_value > 50) {
        printf("Cold\r\n");
    } else if (tsr_value > 40) {
        printf("Cool\r\n");
    } else if (tsr_value > 25) {
        printf("Normal\r\n");
    } else if (tsr_value > 15) {
        printf("Warm\r\n");
    } else {
        printf("Hot\r\n");
    }
    printf("TS ADC: %u\r\n", tsr_value);

    // 读取电池电压
    uint16_t battery_mv = charge_ic_read_battery_voltage();
    printf("Battery Voltage: %u.%03uV\r\n", battery_mv / 1000, battery_mv % 1000);
    printf("------------------------\r\n");
}
// 范围: 4070mV ~ 4700mV, 步进10mV
void charge_ic_set_voltage(uint16_t voltage_mv)
{
    uint8_t reg_addr = 0x04;
    uint8_t data;

    // 读取当前值
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    // VREG[5:0] = (voltage_mv - 3840) / 10, 限制范围
    uint8_t vreg = (voltage_mv - 3840) / 10;
    if (vreg > 63) vreg = 63;

    // 写入: [7:2]=VREG, [1]=rechg_thresh, [0]=boost_lim
    data = (vreg << 2) | (data & 0x03);

    uint8_t write_data[2] = {reg_addr, data};
    i2c_write(write_data, 2);

    uint16_t actual_voltage = 3840 + vreg * 10;
    printf("Set charge voltage: %umV (reg=0x%02X)\r\n", actual_voltage, data);
}

// 设置充电电流 (mA)
// 范围: 0mA ~ 3820mA, 步进20mA
void charge_ic_set_current(uint16_t current_ma)
{
    uint8_t reg_addr = 0x02;
    uint8_t data;

    // 读取当前值
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    // ICHG[6:0] = current_ma / 20, 限制范围
    uint8_t ichg = current_ma / 20;
    if (ichg > 191) ichg = 191;

    // 写入: [7:2]=ICHG, [1]=head_expire_en, [0]=boost_freq
    data = (ichg << 2) | (data & 0x03);

    uint8_t write_data[2] = {reg_addr, data};
    i2c_write(write_data, 2);

    uint16_t actual_current = ichg * 20;
    printf("Set charge current: %umA (reg=0x%02X)\r\n", actual_current, data);
}

// 设置完成后调用此函数使配置生效
void charge_ic_apply_settings(void)
{
    // 读取并重新写入REG04触发配置更新
    uint8_t reg_addr = 0x04;
    uint8_t data;
    i2c_write(&reg_addr, 1);
    i2c_read(&data, 1);

    uint8_t write_data[2] = {reg_addr, data};
    i2c_write(write_data, 2);
    printf("Charge IC settings applied\r\n");
}


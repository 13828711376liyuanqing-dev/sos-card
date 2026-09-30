# ETA69631 充电IC集成指南

## 概述

本文档介绍了如何在GR552x蓝牙芯片中集成ETA69631充电管理IC。该充电IC通过I2C接口与蓝牙芯片通信，用于监控锂电池充电状态、电池电压和充电电流。

## 硬件连接

根据您提供的信息，ETA69631与蓝牙芯片的连接如下：

- **GPIO28** → CHG_SDA (I2C数据线)
- **AON_GPIO4** → CHG_SCL (I2C时钟线)
- **AON_GPIO5** → CHG_INT (中断线，用于充电状态变化)

**注意**: 所有引脚配置已在代码中正确设置，无需修改。

## 文件说明

### 1. 核心驱动程序

- **`eta69631.h`**: 头文件，包含寄存器定义、数据结构和函数声明
- **`eta69631.c`**: 驱动程序实现，包括I2C通信、状态监控和配置功能

### 2. 测试程序

- **`chg_test.h`**: 测试功能头文件
- **`chg_test.c`**: 测试功能实现，可用于验证充电IC功能

### 3. 集成文件

- **`main.c`**: 已修改，添加了充电IC初始化和处理

## 主要功能

### 1. 充电状态监控
- 充电状态：未充电、预充电、快充、充电完成
- 电源状态：电源良好、热调节激活等
- VBUS状态：USB主机、适配器、OTG

### 2. 故障检测
- 充电故障：输入故障、热故障、超时
- 电池故障：过压保护
- NTC故障：温度过高、过低
- 看门狗故障、升压故障

### 3. 电池信息获取
- 电池电压（mV）
- 系统电压（mV）
- 充电电流（mA）

### 4. 配置功能
- 充电电流设置（64-5056mA）
- 充电电压设置（3504-4624mV）
- 输入电流限制（100-3250mA）
- 充电使能/禁用

## 使用说明

### 1. 初始化

在`main.c`中添加以下代码：

```c
#include "eta69631.h"

// 在main函数中初始化
if (!eta69631_init())
{
    APP_LOG_ERROR("ETA69631 initialization failed");
}
```

### 2. 主循环处理

在`main.c`的主循环中添加：

```c
eta69631_process();  // 处理充电IC中断和状态更新
```

### 3. 获取充电状态

```c
// 获取状态信息
eta69631_status_t status;
if (eta69631_get_status(&status))
{
    const char* status_str = eta69631_get_chrg_status_string();
    APP_LOG_INFO("Charging Status: %s", status_str);
}

// 检查充电是否完成
if (eta69631_is_charging_done())
{
    APP_LOG_INFO("Charging complete!");
}

// 检查电源状态
if (eta69631_is_power_good())
{
    APP_LOG_INFO("Power is good");
}
```

### 4. 获取电池信息

```c
eta69631_battery_info_t battery_info;
if (eta69631_get_battery_info(&battery_info))
{
    APP_LOG_INFO("Battery: %dmV, System: %dmV, Charge: %dmA",
               battery_info.bat_voltage,
               battery_info.sys_voltage,
               battery_info.charge_current);
}
```

### 5. 配置充电参数

```c
// 设置充电电流为1000mA
eta69631_set_charge_current(1000);

// 设置充电电压为4.2V (4200mV)
eta69631_set_charge_voltage(4200);

// 设置输入电流限制为2000mA
eta69631_set_input_current_limit(2000);
```

### 6. 故障处理

```c
eta69631_fault_t fault;
if (eta69631_get_fault(&fault))
{
    if (fault.chrg_fault != ETA69631_FAULT_CHRG_NORMAL)
    {
        APP_LOG_WARNING("Charge fault detected: 0x%02X", fault.chrg_fault);
    }
    if (fault.bat_fault == ETA69631_FAULT_BAT_OVP)
    {
        APP_LOG_ERROR("Battery overvoltage protection triggered!");
    }
}
```

## 测试功能

### 1. 运行所有测试

```c
#include "chg_test.h"

// 运行全面测试
chg_test_run_all();
```

### 2. 监控模式

```c
// 在main循环中调用，每10秒打印一次状态
chg_test_monitor(10000);  // 10秒间隔
```

### 3. 按键测试

已修改SOS按键功能，当按下SOS键时，会自动打印充电状态信息。

## 配置选项

### 默认配置（可在`eta69631.c`中修改）

```c
#define ETA69631_DEFAULT_CHRG_CURRENT  1000    /* 1000mA */
#define ETA69631_DEFAULT_CHRG_VOLTAGE  4200    /* 4.2V */
#define ETA69631_DEFAULT_INPUT_CURRENT 2000    /* 2000mA */
```

### I2C配置

```c
#define ETA69631_I2C_ID             APP_I2C_ID_1
#define ETA69631_I2C_SPEED          I2C_SPEED_400K
```

## 调试信息

驱动程序会通过串口输出调试信息，包括：
- 初始化状态
- 充电状态变化
- 故障报警
- 定期电池信息

## 注意事项

1. **引脚确认**: 所有引脚已确认：
   - GPIO28: CHG_SDA (I2C数据线)
   - AON_GPIO4: CHG_SCL (I2C时钟线)
   - AON_GPIO5: CHG_INT (中断线)
2. **I2C地址**: ETA69631的I2C地址为0x6A（7位地址）
3. **中断处理**: 充电状态变化会通过AON_GPIO5产生中断
4. **电源管理**: 充电IC会自动管理充电过程，代码只需监控状态
5. **兼容性**: 确保I2C引脚配置与其他外设（如DA221传感器）不冲突

## 故障排除

### 1. 初始化失败
- 检查I2C连接是否正常
- 确认I2C地址是否正确（0x6A）
- 检查电源是否正常

### 2. 无法读取状态
- 检查I2C通信是否正常
- 确认GPIO配置是否正确
- 检查充电IC是否正常工作

### 3. 充电状态不更新
- 检查中断引脚连接
- 确认中断配置是否正确
- 检查充电IC是否处于正常工作状态

## 扩展功能

### 1. 低电量报警
可以在代码中添加低电量检测逻辑：

```c
if (battery_info.bat_voltage < 3500)  // 3.5V
{
    APP_LOG_WARNING("Low battery: %dmV", battery_info.bat_voltage);
    // 触发低电量警告或关机
}
```

### 2. 充电统计
可以添加充电时间统计和充电周期计数功能。

### 3. 蓝牙通知
可以将充电状态通过蓝牙通知手机或其他设备。

## 联系支持

如有问题或需要进一步帮助，请提供：
1. 实际的硬件连接图
2. 充电IC型号和数据手册
3. 遇到的错误信息
4. 测试环境描述

# GCC 工程流程分析与 KEIL 建工程说明

## 1. 分析范围

分析目录：

```text
D:\CODEX\sos-card
```

核心项目：

```text
ble_app_uart_c
```

该项目基于 Goodix GR5526 SDK，当前 GCC 工程已经生成过可用的 `bin`、`hex` 和 `map` 文件。

本次分析为只读分析，没有修改源码，没有执行 KEIL 编译、下载或硬件验证。

## 2. 工程目录结构

```text
sos-card
├─ ble_app_uart_c                 当前应用工程
│  ├─ GCC                          GCC Makefile 和链接文件
│  ├─ Src
│  │  ├─ platform                  板级初始化
│  │  ├─ user                      应用业务代码
│  │  └─ external                  QP/C、cJSON、slre
│  ├─ pin_v2.csv                   引脚配置记录
│  └─ GCC/out                      GCC 编译输出
├─ SDK                             Goodix GR5526 SDK
│  ├─ components                   BLE、协议、库和应用组件
│  ├─ drivers                      外设驱动
│  ├─ platform                     SoC、启动文件、板级支持
│  ├─ external                     FreeRTOS、RTT、TinyUSB 等
│  └─ projects                     SDK 官方示例工程
├─ cat_1                           Cat.1 相关资料和工程
└─ doc                             硬件、证书及其他资料
```

## 3. 软件总体流程

```text
上电复位
  │
  ├─ Startup.S
  │    └─ Reset_Handler
  │         ├─ 初始化栈
  │         ├─ 初始化数据段和 BSS
  │         └─ 进入 main()
  │
  ├─ main.c
  │    └─ 当前启用 TK_USE_QP = 1
  │         ├─ QF_init()
  │         ├─ BSP_init()
  │         ├─ BSP_start()
  │         └─ QF_run()
  │
  ├─ QP/C 事件驱动框架
  │    └─ 运行应用主动对象和事件队列
  │
  ├─ BSP 初始化
  │    ├─ GPIO
  │    ├─ UART
  │    ├─ I2C
  │    ├─ 充电芯片 ETA69631
  │    ├─ DA221 传感器
  │    ├─ BLE 协议栈
  │    └─ CLI 命令行
  │
  ├─ BLE 初始化完成事件
  │    └─ ble_evt_handler()
  │         └─ ble_app_init()
  │              ├─ 初始化 BLE 扫描
  │              ├─ 初始化 UART↔BLE 数据通道
  │              └─ 启动扫描
  │
  ├─ BLE 广播接收
  │    └─ TK Beacon 数据解析
  │
  ├─ UART 接收数据
  │    └─ 写入 UART 环形缓冲区
  │         └─ 按 MTU 分包发送到 BLE
  │
  └─ BLE 接收数据
       └─ 写入 BLE 环形缓冲区
            └─ 发送到 UART
```

## 4. 主要软件模块

| 文件或目录 | 主要职责 |
|---|---|
| `Src/user/main.c` | 系统入口、QP 启动、BLE 启动、SysTick |
| `Src/user/user_app.c` | BLE 扫描、连接、GUS UART Service 通信 |
| `Src/user/transport_scheduler.c` | UART 与 BLE 双向数据转发、环形缓冲和流控 |
| `Src/platform/bsp.c` | 板级初始化、QP/C 与硬件连接 |
| `Src/user/blinky.c` | QP 示例应用和灯光逻辑 |
| `Src/user/sensor.c` | DA221 传感器状态机 |
| `Src/user/da221.c` | DA221 I2C 底层驱动 |
| `Src/user/charge_ic.c` | 充电芯片底层控制 |
| `Src/user/eta69631.c` | ETA69631 寄存器操作 |
| `Src/user/charging_commands.c` | `chg status`、`chg current` 等命令 |
| `Src/user/cli.c` | 串口命令行解析 |
| `Src/user/cat1svr.c` | Cat.1 模块通信 |
| `Src/user/location_servise.c` | 定位相关业务 |
| `Src/external/qpc_7.3.4` | QP/C 事件驱动框架 |
| `Src/external/cJSON-1.7.19` | JSON 解析 |
| `Src/external/slre-1.3` | 简单正则表达式解析 |
| `SDK/components/sdk/ble.c` | Goodix BLE SDK 封装 |
| `SDK/components/profiles/gus_c/gus_c.c` | GUS UART Client 协议 |

## 5. `main.c` 当前实际运行分支

文件：

```text
ble_app_uart_c/Src/user/main.c
```

当前代码中：

```c
#define TK_USE_QP 1
```

因此真正编译和运行的是：

```c
int main()
{
    QF_init();
    BSP_init();
    BSP_start();
    return QF_run();
}
```

下面的传统裸机初始化分支不会参与当前编译：

```c
app_periph_init();
ble_stack_init();

while (1)
{
    app_log_flush();
    transport_schedule();
    pwr_mgmt_schedule();
}
```

因此 KEIL 工程必须完整加入 QP/C 文件，否则容易出现以下链接错误：

```text
undefined symbol QF_init
undefined symbol BSP_init
undefined symbol BSP_start
undefined symbol QF_run
```

## 6. GCC 工程组成

GCC 配置文件：

```text
ble_app_uart_c/GCC/Makefile
```

### 6.1 SDK 底层文件

```text
SDK/platform/soc/common/gr_system.c
SDK/platform/soc/common/gr_interrupt.c
SDK/platform/soc/common/gr_platform.c
SDK/platform/soc/src/gr_soc.c
SDK/platform/boards/board_SK.c
```

### 6.2 外设驱动

```text
SDK/drivers/src/app_dma.c
SDK/drivers/src/app_gpiote.c
SDK/drivers/src/app_io.c
SDK/drivers/src/app_pwr_mgmt.c
SDK/drivers/src/app_uart.c
SDK/drivers/src/app_uart_dma.c
SDK/drivers/src/app_i2c.c
SDK/drivers/src/app_i2c_dma.c
SDK/drivers/src/app_adc.c
SDK/drivers/src/app_adc_dma.c
SDK/drivers/src/app_rtc.c
SDK/drivers/src/app_aon_wdt.c
```

### 6.3 BLE 协议和服务

```text
SDK/components/libraries/ble/ble_scanner/ble_scanner.c
SDK/components/libraries/ble/ble_time/ble_time.c
SDK/components/sdk/ble.c
SDK/components/profiles/common/ble_prf_utils.c
SDK/components/profiles/gus_c/gus_c.c
```

### 6.4 用户业务文件

```text
Src/platform/user_periph_setup.c
Src/platform/bsp.c
Src/user/main.c
Src/user/app.c
Src/user/user_app.c
Src/user/transport_scheduler.c
Src/user/da221.c
Src/user/gpio_test.c
Src/user/charge_ic.c
Src/user/at_cmds.c
Src/user/cli.c
Src/user/log_cmd.c
Src/user/blinky.c
Src/user/location_servise.c
Src/user/cat1svr.c
Src/user/sensor.c
Src/user/da221_config.c
```

### 6.5 QP/C 文件

```text
qv.c
qep_hsm.c
qep_msm.c
qf_act.c
qf_actq.c
qf_defer.c
qf_dyn.c
qf_mem.c
qf_ps.c
qf_qact.c
qf_qeq.c
qf_qmact.c
qf_time.c
qv_port.c
```

### 6.6 第三方文件

```text
cJSON.c
slre.c
SEGGER_RTT.c
```

## 7. GCC 与 KEIL 的关键差异

### 7.1 启动文件

GCC 使用：

```text
SDK/platform/arch/arm/cortex-m/gcc/startup_gr55xx.s
```

KEIL 应使用：

```text
SDK/platform/arch/arm/cortex-m/keil/Startup.S
```

不能把 GCC 启动文件直接加入 KEIL 工程。

### 7.2 BLE 库

GCC 使用：

```text
SDK/platform/soc/linker/gcc/libble_sdk.a
```

KEIL 使用：

```text
SDK/platform/soc/linker/keil/ble_sdk.lib
```

不能把 `.a` 文件直接替代 `.lib` 文件。

### 7.3 链接文件

GCC 使用：

```text
ble_app_uart_c/GCC/gcc_linker.lds
```

KEIL 不直接使用 `.lds`，需要使用 SDK 已有的 Keil scatter/linker 配置。

参考模板：

```text
SDK/projects/peripheral/dspi/app_dspi/Keil_5/app_dspi.uvprojx
```

### 7.4 编译器选项

GCC 当前使用的主要选项：

```text
-std=gnu99
-mcpu=cortex-m4
-mthumb
-mfpu=fpv4-sp-d16
-mfloat-abi=softfp
-ffunction-sections
-fdata-sections
```

KEIL 中应对应配置：

- ARM Compiler 5 或兼容的 ARM Compiler
- Cortex-M4
- Thumb
- 单精度 FPU
- SoftFP
- C99/GNU 扩展兼容模式
- 初次调试建议先使用 `-O0` 或 `-O1`

## 8. KEIL 建工程步骤

### 第一步：复制官方模板

复制：

```text
SDK/projects/peripheral/dspi/app_dspi/Keil_5
```

目标目录：

```text
ble_app_uart_c/Keil_5
```

然后将工程改名为：

```text
ble_app_uart_c.uvprojx
```

### 第二步：修改 Target 配置

设置：

- Target Name：`ble_app_uart_c`
- Output Name：`ble_app_uart_c`
- 输出目录：`Objects`
- Listing 目录：`Listings`
- Device：`ARMCM4_FP`
- CPU：Cortex-M4
- IROM/RAM 地址和容量：保持 GR5526 官方模板配置

### 第三步：替换启动文件和 BLE 库

删除模板中的启动文件，添加：

```text
SDK/platform/arch/arm/cortex-m/keil/Startup.S
```

链接库改为：

```text
SDK/platform/soc/linker/keil/ble_sdk.lib
```

不要使用：

```text
GCC/libble_sdk.a
GCC/startup_gr55xx.s
GCC/gcc_linker.lds
```

### 第四步：添加 SDK 源文件

按 GCC Makefile 添加以下目录中的实际 `.c` 文件：

```text
SDK/platform/soc/common
SDK/platform/soc/src
SDK/platform/boards
SDK/drivers/src
SDK/components/libraries
SDK/components/sdk
SDK/components/profiles/common
SDK/components/profiles/gus_c
SDK/external/segger_rtt
```

### 第五步：添加用户文件

至少添加：

```text
ble_app_uart_c/Src/platform/user_periph_setup.c
ble_app_uart_c/Src/platform/bsp.c
ble_app_uart_c/Src/user/main.c
ble_app_uart_c/Src/user/app.c
ble_app_uart_c/Src/user/user_app.c
ble_app_uart_c/Src/user/transport_scheduler.c
ble_app_uart_c/Src/user/sensor.c
ble_app_uart_c/Src/user/da221.c
ble_app_uart_c/Src/user/da221_config.c
ble_app_uart_c/Src/user/charge_ic.c
ble_app_uart_c/Src/user/eta69631.c
ble_app_uart_c/Src/user/charging_commands.c
ble_app_uart_c/Src/user/chg_test.c
ble_app_uart_c/Src/user/at_cmds.c
ble_app_uart_c/Src/user/cli.c
ble_app_uart_c/Src/user/log_cmd.c
ble_app_uart_c/Src/user/blinky.c
ble_app_uart_c/Src/user/location_servise.c
ble_app_uart_c/Src/user/cat1svr.c
```

并加入完整 QP/C、cJSON、slre 文件。

### 第六步：添加头文件路径

```text
ble_app_uart_c/Src/config
ble_app_uart_c/Src/platform
ble_app_uart_c/Src/user
ble_app_uart_c/Src/external/qpc_7.3.4/qpc/include
ble_app_uart_c/Src/external/qpc_7.3.4/qpc/ports/arm-cm/qv/gnu
ble_app_uart_c/Src/external/cJSON-1.7.19
ble_app_uart_c/Src/external/slre-1.3
SDK/components/boards
SDK/components/drivers_ext/gr55xx
SDK/components/libraries
SDK/components/libraries/ble/ble_scanner
SDK/components/libraries/ble/ble_time
SDK/components/profiles/common
SDK/components/profiles/gus_c
SDK/components/sdk
SDK/drivers/inc
SDK/drivers/inc/hal
SDK/platform/include
SDK/platform/soc/include
SDK/platform/boards
SDK/platform/soc/linker/keil
SDK/external/freertos/include
SDK/external/segger_rtt
SDK/platform/arch/arm/cortex-m/cmsis/core/include
```

### 第七步：添加宏定义

GCC 当前定义：

```text
ENV_USE_FREERTOS
```

KEIL 初次建工程时应先同步这个宏。当前 `main.c` 又启用了 QP/C，说明工程中存在 QP 与 FreeRTOS 配置混用现象，建议先保持现状解决真实编译错误，不要一开始大范围清理宏定义。

### 第八步：检查 QP/C 移植层

GCC 使用：

```text
qpc/ports/arm-cm/qv/gnu/qv_port.c
```

KEIL 编译时如果出现 GCC 专用语法错误，需要改用 QP/C 的 ARM/KEIL 移植层，或只对 `qv_port.c` 增加编译器条件分支。

不要直接修改 QP/C 核心文件。

## 9. 建议的 KEIL 编译排错顺序

1. 先加入启动文件、BLE 库、基础 SDK 文件和 `main.c`。
2. 解决启动文件、头文件和链接库问题。
3. 加入 BLE 相关文件。
4. 加入 UART/BLE 传输模块。
5. 加入 QP/C 文件。
6. 加入传感器、充电芯片、Cat.1、JSON 等业务模块。
7. 最后加入测试和命令模块。

常见错误：

| 错误 | 可能原因 |
|---|---|
| `cannot open source input file` | 工程相对路径错误 |
| `undefined symbol ble_stack_init` | `ble_sdk.lib` 或 BLE 源文件未加入 |
| `undefined symbol QF_run` | QP/C 文件未完整加入 |
| `undefined symbol BSP_start` | `bsp.c` 或 QP 业务文件未加入 |
| `undefined symbol __aeabi_*` | ARM 编译器版本或运行库配置不匹配 |
| `multiple definition of main` | 重复加入其他 `main.c` |
| `cannot open scatter file` | KEIL 链接配置缺少 scatter 文件 |
| `RAM/ROM overflow` | KEIL 内存布局与 GCC `.lds` 不一致 |

## 10. 关键结论

这个项目不是简单把 GCC Makefile 转换成 KEIL 工程，必须重新处理以下四项：

```text
GCC startup_gr55xx.s
        ↓
KEIL Startup.S

libble_sdk.a
        ↓
ble_sdk.lib

gcc_linker.lds
        ↓
KEIL scatter/linker 配置

GCC 编译选项
        ↓
KEIL Target、Compiler、Linker 配置
```

用户 C 代码和大多数 Goodix SDK C 文件可以继续使用。重点检查：

- 启动文件
- BLE 库
- 内存布局
- QP/C 编译器适配
- 宏定义
- KEIL 工程完整文件清单
- ETA69631 和充电测试新增文件是否真正加入工程

## 11. 当前未完成项

目前没有找到：

```text
ble_app_uart_c/Keil_5/ble_app_uart_c.uvprojx
```

因此检查清单中“打开 KEIL 工程”这一步目前不能直接执行，必须先根据 SDK 官方 Keil 工程模板建立工程。

最终是否真正迁移成功，还需要用户使用 KEIL 完成：

- 编译
- 链接
- 生成 HEX/BIN
- 下载到 GR5526
- 串口日志确认
- BLE、UART、充电芯片和传感器实机测试


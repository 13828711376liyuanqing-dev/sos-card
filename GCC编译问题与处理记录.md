# GCC 编译问题与处理记录

## 1. 项目与工具链

- 项目目录：`D:\CODEX\sos-card\ble_app_uart_c`
- GCC 工程：`ble_app_uart_c\GCC`
- GNU Arm GCC：xPack GNU Arm Embedded GCC 15.2.1
- GNU Make：4.4.1
- 工具链目录：`D:\CODEX\sos-card_toolchains\runtime\arm-gcc-xpack\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin`
- Make 目录：`D:\CODEX\sos-card_toolchains\runtime\mingw\mingw64\bin`

## 2. 初始编译问题

### 2.1 `LED_G_IO_PIN` 未定义

错误表现：

```text
LED_G_IO_PIN undeclared
```

原因：

`user_periph_setup.h` 只有在对应板型宏启用时才会定义 `LED_G_IO_PIN`。本项目使用的是 TK UART 调试板配置，但 GCC Makefile 没有默认打开该配置宏。

处理：

在 `ble_app_uart_c\GCC\Makefile` 的 GCC 编译宏中加入：

```make
TK_Board_UART_DBG
```

编译时可以看到：

```text
#pragma message: LED_G_IO_PIN APP_IO_PIN_4
#pragma message: USE TK Board
```

这说明 LED 引脚和板型配置已经生效。

### 2.2 `gpio_init()` 未声明

错误表现：

```text
implicit declaration of function 'gpio_init'
```

原因：

`gpio_init()` 已经在 `Src\user\gpio_test.c` 中实现，但没有放在公共头文件中声明。新版 GCC 对隐式函数声明处理更加严格。

处理：

在 `Src\platform\user_periph_setup.h` 增加：

```c
void gpio_init(void);
uint8_t charge_ic_init(void);
```

其中 `charge_ic_init()` 是同一轮编译中发现的另一个缺失声明，也一并补充。

## 3. 后续编译错误及处理

### 3.1 `strcmp()` 未声明

文件：`Src\user\log_cmd.c`

错误：

```text
implicit declaration of function 'strcmp'
```

处理：

增加标准头文件：

```c
#include <string.h>
```

### 3.2 QPC 的 `QActive` 类型转换错误

文件：`Src\user\cat1svr.c`

错误：

```text
expected 'QActive * const' but argument is of type 'QAsm *'
```

原因：

`QACTIVE_POST()` 要求传入 `QActive *`，原代码通过 `Q_ASM_UPCAST(me)` 得到的是 `QAsm *`，GCC 15.2.1 不再接受该隐式类型转换。

处理：

将：

```c
QACTIVE_POST(Q_ASM_UPCAST(me), &pe->super, 0U);
```

改为：

```c
QACTIVE_POST((QActive *)me, &pe->super, 0U);
```

### 3.3 `QTimeEvt` 被错误转换成 `QActive *`

文件：`Src\user\sensor.c`

错误：

```text
expected 'QTimeEvt * const' but argument is of type 'QActive *'
```

原因：

`sample_clk` 实际类型是 `QTimeEvt`，但原代码把它转换成了 `QActive *` 后传给 QPC 定时器函数。

处理：

将定时器参数改为实际类型：

```c
QTimeEvt_ctorX(&DA221_inst.sample_clk,
               (QActive *)&DA221_inst,
               DA221_MOTION_INT_SIG,
               0U);
QTimeEvt_armX(&DA221_inst.sample_clk,
              BSP_TICKS_PER_SEC / 5U,
              BSP_TICKS_PER_SEC / 5U);
(void)QTimeEvt_disarm(&DA221_inst.sample_clk);
```

### 3.4 I2C 回调函数原型不匹配

文件：`Src\user\sensor.c`、`Src\user\sensor.h`

错误：

```text
expected 'app_i2c_evt_handler_t'
```

原因：

SDK 定义的 I2C 回调原型是：

```c
typedef void (*app_i2c_evt_handler_t)(app_i2c_evt_t *p_evt);
```

原项目回调多带了一个 `DA221 *` 参数，不能直接传给 SDK。

处理：

将回调函数统一为：

```c
void DA221_i2c_evt_handler(app_i2c_evt_t *p_evt);
```

并同步修改 `.c` 和 `.h` 中的声明及定义。

## 4. Windows 下 Makefile 兼容处理

文件：`ble_app_uart_c\GCC\Makefile`

处理内容：

- Windows 下使用 PowerShell 创建 `out`、`out\obj`、`out\lst` 目录。
- Windows 下使用 PowerShell 清理输出目录。
- 去除对 Unix `head` 命令的依赖。
- Windows 下关闭可能导致命令拼接异常的回显前缀。
- 保留 GCC、ASM、链接和 BIN/HEX 生成流程。

## 5. 编译命令

在 PowerShell 中执行：

```powershell
cd D:\CODEX\sos-card
$env:Path = "D:\CODEX\sos-card_toolchains\runtime\arm-gcc-xpack\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin;D:\CODEX\sos-card_toolchains\runtime\mingw\mingw64\bin;$env:Path"
mingw32-make -C ble_app_uart_c\GCC all
```

如需清理后重新编译：

```powershell
mingw32-make -C ble_app_uart_c\GCC clean
mingw32-make -C ble_app_uart_c\GCC all
```

## 6. 最终验证结果

最终 Make 返回：

```text
退出码：0
```

生成文件：

```text
ble_app_uart_c\GCC\out\ble_app_uart_c.bin
ble_app_uart_c\GCC\out\ble_app_uart_c.hex
ble_app_uart_c\GCC\out\lst\ble_app_uart_c.elf
ble_app_uart_c\GCC\out\lst\ble_app_uart_c.map
```

最终内存统计：

```text
text：191724
data：64
bss ：50128
```

## 7. 文件用途

- `.bin`：通常用于烧录固件。
- `.hex`：部分烧录工具使用的 Intel HEX 格式固件。
- `.elf`：调试、符号和地址分析文件，不能在 Windows 上直接运行。
- `.map`：链接地址和内存分布分析文件。

## 8. 当前结论

GCC 项目已经完成一次完整编译，源码编译、链接以及 BIN/HEX/ELF/MAP 生成均成功。

链接阶段仍有 SDK 绝对地址符号相关 warning，但没有导致构建失败。这些警告来自 SDK 的固定地址/ROM 符号链接机制，不等同于编译错误。

本次没有进行烧录、下载或硬件运行验证，因此当前结论是：

```text
GCC 静态编译通过，固件硬件运行尚未验证。
```

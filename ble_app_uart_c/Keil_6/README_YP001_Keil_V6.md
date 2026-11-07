# YP001 GR5526 Keil V6 / Arm Compiler 6 工程

工程文件：`YP001_GR5526.uvprojx`

## 打开与编译

1. 在 Keil µVision V6 中打开本目录的 `YP001_GR5526.uvprojx`。
2. 选择 Target `YP001_GR5526_AC6`，工具链使用 Arm Compiler 6；本工程最近验证版本为 V6.14。
3. 日常修改后执行 **Project → Build Target** 或按 F7。工程已配置 `YP001_BOARD`、GR5526 SDK include、官方 Keil BLE 库、Keil Startup.S、Armclang QP/C port 和项目专用 scatter 文件。

若 `Objects` 曾被清理，必须先按 F7 重新生成 `Objects/YP001_GR5526.axf`，再点下载；直接下载会报无法加载 AXF。

## 后续交付检查项

- [ ] 主工程与交付副本的 `.uvprojx`、`.sct` 和下载参数保持一致；两边分别运行 `验证Keil6交付.ps1`。
- [ ] 在实际交付副本中用 Keil 6 编译，记录错误/警告数，并确认 `Objects/YP001_GR5526.axf` 与 `.hex` 存在。
- [ ] 下载时单独记录 `Programming Done`、`Verify OK` 和板上启动结果；编译成功不代替下载验证。
- [ ] 清理时只删除 `.o`、`.d`、`.dep`、`.lnp`、`.htm`、`.lst`、`.map` 等中间文件。保留 AXF/HEX、工程配置、scatter、Flash 算法和下载日志；清理前后核对 AXF/HEX 哈希，再运行交付检查。若确需删除 AXF/HEX，必须明确标记“下载前先按 F7 重建”。

最近验证：Keil AC6 编译 0 错误、0 警告；J-Link 下载出现 `Programming Done` 和 `Verify OK`。LVGL 字形修复后，从 GR5526 RAM 读回的 200×200 帧缓冲字形正确，用户已确认实物屏幕与帧缓冲一致。开机 LOGO 保留。

## J-Link 调试/下载连接

- `YP001_GR5526.uvprojx` 与 `.uvoptx` 的 Flash 编程器均改为 `GR5xxx_16MB_Flash.FLM`，Flash 区间为 `0x00200000` 起、`0x01000000` 长；算法文件使用 Keil 安装目录中的 GR5xxx FLM。
- 每位开发者应在 **Options for Target → Debug → Settings** 选择自己的 J-Link，接口设为 **SW**，频率为 **1 MHz**。
- 在 Debug 的 Initialization File 中选择 `ac6_debug.ini`：脚本复位并加载当前 Target 的 `%L`（AXF），再初始化栈指针和向量表。
- 在 **Options for Target → Debug → Settings** 确认接口为 **SW**，频率为 **1 MHz**。只在 SWD/CoreSight 能识别 Cortex-M4 后再执行下载。
- 若日志已出现 `Found Cortex-M4` 与 CoreSight ROM table，但仍报错，请看后续 Build Output：之后出现的错误可能属于复位、加载脚本或 Flash 算法阶段。若日志仍是 `Could not find core in Coresight setup`，再检查板卡供电与 J-Link VTref、GND 共地、SWDIO、SWCLK、NRST 连接及复位状态。
- 如果 µVision 找不到 `GR5xxx_16MB_Flash.FLM`，将交付包内 `Tools/GR5xxx_16MB_Flash.FLM` 复制到 Keil 安装目录的 `ARM/Flash` 后重新打开工程。

## 工程核对

- 芯片宏由 `Src/config/custom_config.h` 提供 `SOC_GR5526`。
- 编译宏：`ENV_USE_FREERTOS`、`TK_Board_UART_DBG=1`、`YP001_BOARD`。
- QP/C 的通用端口头文件与 `qv_port.c` 均指向 `arm-cm/qv/armclang`；AC6 C 参数明确指定 `-std=c99`，以支持 SDK/QP/C 使用的 C99 语法。
- AC6 汇编选项设为 armasm 兼容模式（`ClangAsOpt=0`），以匹配 SDK `Startup.S` 的 ARMASM 语法；设为 Clang GNU 汇编时会将 `IF/AREA/DCD` 等指令报成大量错误。
- LVGL 8.3.1 源码位于 `Src/external/lvgl_8.3.1`，配置为 200×200 单色软件绘制；`Src/user/gui/epaper_lvgl.c` 将 LVGL 输出转换为 DEPG0150 的 5000 字节帧。字形按字节对齐行跨度修正。开机 LOGO 仍走原有显示流程。
- 项目专用 `YP001_GR5526.sct` 将应用放在 `0x00202000`、应用信息放在 `0x00202200`，并按 Goodix AC6 scatter 布局将 `RAM_CODE` 放在 `0x00106000`、数据区放在 `0x2000B000`。
- 当前限制：`ble_scanner_start()` 会在 YP001 上触发 INVSTATE HardFault，因此扫描暂时关闭；BLE 栈初始化返回 0 不代表扫描工作正常。告警和电池数据尚未接入，界面显示 `--`。UART0 为 115200 8N1。

若首次构建报错，请把 Keil Build Output 从首个 error 到结束完整贴回；不要用旧 HEX/BIN 判断本次构建结果。

# YP001 蓝牙 DTM 方案 2：CAT1 PWRKEY 自动开机修改说明

## 本轮范围、原因和结果

上一版方案 2 只将 GR5526 GPIO6 置高，请求 CAT1 电源；CAT1 仍未开机。现版独立 DTM 固件在蓝牙 HCI 初始化前，先释放 AON_GPIO0/Q4 控制的 CAT1 第 7 脚 PWRKEY，再置高 GPIO6 供电，等待 200 ms，按下 PWRKEY 1600 ms，最后释放。上述极性和时序分别对照当前 YP001 硬件映射、产品板 `yp001_board_config.h` 与 `gpio_test.c`。GPIO 初始化或写入失败时，不继续进入 HCI。CAT1 调试继续使用模块自身 USB；此固件不初始化 GR5526 CAT1 UART4，也不发送 AT。

| 文件/函数 | 修改前 | 修改后及原因 |
|---|---|---|
| `SDK/projects/ble/dtm/yp001_ble_dtm/Src/user/main.c`，`cat1_power_and_start_for_usb()`/`main()` | 只置高 GPIO6，未操作 PWRKEY | 在方案 2 构建宏使能时追加 AON_GPIO0 释放-按下-释放，保证软件发出开机请求；失败则停在错误循环。代码旁标注 `SAM | 2026-10-12 19:06 +08:00` |
| `tools/ble_dtm_factory/方案2_电脑手动控制/固件/` | 仅供电的旧 HEX/BIN | 换成本轮 GCC 构建的 PWRKEY 自动开机 HEX/BIN，应用起点仍为 `0x00202000` |
| 方案 2 `使用说明.md`、`使用说明.pdf`、`SHA256SUMS.txt` 和总 `README.md` | 文档明确写着不操作 PWRKEY | 写明真实开机时序、冷启动/重复脉冲注意点及新包入口，防止工厂误用旧版 |

方案 1 原版固件与工具 EXE 未修改。两份产品工程 `ble_app_uart_c`、`SVN交付_YP001_GR5526_20261001/ble_app_uart_c` 本轮没有改动，也没有覆盖任何既有未提交文件；`Air780EGH` 仅为允许的 CAT1 项目入口，没有从旧 CAT1 目录读取或复制代码。现版仍是蓝牙 DTM 测试固件，不是产品固件。

## 构建与静态校验

- 独立 GCC DTM 工程执行 `mingw32-make -B -j 1 BUILD=out_cat1_boot CAT1_POWER_ON_BOOT=1 V=0`，退出码 0；日志 `SDK/projects/ble/dtm/yp001_ble_dtm/GCC/build_cat1_boot_20261012.log`。日志未见 `error:`，有 894 条 `warning:`，主要是既有 SDK ROM 绝对符号/GCC 链接警告；不能据此声称实板启动成功。
- 检查 ELF `main` 反汇编：先初始化/释放 AON_GPIO0，随后 GPIO6 供电，再分别调用 `delay_ms(200)`、PWRKEY 置高、`delay_ms(1600)`、PWRKEY 置低，之后才进入 `ble_hci_uart_init()`。
- 新 HEX SHA-256：`97E7F6F37364BD2787D23182E60C4FFEEE6BFC0AF00CD58DDB56E70DBDB99150`；新 BIN SHA-256：`018128C90DFF20C1A72319F6F9A315CFF25513B28E54B66B2AFCEC175E2187B3`。Intel HEX 逐行校验和有效，范围 `0x00202000–0x0021D7D7`；HEX 含 106192 个数据字节，BIN 长 112600 字节，所有 HEX 字节与 BIN 同址一致，6408 个 HEX 间隙在 BIN 中为 `0x00`。
- 方案 1 HEX SHA-256 仍为 `192ED9332B7C93A2255D211DE56E7EBAC8609231E120FDFBD05A66FD41453603`。
- 方案 2 PDF 为当前 Markdown 的打印版，2 页，已渲染查看中文字形、换行和页脚。ZIP 内文件、清单哈希的最终复核结果见下方交付记录。

## 实板边界与交付

本轮没有下载固件、测电压或示波器波形，不能确认 CAT1 第 7 脚实际出现有效脉冲、CAT1 已开机或 USB 已枚举。若 CAT1 因 USB 在 GR5526 单独复位后仍运行，重复 PWRKEY 脉冲可能把模块关机，首次测试应从冷启动开始并观察 USB 枚举。首次实板应测 GPIO6、CAT1 VBAT、PWRKEY 第 7 脚波形，再确认 CAT1 USB 下载；蓝牙 HCI 和暗室 TX/RX 仍需分别验收。

当前只有产品板、没有该板确切可恢复产品镜像，且拟电池与 USB/5V 同接。DTM 测试镜像没有产品 ETA69631 禁充初始化；现阶段不可按该接法在当前板烧写。先取得可恢复镜像及专用样机，断开电池并验证 5V 路径和 SCA/实际擦除范围，再安排上板。旧 `CAT1上电` ZIP 保留为历史包；新版交付包名为 `YP001_蓝牙天线暗室测试_方案2_CAT1自动开机_待样机验证_20261012.zip`。

## 强制检查项逐项记录

| 检查项 | 结果/证据 |
|---|---|
| 修改前工作区和目标文件检查 | 查看 `git status`、独立 DTM `main.c`、Makefile、方案 2 旧包及说明；大量既有未提交/未跟踪内容均保留 |
| 主工程/交付副本差异检查 | 两份产品板 `yp001_board_config.h` 哈希均为 `5A09C1EA6EB2D66218678E13C24C6820A701ADD3B594C6E2C9BBF8720ABE4C11`；本轮不改产品工程，因此无同步/覆盖 |
| 硬件与启动路径 | 当前板 GPIO6 高请求 CAT1 供电；AON_GPIO0 经 Q4 反相到 PWRKEY；按产品手动开机 200/1600 ms 时序；复位重入及 USB 维持 CAT1 运行的风险已写说明 |
| 代码时间/修改人/原因注释 | `main.c` 改动附近有 `SAM | 2026-10-12 19:06 +08:00` 和原因；Makefile 复用上一版已标注的开关 |
| 清理脚本及下载配置 | 未修改 `keilkilll.bat`、`Invoke-KeilClean.ps1`、Keil 项目、Flash 算法；未执行清理、擦除或下载 |
| 本轮中文修改说明 | 本文件，并给上一轮供电说明添加历史版本提示 |
| 主工程 Keil 6 编译 | 未执行；产品工程源码未修改，本轮目标是独立 GCC DTM 方案 2，重编产品工程会改写现有产品 AXF/HEX |
| 交付工程 Keil 6 编译 | 未执行；交付副本源码未修改，理由同上 |
| 静态/主机校验 | 独立 GCC 全量构建、ELF 反汇编、HEX 校验和及 BIN 同址核对、方案 1 哈希、PDF 渲染、ZIP/清单核验 |
| 实板测试及未完成项目 | 未烧写；CAT1 VBAT/PWRKEY/USB、蓝牙 HCI/TX/RX、恢复产品固件和身份数据保留均未验收 |

## 交付记录

`tools/ble_dtm_factory/YP001_蓝牙天线暗室测试_方案2_CAT1自动开机_待样机验证_20261012.zip` 包含 6 个文件，解包数据与方案 2 当前目录逐字节一致；`SHA256SUMS.txt` 对 EXE、HEX、BIN、MD、PDF 共 5 项逐项通过。ZIP SHA-256 为 `666999EFA9344CFD4FAD6D9B3F5D84B9F0DBD3B6D71EA11B6ED51F008EE67107`；清单 SHA-256 为 `518E8DCA5C2326ED8664BBE3690F81C850B8C53C0E6C128CDF7D3E1E4BB6FA39`。

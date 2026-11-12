# GR OTA 最小 Boot 的 SDK 交接适配

SAM | 2026-10-21 +08:00 | 将上一轮交接接口接到SDK1.0.4真实符号，在隔离工程验证，不开放安装或设备跳转。

## 本轮实现

新增 `tools/ota/boot/yp001_ota_sdk_handoff.c/.h`，`yp_boot_minimal_sdk_handoff()`返回可信回调，取得回调本身无硬件操作。正式使用必须通过已有 `yp_boot_start` 的验签/恢复/向量检查链，不能直接调用回调绕过检查。

- quiesce：调用 `bootloader_wdt_refresh()`，再调用 `app_periph_deinit()`。
- jump：再次喂狗，再调用 `sys_firmware_jump(A物理地址, 正文长度)`。正文不含904字节签名尾部。
- 若SDK跳转返回：调用 `hal_nvic_system_reset()`。如果复位请求仍返回，停在不喂狗的循环中，不能返回已拆除外围的业务环境。
- 编译门：UART DFU、BLE DFU、总DFU、日志均须关闭，看门狗必须开启；缺少这些配置定义也拒绝编译。

这些回调只支持当前单线程最小Boot，使用前必须完成 `app_periph_init`，所有同步Flash/验签操作已结束且没有后台写入或DMA。未来增加外围不能直接沿用该适配。

## 依据与尚未解决的硬件边界

活动SDK `SDK/components/libraries/app_bootloader/bootloader_boot_vendor.c` 的 `app_bootloader_jump` 明确先反初始化后 `sys_firmware_jump`。隔离工程 `Src/platform/user_periph_setup.c` 当前开启加密时钟、看门狗及SysTick；UART/BLE下载和日志关闭。其 `app_periph_deinit` 停止SysTick，不关闭看门狗。适配保持这一路径，不另行猜测PRIMASK/VTOR/NVIC寄存器操作。

`sys_firmware_jump` 的中断/上下文交接委托SDK。链接Map已确认使用活动SDK `system_sdk_patch.o` 的真实符号，并链接真实系统复位函数；不是只链接了主机假函数。但这不能证明实板已成功跳转。

生产应用 `ble_app_uart_c/Src/platform/bsp.c:BSP_init` 中看门狗初始化在业务/OTA初始化及部分外围初始化之后。因此从Boot跳转至应用接管看门狗之间的耗时、初始化结果与潜在超时仍需核对和实测。本轮没有修改生产启动次序，也没有关闭看门狗来规避问题。

Boot自身的看门狗初始化返回值目前由已有参考初始化代码忽略，尚未补充成功证据；新适配的quiesce返回0只表示已调用这个void反初始化函数，不宣称所有外围硬件状态已读回确认。

## 测试与构建证据

新增 `tools/ota/test_gr_sdk_handoff.c/.py`，先运行观察到适配文件尚不存在的编译失败；实现后通过：

1. 获取回调不触发硬件操作。
2. 用SDK形状的测试桩验证喂狗→反初始化→喂狗→跳转→复位顺序，以及地址/长度传递。
3. 模拟跳转返回，以longjmp截获复位请求；测试不执行硬件复位，也未证明实际看门狗能救援。
4. 五个不兼容配置逐一编译失败，且命中预期编译门。

重新执行 `test_gr_flash.py`，原启动交接、Flash故障与SDK尾部大小测试通过。

隔离工程增加适配源文件和函数指针保留探针。探针不取得、不调用硬件回调，main仍未调用选择器或跳转。Keil进程退出0，0错误/0警告；日志：`logs/ota_preflight_20261021/boot_sdk_handoff_build.log`。

| 隔离Boot容量 | 字节 |
|---|---:|
| Code | 32256 |
| RO | 352 |
| RW加载数据 | 2204 |
| ZI运行数据 | 30032 |
| Code+RO+RW | 34812 |
| 加904字节尾部预算 | 35716 |
| 36KiB区内余量 | 1148 |

AXF SHA256：`B81A116C70359A4A52AA506806107EE586BD020C36022C6A3F1817CEACD12515`。文件仍为 `DO_NOT_FLASH_boot_high.axf`，禁止烧录。

当前主工程HEX与新Map的 `check_layout.py` 通过候选容量检查；应用槽估算余792字节，仍为 `layout_approved=false`、`install_enabled=false`。容量余量已很小，后续新增后端必须重新测量，不能以裁掉安全检查或移动用户区解决超限。

## 强制检查与下一步

| 项目 | 结果 |
|---|---|
| 范围/工作区 | 新增候选适配和主机测试，局部修改隔离工程及探针，保留业务代码 |
| SAM标注/中文说明 | 已在新增文件及探针附近标注，本文记录 |
| 主工程/交付副本 | 未修改生产源码及配置，无需同步；未将旧HEX称作新产物 |
| 两份生产编译 | 不适用本轮；仅隔离工程编译通过 |
| SDK/清理/数据 | 未修改SDK、清理脚本或Flash布局；未写用户数据；无Git/SVN操作 |
| 要求保持 | F-031/F-032、双端串行、固定70%及安全条件不变，安装继续禁用 |
| 实板验收 | 未连接、烧录、擦除、重启；跳转、中断、看门狗连续性均未实测 |

下一步先处理长时间扇区交换/验签期间的看门狗服务与启动接管边界，再接可信包、首次初始化、持久协调和健康确认。不能仅因SDK跳转已链接就把独立Boot或完整OTA标记完成。

# UART0 日志追踪

当前工程：`Keil_6/YP001_GR5526.uvprojx`，目标 `YP001_GR5526_AC6`。

- UART0 TX：GPIO28，QFN68第59脚，GPIOB PIN12，MUX2。接USB转TTL的RX。
- UART0 RX：GPIO29，QFN68第60脚，GPIOB PIN13，MUX2。接USB转TTL的TX；只收日志可不接此线。
- 共地，电平匹配板上IO电压；115200、8数据位、无校验、1停止位、无流控。
- 开机直出banner、printf、APP_LOG和CLI共用UART0。CAT1仍使用UART4。
- 先打开串口采集，再复位上电；保存完整原始日志。

预期第一条为 `=== YP001 GR5526 BOOT / UART0 ===`，随后有管脚/串口参数和编译日期时间；启动阶段显示RTC、CLI、GPIO、QP对象、BLE初始化返回值及进入QF_run。编译时间表示该源文件最近一次编译时间，不替代固件版本号或哈希。

运行日志默认开启；现有CLI日志开关仍可关闭普通日志，CLI强制输出不受它影响。本次已核对源码路由，未编译、下载或实测串口。请用Keil AC6重新Build并下载后采集。

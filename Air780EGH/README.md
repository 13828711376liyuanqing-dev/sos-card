# Air780EGH 当前 CAT1 项目

用户于 2026-10-10 指定：此目录是 CAT1 代码、底包和后续调试的唯一项目来源。不要从旧目录加载、复制、合并或打包项目内容。

- 入口：`main.lua`，初始化 UART1 和既有业务，注册 `antenna_test.lua`。
- 串口：`uart_app.lua`，UART1 460800 / 8N1，CRLF 文本命令。
- 4G＋GNSS 天线任务：`antenna_test.lua`，支持 `AT+ANTSTART=ALL,2`、`AT+ANTSTOP`、`AT+ANTSTATUS`；也支持 LTE/GNSS 单独模式。
- 底包文件：`soc/LuatOS-SoC_V2052_Air780EGH_113.soc`。文件名不是当前模块烧录版本的实测证明；不要因历史代码注释而替换底包。
- 其它业务文件保持本目录现有版本。`sys`、`exgnss` 等系统库由适配的 LuatOS 固件提供；查官方 API 不表示可切换项目来源。

PC 上位机在 `D:/CODEX/sos-card/tools/cat1_antenna/bin/CAT1Antenna.exe`，经汇顶 UART0（115200）→ UART4（USB烧写完成后手动设置460800）连接模块。完整使用及验收说明见 `../doc/2026-10-10_CAT1双天线调试整合说明.md`。

本轮只完成主机软件测试和固件编译，尚未下载两端程序或验证实板天线效果。

当前流程：汇顶只供电 → USB烧写本目录底包/Lua → 手动AT；见 `../doc/2026-10-10_CAT1先供电后USB烧写说明.md`。

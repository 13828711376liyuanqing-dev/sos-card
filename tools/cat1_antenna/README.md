# CAT1 双天线调试台（Windows）

SAM | 2026-10-10 16:53 +08:00 | 新增本地上位机，供 4G 主天线与 GNSS 天线对比采集使用。

## 运行与连接

CAT1 项目代码唯一来源：`D:\CODEX\sos-card\Air780EGH`。更新模块时必须包含该目录新增的 `antenna_test.lua` 和本轮修改的三个 Lua 文件，并沿用同目录其它业务文件及底包；不要从旧目录取文件。汇顶新 HEX 与 CAT1 新脚本均需安装才能联调。

运行 `bin\CAT1Antenna.exe`。需要 Windows 桌面环境、.NET Framework 4.x、串口驱动，以及当前用户 LocalAppData 写权限；本机编译/渲染已验证，其他电脑与实板仍需验收。无网络依赖、不需要 Python，不会自动连接设备。

1. 先用 Keil 下载汇顶只供电固件，再通过 USB 给 CAT1 烧入 Air780EGH 底包和 Lua。完成后连接 GR5526 UART0，选择 COM26（115200/8N1）；连接本身不发送任何命令。手动点“恢复串口 460800”（先115200再460800重新初始化UART4），再“查询状态”。
2. 需要时点击 CAT1 上电。确保 4G 主天线、GNSS 天线各自正确接入，并使用适配本协议的模块程序。
3. 填写天线编号，选择 ALL / LTE / GNSS 与 1–60 秒间隔，点击开始采样。只有模块 `[ANT] ... type=ACK op=START ok=1` 到达才显示采集中。GR5526 TX 成功不代表模块接受。
4. 停止按钮在 START/STATUS 等待或超时后仍可下发 STOP；只有收到 STOP ACK 才显示“已停止”，5 秒未收到则显示“停止未确认”。其他命令超时后，先查询状态并取得有效 STATUS 回执，才能再次开始采样。断开串口不会关闭模块或保证停止采样；重连清空旧状态及指标。
5. 模块命令框通过 `cat_at` 桥接，支持单行可打印 ASCII，最多 478 字节、7 个空格分隔文本段。启停/状态命令同样走 ACK 等待。

## 数据与日志

每次连接自动创建 `%LOCALAPPDATA%\CAT1Antenna\sessions\<时间_唯一编号>`，界面显示实际位置，点击目录文字可打开文件夹。`raw.log` 带本机时区时间戳，保存所有原始 TX/RX（包括 MCU 噪声）；`samples.csv` 逐帧刷新，保存时间、当前天线编号、指标和原始模块帧。文件创建或写入失败明确弹出错误并断开，不静默丢失。天线编号修改影响随后收到的行。

NA 表示未知/无支持；CSQ=99、非法数字、NaN/Infinity、未定位经纬度均显示并导出 NA，原始帧保留原值。LTE 注册状态保留原始数值；1/5 分别为本地/漫游注册。超过 max(10 秒, 模块 ACK 确认间隔×3) 未更新显示过期；周期尚未确认时按 2 秒计算。编辑间隔控件不会改变旧测量的有效期；START/STATUS 的有效 ACK 才更新采样周期。TTFF 为本轮启动至首次有效定位，不代表清除星历后的冷启动指标。GNSS 原始 SNR 最大值来自 GSV，单位尚未核实，不冒充 CN0；CSV 额外保存 snr_max。模块现有固件/API 是否能提供字段，以模块回传为准。

协议 v1 不带事务编号。超时后查询状态用于重新同步顺序；跨模块重启、异常乱序或极端延迟仍须结合原始日志判断，不能把本机测试当实板验收。

## 离线构建与验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
.\bin\CAT1Antenna.exe --render-preview C:\path\desktop-preview.png
```

构建使用 Windows 自带的 `Microsoft.NET\Framework64\v4.0.30319\csc.exe`，先编译运行 `bin\DesktopTests.exe`，再输出 WinForms EXE。预览只渲染实际窗体，不开串口、不生成测量日志；旁边 `.txt` 保存模式控件状态。主机测试使用 `%TEMP%\CAT1Antenna_HOSTTEST_*` 隔离日志目录，不与真实会话混合。

测试覆盖分块行、未知字段/类型/版本、缺失和无效数值、CSQ=99、失去定位、坐标边界、超长行恢复、ACK 超时/重新同步、断开状态、旧 ACK、数据过期、CSV 转义和实际日志写入/路径失败。串口硬件、拔插、双端波特率、4G 注册与 GNSS 定位仍需实测。


Lua 协议夹具验证：从仓库根目录执行 `tools\cat1_antenna\bin\DesktopTests.exe logs\cat1_antenna_20261010\lua-protocol-fixture.txt`，将 Lua 桩运行生成的原始串口行按 7 字符分片送入同一解析器，验证 START、LTE、GNSS 未定位/已定位、STATUS 与 STOP 顺序。



## 2026-10-10 用户确认：只供电，USB烧写后再AT

汇顶启动仅请求 CAT1 供电，PWRKEY保持释放，不初始化UART4、不自动探测、不切换波特率。上位机连接不发命令；“CAT1上电”按钮也仅打开电源。USB烧写期间不要点击关电/按键或复位汇顶。烧写后手动设置460800，再查询状态或开始采样。

详见 `../../doc/2026-10-10_CAT1先供电后USB烧写说明.md`。

## 烧写后串口恢复实测（2026-10-10）

本机有多个串口：CAT1 USB 为 COM21/22/23，汇顶 UART0 当前是 COM26。界面不预选首个串口，请手动选择汇顶 UART0。连接本身不发命令。点“恢复串口 460800”会在 PC UART0 115200 上顺序发送 `cat_baud 115200` 和 `cat_baud 460800`，让汇顶 UART4 RX 驱动重新初始化；不会重启 CAT1，也不更新 MCU。随后点击“查询状态”，必须看到 `type=ACK op=STATUS ok=1` 才开始采样。该恢复序列在当前实板上使 LTE、GNSS、ALL 的 START/采样/STOP 回执恢复，根因仍需用 UART 波形与原始字节确认。出现 `binary_or_long_line_discarded` 时停止采样后按同序列恢复，不能把丢弃的行当有效指标。

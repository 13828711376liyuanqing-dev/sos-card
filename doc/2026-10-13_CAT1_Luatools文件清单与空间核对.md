# CAT1 Luatools 文件清单与空间核对

SAM｜2026-10-13｜仅准备本地脚本发布副本和只读空间核算；未打开 Luatools、未下载模块、未改原 `.soc` 或用户数据。

## 结论

`Air780EGH` 原始 Lua 和音频直接全选时，本次生成快照中的 30 个 Lua 加音频共 **548,331 字节**；这已经超过旧截图中 Luatools 显示的 512 KiB 脚本容量。原代码在 `Air780EGH` 保持不变。本轮新增[准备脚本](../tools/ota/prepare_cat1_luatools.py)，只在发布副本中删除 Lua 注释并保留代码、字符串和音频文件。发布副本的 30 个 Lua 共 **294,749 字节**，连同 `sample-6s.mp3` 共 **397,819 字节**；对 524,288 字节容量的**原始字节余量为 126,469 字节**。Luatools 的编译、索引、文件系统开销及其界面“已使用”值仍需在工具中读取，不能把原始字节余量写成模块实际剩余空间。工作区仍在变化，若重新生成，以最新 manifest 数字为准。

此前工具截图记录“512 KB/已用506 KB”，那是旧文件列表成功下载后的结果，并非这次发布副本的实际打包值。本机检查时 Luatools 未运行，也没有找到可读取的原项目文件清单或已保存的工具配置；因此没有擅自修改工具项目。通过下面的路径可以在原项目中明确替换文件列表后读取真实空间值。

## Luatools 应选择的文件

1. 保留原项目板型 Air780EGH；底包指向[原 `.soc`](/D:/CODEX/sos-card/Air780EGH/soc/LuatOS-SoC_V2052_Air780EGH_113.soc)。本轮没有重新制作或验证底包。
2. 清掉 Luatools 项目脚本**选择列表**里先前来自 `Air780EGH` 的同名条目，再从[发布脚本目录](/D:/CODEX/sos-card/logs/cat1_luatools_20261013/package)加入全部 **30 个 `.lua` 和 1 个 `sample-6s.mp3`**。这只是工具项目的选择列表操作，不删除模块用户区或原项目源码；避免同时选原文件和压缩副本形成同名冲突。
3. 用[精确文件列表](/D:/CODEX/sos-card/logs/cat1_luatools_20261013/luatools-file-list.txt)逐项核对；[manifest.json](/D:/CODEX/sos-card/logs/cat1_luatools_20261013/manifest.json)含每个原文件与发布副本 SHA256、大小、底包路径和预算。入口必须是发布目录的 `main.lua`，另外五个 `ota_*.lua` 均需在列表中。
4. **先查看 Luatools 计算的“已使用/总空间”并确认没有缺文件、同名、编译报错，再决定是否下载。** 这一步的真实数值未取得，不能凭本文件直接认定烧写一定成功。

本轮文件集合基于 2026-10-12 OTA 修改前快照的原 22 个 Lua，加五个 OTA 模块：`ota_store.lua`、`ota_manager.lua`、`ota_download.lua`、`ota_runtime.lua`、`ota_platform.lua`。原音频仍包含，因为 `audio_drv.lua` 使用 `/luadb/sample-6s.mp3`。准备过程中同一工作区的另一组业务代码更新了 `main.lua` 和 MQTT 接收链：入口现已要求 `business_runtime.lua`，它又要求 `business_core.lua`、`business_store.lua`。准备脚本逐层检查本地 `require`，因此这三份也纳入当前30文件清单；源码在生成期间若变化会失败退出。**这三份是并行工作中的新业务代码，本轮只确认语法和文件依赖，没有替其完成功能验收；若它们继续变化，需要重新生成并复查。**

## 校验与限制

- 准备脚本对每个原 Lua 和发布 Lua 都调用本机 Lupa Lua 5.4 `load` 做语法检查；替换注释为空格/换行，保留字符串原文。它不替代 Air780EGH 上 LuatOS 实机启动、内存和业务测试。
- [独立校验脚本](../tools/ota/verify_cat1_luatools.py)已通过：30 个 Lua 与音频的文件集合、哈希、源码快照和“仅删除注释”转换完全一致。源码更新后先重新生成，再运行此校验；若失败，不使用旧发布副本。
- 重新执行 `python tools/ota/prepare_cat1_luatools.py` 会依据当前原源码再生成副本；如源码有独立修改，先对照 manifest 的哈希、入口 `require` 和项目文件列表，再使用新产物。
- 当前 OTA 产品端口仍缺签名、可信版本映射、真实 HTTP 与厂商激活/GR写槽能力。成功加载这套脚本也只能先测启动、SIM注册和原有业务，不能宣称双端OTA可升级。
- 本轮没有连接设备，也没有修改/清空用户已有设置、绑定、事件和其他数据。模块实际烧写范围、原脚本覆盖及数据区保留仍应由 Luatools 显示和实板读回验证。

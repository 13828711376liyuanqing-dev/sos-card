---
name: yp001-space-budget
description: YP001 whole-device OTA space control — the five size limits (GR payload 441464, CAT1 LuaDB 524288, .sota 524288, zip 2 MiB, CAT1 free space), which standalone tool checks which, how to read the CAT1 free space with `cat_at OTA_FS` on COM26 and fill it into the OTA pack tool, what to do when near a limit. Use when the user asks about 空间/大小/超限/可用空间/OTA_FS/COMPONENT_SPACE, before packaging a new OTA, or when a build is close to the slot size.
---

# YP001 OTA 空间预算与检查

## 红线（SAM | 2026-11-04，用户要求；超红线一键工具停止打包）
配置 `tools/toolkit/budget.json`（组装时复制到工具包根目录；只改这里，写 `_history`），检查 `tools/ota_oneclick/budget.py --gr-hex <HEX> --cat1-src <源码> [--free N]`，说明 `doc/2026-11-04_OTA空间红线_GR与CAT1大小管控.md`。
- GR 签名镜像 ≤ **393216**（384 KiB，从 CAT1 文件区倒推：512 − 常驻 96 − 保留 16 − 余量 16），黄线 376832。
- CAT1 LuaDB ≤ **507904**（留 16 KiB），黄线 499712；.sota ≤ 262144。
- OTA 时 CAT1 可用 ≥ GR 签名镜像 + **32768**（以前是 +16384）。
- 常驻（预检已用，含日志）预算 24 块，超了只提醒；每版增长 > 4 KiB 提醒并写原因（对比 `state.json` 的 `last_success.sizes`）。
- 1.5.10 基准：GR 372968、LuaDB 495674、.sota 188072；离红线 GR 20248、LuaDB 12230。下面"五个限制"是硬上限，仍有效。

给同事看的完整说明：`doc/2026-10-30_空间预算与检查_给同事.md`。这里是操作版。

## 五个限制与检查者
| 限制 | 数值 | 检查 |
|---|---|---|
| GR 固件正文 | ≤ 441464 B（槽 442368 − 签名 904） | 2 号工具 Gr5526Tool "检查"，3 号工具打包再查 |
| CAT1 脚本 LuaDB | ≤ 524288 B | 1 号工具 Cat1UsbImport（余量 < 2 KiB 警告） |
| CAT1 升级包 .sota | ≤ 524288 B | 3 号工具 ① |
| 整机 zip | ≤ 2097152 B | 3 号工具 ③ |
| CAT1 文件区可用空间（设备实际） | ≥ 已签名 GR 镜像 + 904 + 16384 且 ≥ .sota + 16384；最大门槛 459656（槽 442368 + 904 + 16384） | 3 号工具 ③，**数字由人读设备后填** |

## 读 CAT1 可用空间（唯一要人填的数）
1. 板子接电脑，COM26 115200，发一次 `cat_at OTA_FS`（只读）。GR 监控窗口期间不要轮询，先征得用户同意，确认 COM26 没被占用。
2. 返回 `total= used= block=`；可用 = (total − used) × block，例 (128−15)×4096 = 462848。
3. 填入 3 号工具"CAT1 可用空间（字节）"。
- 不估算、不抄旧值、不填门槛值 459656（检查必过=没检查）、不填大。上限是文件区总容量 total×block，且只会越用越少。
- 读数 < 门槛：清理设备文件或减小脚本，不是改数字。
- 事故：10-29 第二轮真实可用 450560，手填 495616，设备报 COMPONENT_SPACE。

## 发起 OTA 前先清理（10-30 第三轮教训）
OTA 一发起，设备会多写约 4 块 OTA 状态文件：读到 462848 的“够用”变成 446464，需要 455760 → 差 9296，停在 COMPONENT_SPACE。处理：`cat_at OTA_PRUNE` 两次（会写设备文件，先问用户；4 号工具“清理 OTA 历史”按钮 / `YpVersionTool.exe prune --port COMx --yes`），清理后 450560，OTA 才继续。所以发起前先清理一次再读数。GR 镜像 438 KB / 文件区 512 KB，余量极小。

## 10-30 参考余量（下一版前重新量）
GR 1.5.2 b6 正文 437568 → 离上限只剩 3896 B（0.9%）；CAT1 LuaDB 522019/524288 → 余 2269 B。两者都贴着上限，加功能前先评估。

## 快超限时
GR：关功能/日志、体积优先优化、看 map 文件找大头。CAT1：删不用模块/测试脚本/日志，注意看的是 .luac 大小。文件区不够：确认可删文件后重读 OTA_FS。任何"拒绝/超限"先处理，不换数字重试。

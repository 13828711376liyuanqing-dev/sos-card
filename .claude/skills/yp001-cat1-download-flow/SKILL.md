---
name: yp001-cat1-download-flow
description: The bench-confirmed YP001 flow for anything CAT1 downloads and hands to GR — resident-name glyph push (字库/姓名字形下载, residentNameMsg JSON, cat_at NAME_URL, platform residentNameUrl) and the shared rules it has with whole-device OTA: CAT1 really online before a command, [OTA_HOLD] power lock for the whole job, clear CAT1 logs before downloading, platform URL with md5=, JSON only, one-shot result, release. Use when the user asks to 下发/测试/推送姓名字库, 字库下载, NAME_URL, 生成姓名JSON, 上传平台地址测试, 下载前清日志, 下载时掉电, or when preparing an OTA/字库 download on the bench. Also: the confirmed framework (Name/Room/Campus glyphs only, long-term storage until a newer Seq or factory reset) and the mandatory checks of a backend-generated JSON (tools/glyph_maker/check_platform_json.py, tools/name_push/run_platform_json.py) — use when the user sends a residentNameMsg file to verify (核对后台文件/字库文件对不对).
---

# YP001 CAT1 下载流程（字库下发 + 与 OTA 共用规则）

SAM | 2026-11-03 | 实板确认：2026-11-02 平台地址下发"欧阳䶮𠮷"成功（扩展 A/B 区生僻字），一次成功、4.3 s 释放保电。记录：`doc/2026-11-02_姓名字形平台推送_实现与测试记录.md`、总结 `doc/2026-11-02_姓名字库下发_工作总结与后续改善.md`。

## 0. 共用规则（字库下载和 OTA 都适用）

1. **命令前 CAT1 必须真在线**：COM26 `business status` 为 `link=1 net=4` 才发命令。GR 空闲约 60 s 会给 CAT1 断电（正常）。
   - `link=0`：`cat1_power on`，核对 `rail_request=on code=0x0000`；轮询 `business status`（不要只等 MQTT CONNECTED 标记——CAT1 已在线时等不到，会白等）。
   - 120 s 内仍无任何 `[CAT1 RX]`：按 AGENTS 红线**只发一次** `cat1_power key`，再确认 SIM/REG/IP/MQTT。
   - 一联网就立刻发命令，别等太久，否则又被空闲断电。
2. **全程保电**：下载/安装期间 CAT1 发 `[OTA_HOLD] 1`（GR 打印 `[OTA_HOLD] on`），每 5 s 刷新；结束等 MQTT 回执发出（3 s）后才发 `0`。GR 只有一把共用锁：**OTA 进行中，字库流程不发 `0`**（OTA 自己管）。
3. **下载前先清日志**：删 `/log/app.log`、`/log/app.log.bak`（fs_log 日志，最多约 2×128 KB）腾空间；`/log/ble.ini` 是待上传业务数据，**不删**；OTA 进行中不清。字库流程已内置（`LOG_CLEARED <n>B`）。OTA 侧受保护文件未内置此步，OTA 前清理用一键工具 `--clean-ota-log` / `--auto-prune`（见 `yp001-whole-ota-run`）。
4. **地址用平台存储**（与 OTA 同一路径，http，地址带 `md5=`）。海外网盘 4G 连不上（实测 catbox `HTTP_-4`）；免费网盘多强制跳 https，CAT1 不跟随跳转。
5. **COM26 被占**（Luatools/串口助手）：`PermissionError` → 请用户释放，不要重试轰炸。
6. 只读状态、不改 OTA 受保护文件；电源/充电参数改动遵守 AGENTS 电源红线。

## 0.5 确认的框架与必检（SAM | 2026-11-04，用户确认并更正；改动要先改设备代码并实板验证）

**框架**：**姓名、房间号、园区三个字段全部由后台下发；出厂本地不留（不留姓名、不留这些字的字库），只留存放空间。**
- 后台文件 = `residentNameMsg` JSON：Name / Room / Campus + 这些字的全部字形，**不管设备自带字库有没有都推**（不按自带字表过滤）。
- 姓名每个非英文字 32px（主页）+ 16px（低电页），最多显示 5 个字；园区每个非英文字 16px。
- 房间号：只是数字等，继续用设备 28px 自带字库（ASCII + 号楼栋单元层室），**后台只推文字，不推字形**（用户 11-04 确认）。
- `Seq` = 生成时当前时间（秒），每终端只增不减；比上次小设备拒收（stale）。
- **存放空间 4 KB**（用户 11-04 批准）：GR 专用 Flash 两页 A/B `0x2FB000` / `0x2FC000`（原来 NVDS 一条约 1 KB；本工程 NVDS 只有 1 个 4 KB 扇区，放不下）；记录 = 20 B 头 + 每字 16 B + 点阵，上限 4000 B；**姓名最多 5 个字** + 园区 11 个字实测 21 个字形约 1.4 KB。新记录先写另一页、读回核对后才擦旧页；旧版存在 NVDS 的开机自动搬过来。CAT1 `resident_name.lua`、`glyphlib.py`、后台版 HTML、检查工具上限都已同步 4000。**待实板验证**（见 `doc/2026-11-04_姓名字库存放空间扩到4KB_方案.md` 第四节）。
- **长期保存**：收下后存 GR，重启、断电、OTA 不丢；只有新下发（Seq 更大）或出厂清空才变。
- **出厂清空**（用户 11-04 定：生产工序串口命令）：GR 串口 `name_store clear`，再 `name_store status` 核对 `resident=-- glyphs=0 stored_bytes=0`（新固件还有 `page=0x000000`）。有线烧录工具（窗口版勾选"出厂：清空姓名/房号/园区"，脚本默认；`--keep-name` 只给台架恢复用）最后一步自动做并核对。设备上没有恢复出厂入口会清。

**必检（每个后台文件下发前，两条都通过）**：
1. `python tools/glyph_maker/check_platform_json.py <文件> [--seq-min <设备上次 Seq>] [--compare-ours]`：字段、范围、点阵长度、CRC、**Name/Campus 每个字的字形都在**（缺了报错）、存储、Seq、房号。
2. `python tools/name_push/run_platform_json.py <文件>`：设备同一套代码（CAT1 `resident_name.lua` + GR `yp_name_glyphs.c`）模拟转发、整批生效、字形逐字节一致、重启恢复。

**11-04 后台第一个文件**（`residentNameMsg_张秀珺.json`，记录 `doc/2026-11-04_后台姓名字库文件核对_张秀珺.md`）：格式全对、字形齐全（13 个，符合框架）、设备能收；**Seq 用了 2024 年时间**（会被拒）。后台浏览器画字，笔画与 lv_font_conv 不同（不算错）。
（11-03 定的"自带字库已有的字不推"已作废，生成工具 `glyphlib.py`、后台版 HTML 已改为全部推送。）

## 1. 生成文件（只用 JSON，2026-11-03 用户决定，不用 zip）

- 后台：`tools/glyph_maker/backend/姓名字形生成器_后台版.html`（浏览器打开；码点插入、描点、自动加粗）→ 下载 `residentNameMsg_<姓名>.json`。
- 台架：`python tools/glyph_maker/glyph_maker.py gen --name <姓名>`（与板上字库逐字节一致）。
- 每字 32px+16px；`Seq` 递增（默认当前时间）；字段见 `tools/glyph_maker/docs/字段与格式说明.md`。
- 改了格式先跑 `python tools/glyph_maker/selftest.py --t0`。

## 2. 固件前提

- GR：含姓名下发（`yp_name_glyphs.c`，支持到 U+10FFFF），板上已烧 1.5.8/b12 `logs/name_push_20261102/signed5`（11-03 18:05：长期保存 + 园区 + 修复开机读姓名 `nvds_get` 长度为 0）。改 GR 才需重烧（`yp001-gr-jlink-flash-tool`）。
- 重启测试：GR 命令行没有复位命令，用 J-Link 只发 `r`/`g`（不写 Flash）；看 RAM 里的姓名可用 `fromelf -s` 找 `s` 的地址后 `savebin`（不停核）。NVDS 只读：`savebin 0x2FC000 0x4000`。
- 地址不带 `md5=` 时用 `cat_at NAME_URL=<地址>,<32位md5>`（11-03 用户自己的 nginx 服务器实测可用）。
- CAT1：`resident_name.lua`（JSON only + 清日志 + 保电 + 回执按 id 存）。刷 `firmware_releases/name_push_cat1_20261102/out/USB_IMPORT`（Luatools，用户操作）。重新生成：把 `Air780EGH/resident_name.lua` 拷进 `…/source/` 后跑 `Cat1UsbImport.exe --source … --out …`（源码副本里 `OTA_TRIAL_SOURCE` 已改为 1.5.8，否则工具报错）。
- 版本号不升（用户要求）。
- SAM | 2026-11-03 | 1.5.9 起固定字库已精简：32px 没有汉字，姓名里的汉字全部要推送；16px 不变。自带字库变化时生成工具的"自带字表"要同步，见技能 `yp001-gr-fonts`。

## 3. 台架触发与监控（COM26，115200）

```
cat_at NAME_URL=<平台地址>            # 地址里有 md5= 自动校验；也可 ,<32位md5>
```
只看事件行（`[NAME_URL=]`、`[OTA_HOLD]`、`rail_request`），不刷全量日志。正常序列：

| 时间 | 行 |
|---|---|
| 0.3 s | `[OTA_HOLD] on` + `[NAME_URL=] DOWNLOADING` |
| ~0.3 s | `[NAME_URL=] LOG_CLEARED <n>B` |
| ~0.8 s | `[NAME_URL=] OK <字节>B seq=<Seq>` |
| ~4.3 s | `[OTA_HOLD] 0` / `off`（一次成功） |

之后 `epd_page screen_main`，请用户目视姓名（没有屏幕回读工具）。

不经平台、只测 GR 显示：`python tools/glyph_maker/glyph_maker.py send --name <姓名> --port COM26`（GR CLI `busline` 注入，最后一行 `glyphs=<n>` 即提交）。

## 4. 故障对照（实测）

| 现象 | 原因 | 处理 |
|---|---|---|
| `FAIL HTTP_-4` | 连不上服务器（海外/被墙） | 换平台存储地址 |
| `FAIL HTTP_301/302` | 跳转 https | 用直链，不跳转 |
| `FAIL MD5` | 文件与 md5 不符 | 重新上传/核对 MD5 |
| `FAIL NOT_RESIDENT_NAME_JSON` | 不是 residentNameMsg JSON（含 zip） | 只传 JSON |
| 保电约 15 s 才释放、平台回 fail，但屏幕已变 | 回执丢失（旧 CAT1 代码，GR 回执早于等待） | 刷修复版 CAT1（回执按 id 存） |
| 屏幕没变、GR `glyphs` 不变 | GR 拒收（CRC/格式/Seq 比上次小） | 查 `Seq` 递增、重新生成 |
| 生僻字发淡 | 后备细宋体 | 后台工具自动加粗（板上已确认） |
| 命令无反应 | CAT1 没开/下电 | 按第 0 节第 1 条上电确认 |

## 5. 完成后

在 `doc/2026-11-02_姓名字形平台推送_实现与测试记录.md` 追加：时间、地址（不贴签名参数也可）、事件序列、用户目视结果；未做的项写清（平台 MQTT 正式下发、GR 重启补拉、低电页 16px、整机 OTA 回归）。

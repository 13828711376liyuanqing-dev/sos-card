---
name: yp001-gr-fonts
description: YP001 GR5526 LVGL fixed fonts (font_cn_16/24/28/32/40) — which size each label uses, the slim character sets (font plan phase 1, board-verified 2026-11-03 with whole OTA 1.5.8→1.5.9, GR -55 KB), how to add or remove a character with subset_fonts.py from the full 2026-10-11 export, the coverage check, and what must be synced afterwards (dev-pack snapshot, web name-glyph tool LOCAL table, size/OTA space, host tests, board look). Use when the user asks about 字库/字体/精简字库/加字/缺字/方框/界面改文字/GR 固件太大/字体规划, or before changing any UI text on the GR.
---

# YP001 GR 固定字库（精简、加字、核对）

SAM | 2026-11-03 | 实板确认：精简后的字库随整机 OTA 1.5.8→1.5.9 上板（`doc/2026-11-03_整机OTA_1.5.8到1.5.9_新后台实板记录.md`），主页显示正常。规划：`doc/2026-11-02_字体整体规划方案.md`。

## 0. 规则

- **姓名不靠固定字库**：平台推送字形并长期保存（技能 `yp001-cat1-download-flow`），所以 32px 不放汉字。出厂姓名留空。
- 固定字库**只放界面真的会显示的字**；保留的字必须和原来**逐字节一致**（从完整原版挑，不重新渲染）。
- 16px、40px **不精简**（16px 留着 185 个常用字：园区、低电页姓名能少推字形）。
- 改字库 = 改 GR 固件：要编译、量大小、上板看页面；烧录照常要用户授权。
- 不碰 Git/SVN；改动前原文件有备份（`D:\CODEX\_archive\fonts_before_subset_20261103\`）。

## 1. 字号和用途（`ble_app_uart_c/Src/user/gui/guider/setup_scr_*.c` + `gui/epaper_ui.c`）

| 字库 | 用在哪 | 现在保留 | 点阵 |
|---|---|---|---|
| font_cn_32 | 只有主页姓名（运行时换成推送字形字体，自带字库只做后备） | ASCII | 3192 B |
| font_cn_28 | 只有主页房号（`safe_text`：缺字显示 `--`） | ASCII + 号楼栋单元层室 | 3338 B |
| font_cn_24 | IMEI、标题、正在呼叫...、通话结束、当前电量低、请及时充电、日期、星期 | ASCII + 当前电量低请及时充电正在呼叫通话结束 + 星期一二三四五六日 | 3895 B |
| font_cn_16 | 园区、低电页姓名/日期、状态、提示 | 不动：ASCII + 185 汉字 | — |
| font_cn_40 | 时间页大时钟 | 不动：ASCII | — |

- 星期运行时是英文（`SUN`..`SAT`，`yp001_business.c`），默认的"星期四"会被覆盖。
- 姓名、园区、低电页信息三个标签运行时换成推送字形字体（`name_fonts_init`）；自带字库缺的字由推送补。
- 完整原版里本来就没有"区幢座"，房号出现这些字会显示 `--`，要客户确认房号格式。

## 2. 工具（`tools/glyph_maker/`）

| 文件 | 作用 |
|---|---|
| `subset_fonts.py` | 按 `KEEP` 字表从 `fonts/full_20261011/`（完整原版，95 ASCII + 185 汉字）挑字，写 `guider_fonts/font_cn_{24,28,32}.c`，并同步一份到 `fonts/`（开发包在项目外运行时读它）。`--check` 只检查不写，会报"same as / CHANGES the current file" |
| `check_ui_fonts.py` | 每个标签的默认文字能不能用它的字号画出来；列出代码里所有中文字串用到的字和它们在哪些字号里；`--text "28:1号楼2单元303室"` 检查运行时文字。有缺字时退出码 1 |
| `selftest.py --t0` | 生成工具与板上字库逐字节一致（16/32px） |

**永远从 `fonts/full_20261011/` 挑**，不要从已精简的文件再精简（挑不回已删的字，32px 还会直接报错）。

## 3. 加字 / 减字 / 改界面文字的流程

1. 改 `subset_fonts.py` 里的 `KEEP`（按字号加字或删字）。
   - 字在完整原版里：直接加。
   - 字不在完整原版里（`not in font` 会列出）：要用 lv_font_conv 按原参数渲染（SimHei、`--bpp 1 --no-compress`、每行补齐到字节，见 `glyphlib.render_lfc`），先和用户确认再做；`--t0` 证明过这条渲染链和板上字库逐字节一致。
2. `python subset_fonts.py --check` → 看保留了哪些字、点阵大小、`glyphs identical`。
3. `python subset_fonts.py` 写入。
4. `python check_ui_fonts.py --text "<字号>:<运行时会出现的文字>" ...` → `RESULT OK`（`PUSHED` 行是推送标签，不算错）。
5. **同步姓名字形工具**（自带字库变了，推送规则跟着变）：
   - Python 版读 `guider_fonts`（或项目外读 `fonts/`），自动跟随；
   - **网页版要改**：`backend/姓名字形生成器_后台版.html` 里 `const LOCAL = {16: ..., 32: ...}` 字表快照（从 `glyphlib.local_font(16/32)` 生成）；
   - `python selftest.py --t0` 全过。
6. 主机测试：`python tools/name_push/test_name_push.py`、`python tools/name_push/test_cat1_resident.py` 全过（CAT1 测试里有依赖自带字库内容的用例）。
7. Keil 编译 0 错误 0 警告；签名看正文大小；**OTA 空间**：要求 = 签名镜像 + 16384 ≤ CAT1 可用（`cat_at OTA_FS`）再留 ≥ 16 KB（技能 `yp001-space-budget`）。
8. 上板看页面。注意：`epd_page <页>` 在业务状态正常时会被覆盖（`[GUI] queued ... live business state may take priority`，`frame unchanged`），低电、呼叫、通话结束页要等真实场景看，或用第 4 步的电脑核对代替。

## 4. 实测数字（2026-11-03）

| 项 | 精简前 | 精简后 |
|---|---|---|
| RO-data（Keil） | 146532 | 90476 |
| GR 签名镜像 | 429288 | 372968（-55 KB） |
| OTA 空间要求 | 445672（差 15.6 KB） | 389352（可用 425984，余 36.6 KB） |
| 姓名推送大小（5 个汉字，32px 全推） | — | 约 400–900 B（上限 1000 B） |

## 5. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 界面某处出现方框 | 那个字号的字表里没有这个字 | `check_ui_fonts.py` 找出来，加进 `KEEP`，走第 3 节 |
| 房号显示 `--` | 房号里有 28px 没有的字（如 区幢座） | 确认格式后加字（不在原版里要渲染） |
| 姓名少推字形、显示方框 | 网页版 `LOCAL` 快照没更新，还以为设备有这些字 | 第 3 节第 5 步 |
| `subset_fonts.py` 报 `(…, 1, 1, 0, 1, 1)` 断言 | 拿已精简的文件当来源 | 来源必须是 `fonts/full_20261011/` |
| GR 又变大、OTA 空间不够 | 加了功能或加了字 | 看 RO-data；必要时做"边下边转"（`doc/2026-11-03_OTA最优方案_配合后台流式推送_测试验证.md`） |

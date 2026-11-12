---
name: yp001-tidy
description: YP001 项目收尾清理（调试日志、旧发布目录、tmp、根目录零散文件），用本地工具 tools/tidy/tidy.py，不用手工逐个清。一个功能调试完并同步后用。
---

# YP001 收尾清理

SAM | 2026-11-04 | 用户要求：一个功能调试完就清理，保持目录清楚；清理走本地脚本，省 token。

## 什么时候做

功能板上验证完、`tools/tree_sync/sync_all.py --yes` 同步到 D:\SVN 之后。

## 一条命令收工（优先用）

`python tools/wrapup/wrapup.py`（预览），`python tools/wrapup/wrapup.py --yes`（执行）：先同步到 D:\SVN 并核对、更新基线、交接检查，通过才接着清理；同步没通过就不清理。双击 `tools/wrapup/wrapup.bat` 也行。提交仍由用户或 Codex 做。

## 只清理时

1. `python tools/tidy/tidy.py`：预览，只列数量和大小。
2. 看一眼没问题，`python tools/tidy/tidy.py --yes`：移动到 `D:\CODEX\_archive\tidy_<时间>\`（移动不删除，要找回就从那里拿）。
3. 回复只报：移了多少、多大、有没有被占用没动的。

## 规则（写在工具里）

- `firmware_releases/`：留最新 3 个目录 + `使用说明.md`；`ota_1.5.9_to_1.5.10_20261104_1201` 固定保留（工具测试用它当样本）。
- `logs/`、`tmp/`：2 天前的条目移走。可用 `--log-days`、`--tmp-days`、`--keep-releases` 调整。
- 根目录零散文件（`tmp_*.png`、`keil_build*.log`、`*.jlink`、`luac.out`、预览图、`*.bak_*` 等）、`tools/` 下 `__pycache__`。
- 不碰源码（Air780EGH、ble_app_uart_c、SDK、tools 代码、doc、skills）、工具包、密钥、版本控制目录。
- 被别的程序占用的移不动，会列出来，不强删。

## 新增调试产物时

放在 `logs/<功能>_<日期>/` 或 `tmp/`，不要放项目根目录；这样 tidy 能自动认出来。要长期保留的结论写进 `doc/*.md`。

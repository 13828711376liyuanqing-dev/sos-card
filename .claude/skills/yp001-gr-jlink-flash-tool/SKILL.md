---
name: yp001-gr-jlink-flash-tool
description: Wired (J-Link only, no Keil project) flashing of a signed YP001 GR5526 image with Boot re-pairing, confirmed on the bench 2026-11-01. Use when the user asks to 烧写/下载/有线烧 GR, put a new GR baseline on the board, or recover a board that cannot take an OTA.
---
# YP001 GR5526 J-Link 有线烧录（实板确认 2026-11-01）

工具：`tools/gr_release/GR_JLink_Flash/`（`一键烧录.bat` 或 `python yp001_gr_jlink_flash.py <签名.bin> [--yes] [--port COM26|none]`）。只需 Python + SEGGER J-Link，Flash 算法 `GR5xxx_16MB_Flash.FLM` 随工具。

流程：只读快照 → 取板上 Boot 只改 40 B 基线描述符（offset 0x71F0：正文长度、版本号 maj*1e6+min*1e3+patch、正文 SHA-256）→ 擦 0x2F6000-0x2FAFFF（scratch/Boot 日志/owner）和 B 槽 → 写 A 并复位 → 单独会话擦写 Boot → 读 SCA 必须指向 0x2EC000（不对自动重写，最多 3 次）→ 整片读回核对 → COM26 fw_version。

SAM | 2026-11-04：**最后一步出厂清空**：串口 `name_store clear` 再核对 `name_store status` 为空（姓名、房号、园区出厂本地不留，等后台下发）；窗口版复选框默认勾选，脚本 `--keep-name` 保留（只给台架恢复用）。没选串口时清空没做，日志提醒手动。GR 姓名字形存在 `0x2FB000`/`0x2FC000`（本工具不擦这两页，靠 `name_store clear` 清）。

坑（均已实测）：
- J-Link V7.54 启动时不加载用户设备目录，`-device YP001_GR5526` 会卡死等对话框；做法是 `-device CORTEX-M4` 连接后 `exec JLinkDevicesXMLPath=<dir>\` + `device YP001_GR5526`。XML 根标签必须是 `<DataBase>`。
- FLM 会把一次会话写的镜像登记进 SCA（0x200000：size、字节和、load、run）。A 和 Boot 同会话写会让 SCA 指向 A，GR 起不来（PC 停在 ROM 0x8xxxx–0x9xxxx）。救法：GR 运行时单独一次"擦 Boot 区 + 写 Boot"会话。
- 清 owner 页必须同时清空 B 槽，否则 GR 首次记进度要求 B 全空，返回 `receiver_unavailable`。
- J-Link 输出首行 "will now exit on Error" 不是错误。
- 只能烧 Gr5526Tool 签名后的 .bin。

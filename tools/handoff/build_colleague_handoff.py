"""SAM | 2026-11-07 +08:00 | Freeze an OUR-based SVN-layout handoff and verify its ZIP without modifying either source tree."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
STAMP = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
NAME = "YP001_SVN结构_同事开发交接_1.5.21_b25_" + STAMP
OUT = ROOT / "handoff_releases" / NAME
NOTES = OUT / "ProductDoc/交接资料"
CAT = ROOT / "firmware_releases/CAT1_1.5.21_b25_CANDIDATE_20261107"
PROVENANCE = {}
SKIP_DIRS = {".git", ".svn", "__pycache__", ".codegraph"}


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source, relative):
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    digest = sha(target)
    if digest != sha(source):
        raise RuntimeError("Source changed during copy " + str(source))
    PROVENANCE[target.relative_to(OUT).as_posix()] = {"origin": str(source), "sha256": digest}


def copy_tree(source, relative, skip=()):
    for current, directories, files in os.walk(source):
        directories[:] = sorted(name for name in directories if name not in SKIP_DIRS | set(skip)
                                and not (Path(current) / name).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            if not path.is_symlink():
                copy_file(path, Path(relative) / path.relative_to(source))


def write(relative, text):
    target = OUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main():
    if OUT.exists():
        raise RuntimeError("Output already exists")
    OUT.mkdir(parents=True)
    state = json.loads((ROOT / "logs/svn_integration_20261107/board_b25/acceptance_after_retry.json").read_text())
    if not state["signed_app_matches"] or state["gr_runtime"] != "1.5.21/b25":
        raise RuntimeError("Current board/source identity is unconfirmed")
    print("Copying SDK and SVN-layout source trees", flush=True)
    copy_tree(ROOT / "SDK", "SDK")
    copy_tree(ROOT / "ProductDoc", "ProductDoc")
    for name in ("Src", "Logo", "GCC"):
        copy_tree(ROOT / "ble_app_uart_c" / name, "ble_app_uart_c/" + name,
                  skip={"Objects", "Listings", "build", "Debug", "Release", "_archive"})
    keil = ROOT / "ble_app_uart_c/Keil_6"
    for path in keil.iterdir():
        if path.is_file() and ".uvguix." not in path.name and path.name != "JLinkLog.txt":
            copy_file(path, "ble_app_uart_c/Keil_6/" + path.name)
    for name in ("YP001_GR5526.axf", "YP001_GR5526.hex", "YP001_GR5526.build_log.htm"):
        copy_file(keil / "Objects" / name, "ble_app_uart_c/Keil_6/Objects/" + name)
    for name in ("YP001_GR5526.map", "YP001_GR5526.bin"):
        copy_file(keil / "Listings" / name, "ble_app_uart_c/Keil_6/Listings/" + name)
    for path in (ROOT / "Air780EGH").iterdir():
        if path.is_file():
            staged = CAT / "source" / path.name
            copy_file(staged if staged.is_file() else path, "Air780EGH/" + path.name)
    copy_tree(ROOT / "Air780EGH/vendor_luac", "Air780EGH/vendor_luac")
    copy_file(ROOT / "Air780EGH/soc/LuatOS-SoC_V2052_Air780EGH_113.soc",
              "Air780EGH/soc/LuatOS-SoC_V2052_Air780EGH_113.soc")
    copy_file(ROOT / "firmware_version.json", "firmware_version.json")
    for path in (ROOT / "tools/ota").iterdir():
        if path.is_file() and path.suffix in {".py", ".c", ".h", ".lua", ".md", ".json"}:
            copy_file(path, "tools/ota/" + path.name)
    copy_tree(ROOT / "tools/ota/boot", "tools/ota/boot")
    business_tests = ["test_sip_disconnect_qp_states.py", "test_scan_stop_shared.py", "test_cat_business.py",
                      "test_peer_state_sync.py", "test_sim_recovery.py", "test_sos_qp.py",
                      "test_sos_qp_states.py", "test_ota_observation_paths.py", "test_ble_sdk_irq_priority.py"]
    for name in business_tests:
        copy_file(ROOT / "tools/business" / name, "tools/business/" + name)
    copy_file(ROOT / "tools/name_push/test_name_push.c", "tools/name_push/test_name_push.c")
    copy_tree(ROOT / "tools/name_push/stubs", "tools/name_push/stubs")
    for name in ("yp001-ota-recovery", "yp001-software-requirements"):
        copy_tree(ROOT / ".codex/skills" / name, "ProductDoc/交接资料/技能/" + name)
    for path in (ROOT / "doc").glob("2026-11-07*.md"):
        if any(word in path.name for word in ("SVN", "同事增量", "扫描SDK", "OTA控制事件", "回退与救援", "OTA合并事故", "版本保护", "OTA影响矩阵")):
            copy_file(path, "ProductDoc/交接资料/过程记录/" + path.name)
    copy_file(ROOT / "doc/YP001_代码修改强制检查项.md", "ProductDoc/交接资料/代码修改强制检查项.md")
    for name in ("build_b25/build_verification.json", "board_b25/acceptance_after_retry.json",
                 "board_b23/acceptance.json", "board_b24/acceptance.json"):
        copy_file(ROOT / "logs/svn_integration_20261107" / name, "ProductDoc/交接资料/证据/" + name)
    for name in ("source_manifest.json", "range_host_check.json", "import/integrity.json"):
        copy_file(CAT / name, "ProductDoc/交接资料/证据/CAT1/" + name)
    for candidate in ("svn_r88_ota_control_events_20261107", "svn_r88_platform_callout_20261107"):
        copy_file(ROOT / "firmware_releases/candidates" / candidate / "manifest.json",
                  "ProductDoc/交接资料/证据/候选清单/" + candidate + ".json")
    for version, build in (("1.5.20", 24), ("1.5.21", 25)):
        name = f"GR5526_{version}_b{build}_signed.bin"
        copy_file(ROOT / f"firmware_releases/GR_{version}_b{build}_SIGNED_CANDIDATE_20261107" / name,
                  "ProductDoc/交接资料/参考固件/" + name)
    copy_tree(CAT / "import/USB_IMPORT", "ProductDoc/交接资料/参考固件/CAT1_1.5.21_b25_USB_IMPORT")
    for name in ("GrJLinkFlash.exe", "GR5xxx_16MB_Flash.FLM", "使用说明.txt"):
        copy_file(ROOT / "YP001_工具包/GR_JLink_Flash_Tool" / name,
                  "ProductDoc/交接资料/参考工具/GR_JLink_Flash_Tool/" + name)
    copy_tree(ROOT / "YP001_工具包/1_CAT1刷机目录生成", "ProductDoc/交接资料/参考工具/CAT1刷机目录生成",
              skip={"logs", "__pycache__"})
    copy_file(ROOT / "YP001_工具包/budget.json", "ProductDoc/交接资料/参考工具/budget.json")
    write("README_SVN交接.md", README)
    write("AGENTS.md", AGENTS)
    write("ProductDoc/交接资料/01_已确认功能与验收范围.md", ACCEPTANCE)
    write("ProductDoc/交接资料/02_OTA红线与交付验收.md", OTA_RULES)
    write("ProductDoc/交接资料/03_待完善与合并顺序.md", BACKLOG)
    write("ProductDoc/交接资料/04_编译回归与回退.md", BUILD)
    write("验证交接文件.ps1", VERIFY)
    status = {"release": "1.5.21/b25", "kind": "DEVELOPMENT_HANDOFF_CANDIDATE",
              "hardware": state, "GR_source": "OUR main project current b25",
              "CAT1_source": "Air780EGH with three staged version-range files used to build the installed receiver",
              "sdk": "GR5526 SDK 1.0.4", "soc": "V2052_Air780EGH_113",
              "full_dual_ota": "PENDING_REQUIRED_FOR_STABLE_RELEASE", "cat_next_scope": "1.5.21 -> 1.5.22",
              "manual_OTA_TRIAL_md5_frozen": False, "complete_KV_inventory": "UNVERIFIED"}
    write("验收状态.json", json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    project = OUT / "ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx"
    missing = []
    for node in ET.parse(project).findall(".//FilePath"):
        target = project.parent / (node.text or "").replace("\\", "/")
        if not target.is_file():
            missing.append(str(target))
    if missing:
        raise RuntimeError("Missing Keil source references " + repr(missing))
    pre = json.loads((ROOT / "firmware_releases/candidates/svn_r88_platform_callout_20261107/pre_f7_inputs.json").read_text())
    internal = 0
    for item in pre["files"]:
        path = Path(item["path"]).resolve()
        if path.is_relative_to(ROOT):
            relative = path.relative_to(ROOT)
            expected = CAT / "source/main.lua" if relative.as_posix() == "Air780EGH/main.lua" else path
            if not (OUT / relative).is_file() or sha(OUT / relative) != sha(expected):
                raise RuntimeError("Missing or different build input " + str(relative))
            internal += 1
    for name in ("air1103.luac", "es8311.luac", "exsipclient.luac", "exsipproto.luac"):
        if sha(OUT / "Air780EGH/vendor_luac" / name) != sha(CAT / "import/USB_IMPORT" / name):
            raise RuntimeError("CAT vendor mismatch " + name)
    validation = {"all_keil_file_references_exist": True, "frozen_internal_build_inputs_verified": internal,
                  "external_compiler_inputs": len(pre["files"]) - internal,
                  "cat1_vendor_libraries_match_import": True, "metadata_excluded": [".git", ".svn"],
                  "intermediate_cache_scope": "new checkout establishes its own Objects/.d cache on first F7",
                  "full_device_ota": "PENDING"}
    write("构建引用核对.json", json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            relative = path.relative_to(OUT).as_posix()
            manifest.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha(path),
                             "origin": PROVENANCE.get(relative, {}).get("origin", "generated handoff documentation")})
    write("文件清单_SHA256.json", json.dumps({"created": STAMP, "files": manifest}, ensure_ascii=False, indent=2) + "\n")
    archive = OUT.with_suffix(".zip")
    print("Creating and reading back ZIP", flush=True)
    files = [path for path in sorted(OUT.rglob("*")) if path.is_file()]
    expected = {row["path"]: row["sha256"] for row in manifest}
    expected["文件清单_SHA256.json"] = sha(OUT / "文件清单_SHA256.json")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as package:
        for path in files:
            method = zipfile.ZIP_STORED if path.suffix.lower() in {".zip", ".mp3", ".png", ".jpg", ".pdf", ".soc"} else zipfile.ZIP_DEFLATED
            package.write(path, NAME + "/" + path.relative_to(OUT).as_posix(), compress_type=method, compresslevel=1)
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            relative = entry.filename[len(NAME) + 1:]
            digest = hashlib.sha256()
            with package.open(entry) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected[relative]:
                raise RuntimeError("ZIP verification failed " + relative)
        if len(package.infolist()) != len(expected):
            raise RuntimeError("ZIP inventory mismatch")
    digest = sha(archive)
    archive.with_suffix(".zip.sha256.txt").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    result = {"directory": str(OUT), "zip": str(archive), "files": len(files),
              "zip_bytes": archive.stat().st_size, "zip_sha256": digest, "zip_member_hashes_verified": True}
    (ROOT / "handoff_releases/latest_handoff.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


README = """# YP001 同事开发交接

SAM | 2026-11-07 +08:00

本包以我们的主工程为基础，按 D:/SVN 的四个业务目录整理。源码候选为1.5.21/b25，两端运行版本均已读取，GR完整A镜像与签名候选一致。交接用途是继续完善和合并，最终交付须通过真实双端OTA及功能验收。

## 入口

- GR工程为 `ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx`，SDK为根目录 `SDK` 1.0.4，编译器Arm Compiler 6.14。
- CAT1唯一源码入口为 `Air780EGH`，V2052_Air780EGH_113，64位Lua。这里三处OTA版本配置采用本次已生成接收端的1.5.21到1.5.22固定范围。
- `ProductDoc/交接资料/01_已确认功能与验收范围.md`列出确认范围及待验项。
- `ProductDoc/交接资料/02_OTA红线与交付验收.md`是强制交付条件。
- `ProductDoc/交接资料/03_待完善与合并顺序.md`是后续待办和拒绝原样引入的改动。
- `ProductDoc/交接资料/04_编译回归与回退.md`说明构建、验证和回退。

## 开始工作

在新目录解压后运行根目录 `验证交接文件.ps1`，再运行Keil目录的 `验证Keil6交付.ps1`。F7构建自己的依赖缓存，确认新AXF/HEX身份及源码输入。每个改动保留独立差异与回退点，在隔离候选集中合并，整批统一实板及真实双端OTA。通过后才作为稳定版交付。

源码和原始工程目录之外，增加了回归源码 `tools`、身份文件、清单和本文。历史过程记录中的D:/CODEX绝对路径属于原始证据索引，交接使用本包相对目录。

本包的主机、构建、有线启动和局部功能证据均有边界。当前完整双端OTA、连续多轮OTA及完整FS/KV保持为必须完成的待验项，详见验收表。
"""

AGENTS = """# YP001 同事开发强制要求

SAM | 2026-11-07 +08:00

1. 以本包我们的工程为基础逐功能移植。读取ProductDoc/交接资料的四份入口说明和OTA技能，保留已确认功能。
2. 所有修改先评估OTA直接、间接影响，覆盖IRQ/BLE、调度/定时器、UART/DMA、内存、电源/休眠、Boot、签名/布局、用户数据及跨端兼容。
3. 用户已批准隔离候选集中合并。每项保留精确差异、针对性主机检查和独立撤回点，整批统一F7、实板及真实双端OTA，通过后进入稳定版。
4. OTA期间运动、普通按键、找人、休眠及其采样失鲜降权，不能阻塞或重置确认计时。生产与台架一致。真实报警/通话、链路、实际供电、签名/事务和数据保持继续保护。
5. OTA供电门槛为有效电量至少50%或健康USB。保留真实采样、故障检查及完整120秒连续健康观察。新接收端与原GR先、CAT1后的顺序兼容。
6. 保留SDK1.0.4、CAT1 V2052、原Keil6配置。使用原主工程F7，建立缓存后保留Objects/.d。Boot逻辑未改时复用既有Boot，下载按合法配对和签名流程执行。
7. 程序回退及OTA恢复保留最新用户数据。先核对owner/job/hash/epoch、Boot和安装阶段，按合法事务状态处理。
8. 充电电流改变必须先有预算和接电池/仅USB两类峰值实测。保护当前100mA配置，拒绝未经验证的300mA直接移植。
9. 正式版本/build对应唯一内容，保留manifest和真实产物hash。注释使用SAM、北京时间、修改内容与原因，同位置更新原注释，历史写入中文记录。
10. 每项提供修改说明、测试与未验项目。工具无冲突、主机通过、编译通过与实板OTA验收分别记录。验收表中的PENDING须闭环。
"""

ACCEPTANCE = """# 已确认功能与验收范围

SAM | 2026-11-07 +08:00

| 项目 | 当前证据 | 必须补齐的边界 |
|---|---|---|
| 两端启动与通信 | GR实际1.5.21/b25，CAT1实际1.5.21，REG=1，GR业务链路/MQTT就绪，号码快照known=1 | CAT1脚本分区成员设备侧逐字节核对待验 |
| GR签名镜像 | 382184字节，实际A槽与签名文件逐字节一致，构建0错误0警告，726个构建输入一致 | 真实OTA传输、安装和健康确认待验 |
| 双键SOS持续长按锁存 | 用户确认本地触发、声音及报警中重复长按行为，主机覆盖队列与状态机 | 取消交错、松键重新触发的专门实板场景及真实呼叫待验 |
| 通话和结束页 | 用户确认本地注入显示通话页、结束页并返回主页 | 真实SIP拨号/接通/远端挂断及网络条件待验 |
| SIP断开收尾 | 主机实际QP双配置覆盖远端断开、重复断开、不重拨、报警保持 | 真实SIP通话仍待验 |
| 共享扫描与SDK优先级 | b23实板启停返回0，SDK状态0/7/0，停收/恢复计数可见；运动周期启动/停止请求及结果上报已观察 | SOS/定位/手机占用交错与实板OTA并发待验 |
| OTA控制事件降权 | b24起源码落实，实际b25已运行；生产/台架主机持续130秒控制干扰仍完成120秒健康观察 | 真实OTA中运动/按键/找人/休眠干扰下完整闭环待验 |
| 平台CallOut配套 | 实际QP双配置、CAT1业务24项和正常路由6项通过，绑定保存成功才投影，hello恢复，支持3至32字符 | 真实后台绑定/清除、掉电保持、真实号码呼出待验 |
| OTA专项 | 安装收据/重复ACTIVATE、二进制Lua/C、UART静默窗、供电与结果等主机专项通过 | 当前b25完整双端OTA仍PENDING |

历史1.5.14/b18存在设备OTA成功记录和已知问题。其结果按原镜像使用，不能替当前b25验收。当前程序包含新的IRQ、门控和号码同步变更，须绑定实际镜像重测。

保留单键接听/挂断、报警持续与通话状态分离、姓名/房号/园区、SDK/用户数据保护等现有逻辑。以上“保留”表示代码要求，完整业务矩阵按实板验收逐项登记。
"""

OTA_RULES = """# OTA红线与交付验收

SAM | 2026-11-07 +08:00

## 强制要求

- 每次变更评估直接与间接OTA依赖。共享IRQ/BLE、QP调度、UART/DMA、内存、供电、Boot和用户数据均纳入。
- 保留合法owner/job/hash/epoch/进度/签名、两端串行和最新用户数据。当前执行顺序为GR先、CAT1后。
- 控制类运动/普通按键/找人/休眠及其采样失鲜不阻塞OTA、不重置健康计时。真实报警/通话/未知通话、链路和实际供电按保护规则处理。
- 有效电量至少50%或健康USB，保留故障/采样新鲜度；完整120秒健康观察继续执行。
- 源码候选可以集中合并，稳定交付必须通过对应实际镜像的真实双端OTA。失败保留现场，按合法事务修复或回退。

## 必做实板验收

| 验收项 | 通过证据 |
|---|---|
| 来源/目标与内容 | 实际GR/CAT1版本、构建输入、镜像/脚本hash、manifest及合法更高目标 |
| 双端完整升级 | 真实后台受理、下载、UART传输、严格串行安装和两端目标版本 |
| 安装与健康确认 | Boot有效CONFIRMED、合法owner COMPLETE/success、CAT1实际安装终态、120秒确认连续性 |
| 完整性 | 丢ACK/重试、重复ACTIVATE、回执补报、结果队列收尾，原协议范围内核对后台记录 |
| 控制干扰 | 运动、普通按键、找人、休眠控制事件不打断进度或重置计时，真实SOS/通话按保护策略处理 |
| 数据保持 | 比对姓名、房号、园区、电话/白名单、参数、NVDS/FS/KV，程序回退保留最新业务数据 |
| 后续持续OTA | 至少验证下一轮再升级，确认已安装目标可继续接收后续合法升级，不依赖重刷接收端 |

## 当前接收端边界

交接CAT1为1.5.21/b25，main、ota_trial和ota_native_fota的固定范围均为1.5.21到1.5.22。1.5.22目标镜像与后台包尚未生成。手动OTA_TRIAL的MD5为全零，手动入口实际返回拒绝。后台入口独立判定，完整实板OTA保持PENDING。

固定范围保留独立审核作用，不能改成profile与同源全局变量自比较以图省事。范围也涉及root_files_kv_unverified例外，完整KV清单仍未验证。沿用的历史evidence_sha256仅格式校验，不能作为21到22实板证据。连续多轮升级的目标配置与安装后范围衔接是必须完善并实测的项目。
"""

BACKLOG = """# 待完善与合并顺序

SAM | 2026-11-07 +08:00

| 优先级 | 工作 | 处理要求 |
|---|---|---|
| P0 | 当前b25真实双端OTA及后续连续升级 | 按OTA验收表完成，保持版本范围/数据保护，记录实际源码和镜像hash |
| P0 | 电话功能实板闭环 | 从真实平台绑定到CAT1持久化、GR投影、实际号码拨号，覆盖清除/重启/保存失败/单次拨打/不重拨 |
| P1 | 参数查询和设置正常入口 | 现有正常business_core会消费paraSetMsg并回PARAMETERS_NOT_READY，不能把legacy测试分支存在当作可用；查询不写配置，缺字段保留旧值，保存失败不能成功回执 |
| P1 | 参数及号码跨重启统一 | CAT1已是电话持久owner，GR仅RAM投影。GR参数NVDS另做版本、长度、范围及写失败策略，核对旧tag3/4与字库迁移冲突，兼容旧用户记录 |
| P1 | CallInList旧GR legacy解析 | 旧分支误查字符串且循环未使用item_part；正常CAT1已有白名单验证。按实际所有权闭环，避免双端重复保存和回复 |
| P1 | BleScanCntPara | 明确平台字段与“60次/60分钟”语义，不能将分钟参数当扫描次数 |
| P1 | 真实SIP/报警/扫描并发 | 依据已确认功能保留逻辑，补齐实板业务矩阵 |
| P2 | PSRAM、RX与存活探测 | 先统一内存所有权/分配释放、NULL/失败分支、UART帧边界与上下文；持续在线需真实证据 |
| P2 | 重启回执/低电/离线 | 绑定实际持久结果和发送完成，OTA期间遵守既有保电及重启安全门 |

同事300mA充电、原始整个参数结构直接写NVDS、PSRAM与普通free混用、通话结束清报警、四个业务发送函数直接置空、OTA动态范围自比较等差异，均不能原样覆盖我们的实现。原始逐功能审查与精确来源见过程记录。

显示层隐藏三轴信息可以单独评估，真实采样、电量有效性、防残影及其他调用方保持各自职责。每项功能拆小，独立检查和回退，按整批执行构建与实板验收。
"""

BUILD = """# 编译回归与回退

SAM | 2026-11-07 +08:00

## GR

运行 `ble_app_uart_c/Keil_6/验证Keil6交付.ps1`，打开原uvprojx，AC6.14，F7。保留SDK1.0.4、scatter、APP_INFO、下载算法及Keil配置。新解压位置首次F7会建立自己的Objects和.d依赖缓存，后续沿用增量构建。

包内Objects/Listings提供与b25对应的AXF、HEX、MAP、BIN和日志作为构建证据。部署使用签名应用与合法配对Boot，GR_JLink_Flash_Tool取消出厂清空姓名/房号/园区。Root信任、布局和用户数据保护继续核对。签名工作由持有项目签名材料的维护人执行。

## CAT1

维护入口为Air780EGH。沿用soc下V2052_Air780EGH_113及vendor_luac四个已核对库。参考工具中CAT1目录生成器可以生成USB_IMPORT，手动OTA MD5/独立版本范围需按当次正式候选冻结。Luatools下载保留FS/KV，验证实际启动版本及号码快照。

源目录与已编译参考USB_IMPORT都在包内，三处版本范围来自此次接收端候选，原始活动根的旧7到8配置未带回。main.lua个别范围注释仍是历史说明，执行赋值已经核对为21到22，后续修改时同步注释与真实范围。

## 有效主机入口

Python3、Lupa Lua5.4和GCC/QPC宿主环境需在同事电脑配置。现有脚本的GCC安装路径可以按本机环境调整，生产源码/门禁依据保持。

```powershell
python -X utf8 tools/business/test_sip_disconnect_qp_states.py --label colleague_check
python -X utf8 tools/business/test_cat_business.py
python -X utf8 tools/business/test_peer_state_sync.py
python -X utf8 tools/ota/test_ota_control_events.py
python -X utf8 tools/ota/test_gr_install_receipt.py
python -X utf8 tools/ota/test_gr_wire_loop.py
python -X utf8 tools/ota/test_uart_flash_window.py
python -X utf8 tools/business/test_ota_observation_paths.py
```

历史测试脚本保留作追溯，适用性按实际合同核对。当前QP宿主编译对既有unused-variable和旧CallInList的unused-but-set-variable保留warning，实板Keil构建为0错误0警告，相关待完善项已列明。

## 回退

修改前后保存精确diff和manifest。撤回先核对当前after hash，按功能撤销，保留同事后续修改。设备回退前读取合法事务、Boot及安装状态，选择对应程序恢复流程，保留最新用户数据。参考固件中的b24仅用于可追溯的程序候选，不能当整机用户数据快照回写；完整回退/救援演练仍待实测。
"""

VERIFY = r'''$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $root '文件清单_SHA256.json') -Raw -Encoding utf8 | ConvertFrom-Json
$prefix = [IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
$count = 0
foreach ($item in $manifest.files) {
    $path = [IO.Path]::GetFullPath((Join-Path $root $item.path))
    if (-not $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path escapes package' }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing $($item.path)" }
    if ((Get-Item -LiteralPath $path).Length -ne $item.bytes) { throw "Size differs $($item.path)" }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) { throw "Hash differs $($item.path)" }
    $count++
}
Write-Output "PASS package file hashes $count"
'''


if __name__ == "__main__":
    main()

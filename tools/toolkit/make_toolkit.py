"""SAM | 2026-10-30 11:08 +08:00 | Build the YP001 toolkit folder: one folder with the three standalone tools, everything they need, a version table of the
Luatools-derived files and readable instructions. Zip that folder and hand it over; it needs nothing installed on the other PC.
Usage: python tools/toolkit/make_toolkit.py [--out D:/CODEX/sos-card/YP001_工具包] [--toolkit-version 2026.10.30-1]
Refuses to finish if the folder contains any private key material (the signing key is imported by the operator, never shipped)."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = sys.executable
TOOLS = [  # (folder in the toolkit, build dir, built folder name)
    ('1_CAT1刷机目录生成', ROOT / 'tools/cat1_release', 'CAT1_USB_IMPORT_Tool'),
    ('2_GR5526固件检查签名', ROOT / 'tools/gr_release', 'GR5526_Tool'),
    ('3_整机OTA打包', ROOT / 'tools/ota/pack_tool', 'YpOtaPack_Tool'),
    ('4_固件版本与空间', ROOT / 'tools/ver_tool', 'YpVersionTool_Tool'),
    # SAM | 2026-11-04 +08:00 | the wired J-Link flashing tool was added to the folder by hand on 11-01; now built and shipped here
    ('GR_JLink_Flash_Tool', ROOT / 'tools/gr_release/GR_JLink_Flash', 'GR_JLink_Flash_Tool'),
    # SAM | 2026-11-04 +08:00 | check of a platform residentNameMsg file + plain explanation (Markdown) for the backend team
    ('5_姓名字库核对', ROOT / 'tools/name_check', 'NameCheck_Tool'),
    # SAM | 2026-11-10 +08:00 | OTA monitor window: hardware check (J-Link / GR serial / CAT1 USB) + read-only progress watch
    ('6_OTA过程监控', ROOT / 'tools/ota_monitor', 'YpOtaMonitor_Tool'),
    # SAM | 2026-11-10 +08:00 | read-only J-Link probe for a GR stuck in Boot TRIAL (needs the same build's .map/.hex)
    ('7_GR试运行卡点读取', ROOT / 'tools/gr_trial_probe', 'YpTrialProbe_Tool'),
]
BUDGET = HERE / 'budget.json'   # SAM | 2026-11-04 +08:00 | OTA size red lines, master copy (read by every tool and tools/ota_oneclick)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def private_material(folder):
    """Names/contents that look like a private signing key."""
    hits = []
    for p in Path(folder).rglob('*'):
        if not p.is_file():
            continue
        if p.suffix.lower() == '.key' or 'PRIVATE' in p.name.upper():
            hits.append(str(p))
            continue
        if p.stat().st_size <= 65536 and p.suffix.lower() in ('.xml', '.pem', '.txt', '.json', '.key'):
            t = p.read_text(encoding='utf-8', errors='ignore')
            if re.search(r'<D>|<P>|<Q>|BEGIN [A-Z ]*PRIVATE KEY', t):
                hits.append(str(p))
    return hits


README = '''YP001 工具包  {version}
=========================

这个文件夹里的东西是完整的：整个文件夹拷到任何一台 Windows 10/11 电脑上就能用，不需要安装任何软件
（用的是 Windows 自带的 .NET Framework 4）。需要的资源都在各工具自己的子文件夹里。

内容
  1_CAT1刷机目录生成\\    Cat1UsbImport.exe   把 Air780EGH 脚本源码生成 Luatools 的 USB_IMPORT 刷机目录（或 zip），并做检查
  2_GR5526固件检查签名\\  Gr5526Tool.exe      检查编译好的 GR5526 固件（.hex / .bin，Keil、GCC 都行），导入密钥签名，验签
  3_整机OTA打包\\         YpOtaPack.exe       生成 CAT1 包、授权文件，打包并验证整机升级包 <前缀>_<源>---<目标>_<后缀>.zip
  4_固件版本与空间\\     YpVersionTool.exe   改两个固件的版本（改完你手动编译）、检查各自空间、串口读设备 CAT1 可用空间
  GR_JLink_Flash_Tool\\   GrJLinkFlash.exe    用 J-Link 有线烧录签好的 GR 固件（出厂、恢复板子）：擦 owner/Boot 日志和 B 槽，写 A 槽和 Boot
  5_姓名字库核对\\         NameCheck.exe       核对后台生成的姓名字库文件 residentNameMsg_*.json 能否下发，并生成逐段说明（Markdown）
  6_OTA过程监控\\         YpOtaMonitor.exe    后台推送 OTA 时：先检查要接的硬件、要关的程序，再只读监控进度到走完
  7_GR试运行卡点读取\\     YpTrialProbe.exe    GR 停在 Boot TRIAL 不确认时：用板上这版的 .map/.hex，J-Link 只读判断卡在哪一步
  budget.json             OTA 大小红线（所有工具共用；只改这一个文件，并在 _history 里写日期和原因）
  luatools依赖版本.txt    工具包自带的 Luatools 衍生文件及其版本、校验值
  维护人员-升级Luatools步骤.txt
  MANIFEST.sha256         本文件夹每个文件的 sha256，拷贝或解压后可核对完整性

每个工具文件夹里都有“使用说明.txt”，窗口和命令行两种用法都有。

OTA 红线与必检（2026-11-04 起，超红线工具直接报错、不生成）
  GR 签名镜像 ≤ 393216（384 KiB）        2 号、3 号、4 号工具检查（比 GR 槽 441464 严，以它为准：整机 OTA 时 CAT1 要放得下）
  CAT1 脚本区 ≤ 507904（至少留 16 KiB）   1 号、4 号工具检查
  CAT1 升级包 .sota ≤ 262144              3 号工具检查
  OTA 时 CAT1 可用 ≥ GR 签名镜像 + 32768   3 号、4 号工具检查（16 KiB 保留 + 16 KiB OTA 过程增长余量）
  OTA 必检功能（1 号工具第 [4b] 步）：发令前清 CAT1 日志、OTA 中不写日志、保电锁，缺一项就报错
  多次升级：4 号工具读设备时报告 OTA 状态记录大小（每次约 +170 字节），超过 4096 提醒

常用顺序（做一次整机 OTA）
  4 号工具改两个固件的版本 → GR 固件编译（Keil F7 或 GCC）→ 4 号工具检查空间并读设备可用空间 → 2 号工具检查并签名 → 把 Air780EGH 的 main.lua 改成目标版本 → 3 号工具生成 CAT1 包 →
  3 号工具生成授权文件 → 3 号工具检查并打包 → 上传平台后核对整包 MD5；
  CAT1 本身刷机（Luatools）用 1 号工具生成 USB_IMPORT。

2026-11-08 补充（流程变化与刷机注意）
  整机 OTA 的一键流程和评审门属于项目内部工具，不在本工具包里；本工具包的 1、2、3、4 号工具是它的底层，也可以单独使用。
  打包前要有评审记录（逐项评审人和理由）；评审声明是人的判断，工具不替你下。
  GR 固件必须是你在 Keil 里 F7 编出的、晚于所有源码改动的 HEX；改了源码要重新 F7。
  Luatools 刷 CAT1（出厂或台架换新基线；OTA 不需要刷）：
    - 先点“删除全部”清空脚本列表，再添加 USB_IMPORT 目录（否则会静默沿用旧文件）。
    - 想清掉设备上的 OTA 状态（SPENT、旧试装票、遗留任务）：必须勾“清除KV分区”和“清除FS分区”。
      不勾 = 保留 FS/KV，OTA 状态也一起保留。清除会丢绑定号码、MQTT/SIP 参数，需要后台重新下发。
    - 板子是干净的 IDLE、做正常连续升级时不用勾。
    - 刷完用信标核对：IDLE，TRIAL=nil（清过）或 RUNNING（没清）；刷前关掉占用 COM21/COM23 的日志程序。
  串口号因台架而异（GR 命令行口、CAT1 的 3 个口以你的设备管理器为准）；Luatools 会占用 CAT1 的日志口，刷机前关掉别的占用程序。
  OTA 期间不要按键、不要碰板子；CAT1 在 GR 空闲约 60 秒后会被断电，台架上要有保电手段（项目里的保电脚本，或手工保持活动）。
  改版本号：只用 4 号工具（YpVersionTool 的“改版本”），不要手改。它把 GR 版本头、CAT1 main.lua、firmware_version.json 的版本和构建号改成同一个，只管这些；升级范围不再写进源码。
整机 OTA 的步骤（2026-11-10 起：出厂的机器就能接收，不需要接收端，不需要逐台刷机）
  例：设备现在是 1.5.24，要升级到 1.5.25。流程：改版本 -> 编译 -> 签名 -> 打包 -> 上传 -> 推送。
    1. 4 号工具“改版本”：新版本填 1.5.25（构建号比 1.5.24 的大）。
    2. Keil F7 编译 GR（增量编译，编完不要再打开 Keil）。
    3. 2 号工具：给编出来的 hex 签名，得到 GR5526_1.5.25_bNN_signed.bin。
    4. 3 号工具：生成 CAT1 包 -> 生成授权文件（源版本填设备现在的 1.5.24）-> 检查并打包 -> 记下“平台整包 MD5”。
       CAT1 可用空间：用 4 号工具“读取设备可用空间”读到的数。
    5. 把 YP001_1.5.24---1.5.25_FIRST.zip 上传平台，核对 MD5。
    6. 后台对设备推送 1.5.25（设备要在线、电量够）。
  源版本不同的设备要各打一个包（1.5.23 的设备用 1.5.23---1.5.25 的包），因为包只认它的源版本。
  这条规则对 GR 和 CAT1 一样：升级包的清单写明源版本和目标版本，设备只接收“源版本 = 自己当前版本、目标版本更高”的包。
  以前（2026-11-09 之前）CAT1 里写死了升级范围和包的 MD5，每个包要配一个“接收端”，已经取消。旧固件的设备要用 Luatools 刷一次新基线。

密钥（重要）
  私钥不在这个文件夹里，也不要放进来：签名时由操作人员在窗口里选择私钥文件（公钥由它自动导出），工具只在临时目录放一份，用完覆写删除。
  把这个文件夹打包给别人之前，请确认里面没有 .key 文件或其他私钥。（本工具包生成时已经自动检查过一次。）
  现在用的是本地测试密钥（OTA_TEST_*），不是产品发布密钥。

Luatools 版本（重要）
  工具包自带的 Luatools 衍生文件取自：Luatools {lt_version}（构建 {lt_build}），脚本资源 {resource}，底包 {soc}。
  这些文件的版本和校验值见 luatools依赖版本.txt。
  Luatools 升级以后（它会自动更新脚本资源），请在 1 号或 3 号工具里点“检查依赖版本”，在弹出的窗口里选已安装的 Luatools 文件夹
  （通常是 D:\\Installers；点“取消”则只检查工具包自带的文件）。工具会列出本机 Luatools 里哪些文件已经和工具包不同，以及需要升级的文件。
  结果里绿色的“提示”和“结论：不影响使用，不用升级”表示没有影响，什么都不用做：工具按固定校验值使用自带文件，本机 Luatools 升级不影响它，
  现有设备、已生成的刷机目录和 OTA 包也不受影响。
  红色表示必须处理：只有工具包自带的文件缺失或被改动才会出现，请重新拿一份完整的工具包（不要自己替换文件）。
  只有当你决定让设备也改用新的厂商库时才需要升级：把检查结果发给工具维护人，由维护人用新库重新生成、实板验证后发新的工具包
  （步骤见“维护人员-升级Luatools步骤.txt”）；在那之前继续使用现有工具包。
'''

MAINT = '''维护人员：Luatools 升级后更新工具包
==================================

触发：同事（或你自己）在“检查依赖版本”里看到绿色的“提示”并决定要升级（或红色的“必须处理”）。

1. 看清楚变了什么
     YpOtaPack.exe --deps --luatools <新的 Luatools 目录>
   输出会列出：Luatools 版本是否变了；哪些工具文件（luac、soc_tools、7z）变了；较新的脚本资源版本里哪些厂商库
   （air1103、es8311、exsipclient、exsipproto）和工具包不同。
2. 评估
   - 只有 luac / soc_tools / 7z 变了：确认编译产物字节码是否仍然一致（跑下面第 5 步的全部自测，并对比生成的 USB_IMPORT 与旧版）。
   - 厂商库变了：设备固件的组成就变了（它们会被编译进 CAT1 脚本包和刷机目录），必须用新库重新生成并在实板验证，
     不能只替换文件。
   - 底包 SoC 变了（LuatOS-SoC_V2052_Air780EGH_113.soc）：升级分区和 OTA 的假设都要重新核对，这是更大的变更。
3. 更新自带文件（仓库里的“真值”位置）
   - tools/toolkit/luatools_bundle/ 下对应文件：_temp/tools/luac_64bit.exe、soc_tools.exe，
     _temp/uis_download/7zip/32/7z.exe 和 7z.dll，resource/soc_script/<资源版本>/lib/*.lua（目录名改成新资源版本）。
   - Air780EGH/vendor_luac/*.luac 和 vendor.json 里的 sha256（从 Luatools 合并输出 _temp/soc_disk/disk/ 取，或由新库源码编译）。
4. 更新校验值
   - tools/ota/portable/Cat1Native.cs：LibHashes（4 个库）、字符串 resource\\soc_script\\<资源版本>\\lib、
     Tool(...) 里 luac_64bit.exe / soc_tools.exe / 7z.exe 的 sha256、SocHash（底包变了才改）。
   - tools/cat1_release/src/Cat1UsbImport.cs：LuacSha256。 tools/ota/pack_tool/src/YpOtaPack.cs 无需改。
   - tools/toolkit/luatools_version.json：version、build、resource_version、exe_size、exe_sha256（Luatools 版本信息见其日志 log\\tools_*.txt）。
5. 重新生成并自测
     python tools/toolkit/make_toolkit.py --toolkit-version <新版本号，如 2026.11.05-1>
     python tools/cat1_release/test_usb_import_tool.py
     python tools/gr_release/test_gr5526_tool.py
     python tools/ota/pack_tool/test_ota_pack_tool.py
     python tools/toolkit/test_toolkit.py
6. 发布：把新的 YP001_工具包 整个文件夹发给同事，让他们替换旧的；在文档里记录这次升级的原因和实板验证结果。
'''


def human_table(deps):
    lt, soc = deps['luatools'], deps['soc']
    lines = [f"工具包 {deps['toolkit_version']}（生成 {deps['generated']}）", '',
             f"Luatools      {lt['version']}（构建 {lt['build']}；Luatools_v3.exe {lt['exe_size']} 字节，sha256 {lt['exe_sha256']}）",
             f"脚本资源      {lt['resource_version']}",
             f"底包 SoC      {soc['name']}  sha256 {soc['sha256']}（{soc['where']}）", '', '工具包自带的 Luatools 衍生文件：', '']
    for f in deps['files']:
        where = f['luatools_path'].replace('{resource}', lt['resource_version']) or '（随脚本资源版本更新，无单独位置）'
        lines += [f"  {f['name']}", f"      作用    {f['role']}", f"      sha256  {f['sha256']}",
                  f"      用于    {'、'.join(f['used_by'])}", f"      在 Luatools 里的位置  {where}"]
    lines += ['', 'Luatools 升级后：在工具里点“检查依赖版本”，在弹出的窗口里选已安装的 Luatools 目录；有变化时按“先看这里.txt”处理。']
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'YP001_工具包'))
    ap.add_argument('--toolkit-version', default=datetime.now().strftime('%Y.%m.%d') + '-1')
    ap.add_argument('--no-build', action='store_true', help='reuse the already built tool folders')
    a = ap.parse_args()
    out = Path(a.out)
    if not a.no_build:
        for _, build_dir, _ in TOOLS:
            subprocess.run([PY, str(build_dir / 'build_exe.py')], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([PY, str(HERE / 'gen_deps.py'), '--out', str(HERE / '_deps.json'), '--toolkit-version', a.toolkit_version], check=True, stdout=subprocess.DEVNULL)
    deps = json.loads((HERE / '_deps.json').read_text(encoding='utf-8'))
    (HERE / '_deps.json').unlink()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for folder, build_dir, built in TOOLS:
        dst = out / folder
        shutil.copytree(build_dir / built, dst, ignore=shutil.ignore_patterns('last_port.txt', 'logs'))
        if 'files' in deps and folder in (TOOLS[0][0], TOOLS[2][0]):   # only the CAT1 and pack tools use Luatools files
            (dst / 'luatools_deps.json').write_text(json.dumps(deps, ensure_ascii=False, indent=1), encoding='utf-8')
    lt = deps['luatools']
    (out / '先看这里.txt').write_text(README.format(version=a.toolkit_version, lt_version=lt['version'], lt_build=lt['build'], resource=lt['resource_version'],
                                                     soc=deps['soc']['name']).replace('\n', '\r\n'), encoding='utf-8')
    (out / 'luatools依赖版本.txt').write_text(human_table(deps).replace('\n', '\r\n'), encoding='utf-8')
    (out / '维护人员-升级Luatools步骤.txt').write_text(MAINT.replace('\n', '\r\n'), encoding='utf-8')
    (out / 'luatools_deps.json').write_text(json.dumps(deps, ensure_ascii=False, indent=1), encoding='utf-8')
    shutil.copy2(BUDGET, out / 'budget.json')
    hits = private_material(out)
    if hits:
        shutil.rmtree(out)
        sys.exit('STOP: private key material found in the toolkit, folder removed: ' + ', '.join(hits))
    lines = [f'{sha(p)} *{p.relative_to(out).as_posix()}' for p in sorted(out.rglob('*')) if p.is_file()]
    (out / 'MANIFEST.sha256').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    size = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    print(f'toolkit {a.toolkit_version}: {out}  ({len(lines)} files, {size / 1048576:.1f} MiB, no private key material)')


if __name__ == '__main__':
    main()

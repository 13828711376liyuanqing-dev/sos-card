"""YP001 GR5526 有线烧录工具（只用 J-Link，不需要 Keil 工程）。

SAM | 2026-11-01 +08:00 | 把 Gr5526Tool 签好的镜像烧进 A 槽，并让板上 Boot 认它：
  1. 只读整片快照（烧前备份）；
  2. 从快照取出板上现有 Boot，只改它内嵌的 40 字节基线描述符（长度 + 版本号 + 正文 SHA-256），其余字节不动；
  3. 擦除 scratch + Boot 日志 + GR owner（0x2F6000-0x2FAFFF）和 B 槽（0x280000-0x2EBFFF），Boot 走 EMPTY + 基线启动；
  4. 写 A 槽（0x202000）和配对 Boot（0x2EC000），J-Link 校验；
  5. 复位一次，再读整片核对：A、Boot、清空区、B 槽、NVDS 不变。
Flash 算法用 GR5xxx_16MB_Flash.FLM，通过 J-Link 的 JLinkDevices 机制注册成设备 YP001_GR5526。
用法：python yp001_gr_jlink_flash.py <签名镜像.bin> [--yes] [--port COM26]
"""
import argparse, hashlib, re, shutil, struct, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
JLINK = Path(r'C:\Program Files\SEGGER\JLink\JLink.exe')
DEVICE = 'YP001_GR5526'
FLASH_BASE, SNAP_SIZE = 0x200000, 0x100000
A_ADDR, B_ADDR, SLOT = 0x202000, 0x280000, 0x6C000
BOOT_ADDR, BOOT_MAX = 0x2EC000, 0xA000
CLEAR_ADDR, CLEAR_END = 0x2F6000, 0x2FB000            # scratch, Boot journal x2, GR owner x2
NVDS_ADDR = 0x2FE000
DESC_OFF = 0x71F0                                      # baseline descriptor inside Boot (after approvals + 3 hashes)
LAYOUT_HASH = bytes.fromhex('4f46b271bc865a8f')
SIG_TAIL = 904
# SAM | 2026-11-07 +08:00 | Scoped maintenance pins every session to one probe and can keep loader files local.
PROBE_SERIAL = None
DEVICE_DIRECTORY = None
XML = f'''<DataBase>
  <Device>
    <ChipInfo Vendor="Goodix" Name="{DEVICE}" Core="JLINK_CORE_CORTEX_M4" WorkRAMAddr="0x20000000" WorkRAMSize="0x8000" />
    <FlashBankInfo Name="Flash" BaseAddr="0x00200000" MaxSize="0x01000000" Loader="GR5xxx_16MB_Flash.FLM" LoaderType="FLASH_ALGO_TYPE_OPEN" AlwaysPresent="1" />
  </Device>
</DataBase>
'''


def log(msg):
    print(msg, flush=True)


def install_device():
    """Register the GR5526 flash loader with J-Link (per-user folder, no admin)."""
    import os
    d = DEVICE_DIRECTORY or Path(os.environ['APPDATA']) / 'SEGGER' / 'JLinkDevices' / 'YP001'
    d.mkdir(parents=True, exist_ok=True)
    flm = HERE / 'GR5xxx_16MB_Flash.FLM'
    if not flm.exists():
        sys.exit('缺少 GR5xxx_16MB_Flash.FLM（应与本工具放在同一文件夹）')
    if not (d / flm.name).exists() or (d / flm.name).read_bytes() != flm.read_bytes():
        shutil.copy2(flm, d / flm.name)
    if not (d / 'JLinkDevices.xml').exists() or (d / 'JLinkDevices.xml').read_text(encoding='utf-8') != XML:
        (d / 'JLinkDevices.xml').write_text(XML, encoding='utf-8')
    return d


def jlink(device, commands, logfile, timeout=900):
    # J-Link V7.54 does not pick up the per-user device folder at start-up (it then waits on a device dialog), so connect as
    # a plain Cortex-M4 and select the GR5526 device after pointing the DLL at this tool's XML.
    pre = []
    if device == DEVICE:
        pre = [f'exec JLinkDevicesXMLPath={install_device()}\\', f'device {DEVICE}']
    script = logfile.with_suffix('.jlink')
    script.write_text('\n'.join(pre + commands + ['exit']) + '\n', encoding='ascii')
    select = ['-SelectEmuBySN', str(PROBE_SERIAL)] if PROBE_SERIAL is not None else []
    r = subprocess.run([str(JLINK)] + select + ['-NoGui', '1', '-ExitOnError', '1', '-device', 'CORTEX-M4', '-if', 'SWD',
                        '-speed', '4000', '-autoconnect', '1', '-CommandFile', str(script)],
                       capture_output=True, text=True, errors='replace', timeout=timeout)
    logfile.write_text(r.stdout + r.stderr, encoding='utf-8')
    return r.returncode, r.stdout + r.stderr


def snapshot(out, logdir, name):
    code, text = jlink('CORTEX-M4', [f'savebin {out},0x{FLASH_BASE:X},0x{SNAP_SIZE:X}'], logdir / f'{name}.log')
    data = out.read_bytes() if out.exists() else b''
    if len(data) != SNAP_SIZE:
        sys.exit(f'快照失败（{name}），请看 {logdir / (name + ".log")}')
    return data


def version_number(app):
    m = re.search(rb'YP001_FW\|GR5526\|(\d{3})\.(\d{3})\.(\d{3})\|(\d+)\|END', app)
    if not m:
        sys.exit('签名镜像里找不到版本标记 YP001_FW|GR5526|x.y.z|build|END')
    a, b, c = (int(x) for x in m.groups()[:3])
    return a * 1000000 + b * 1000 + c, f'{a}.{b}.{c}', int(m.group(4))


def main(preflight=None):
    global PROBE_SERIAL, DEVICE_DIRECTORY
    ap = argparse.ArgumentParser(description='YP001 GR5526 J-Link 有线烧录（签名镜像 + 配对 Boot）')
    ap.add_argument('image', nargs='?', help='Gr5526Tool 生成的 GR5526_x.y.z_bN_signed.bin（不填则运行时询问）')
    ap.add_argument('--yes', action='store_true', help='不再询问确认（默认要求输入 FLASH）')
    ap.add_argument('--port', default='COM26', help='GR CLI 串口，烧完读 fw_version；填 none 跳过')
    # SAM | 2026-11-04 +08:00 | Factory rule: Name / Room / Campus come only from the platform, nothing kept locally, so the
    # last step clears the name store (GR CLI name_store clear) and checks it is empty. Bench recovery can keep the name.
    ap.add_argument('--keep-name', action='store_true', help='不清空姓名/房号/园区（台架恢复板子时用；出厂必须清空）')
    ap.add_argument('--probe-sn', type=int, help='固定J-Link序列号，避免多个探针间切换')
    ap.add_argument('--device-dir', type=Path, help='本次维护的本地XML/FLM目录，不改用户全局注册')
    args = ap.parse_args()
    if args.probe_sn is not None and args.probe_sn <= 0:
        ap.error('--probe-sn must be positive')
    PROBE_SERIAL = args.probe_sn
    DEVICE_DIRECTORY = args.device_dir.resolve() if args.device_dir else None

    if not args.image:
        args.image = input('请把签名镜像 GR5526_x.y.z_bN_signed.bin 拖进来（或输入路径），回车：')
    args.image = args.image.strip().strip('"').strip()
    img = Path(args.image)
    if not img.is_file() or img.suffix.lower() != '.bin':
        sys.exit(f'找不到签名镜像文件：{args.image}（要的是 Gr5526Tool 生成的 .bin）')
    app = img.read_bytes()
    if not 8 + SIG_TAIL < len(app) <= SLOT:
        sys.exit(f'镜像大小 {len(app)} 不对（必须是签名后的 .bin，且不超过 {SLOT}）')
    ver, ver_text, build = version_number(app)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    logdir = HERE / 'logs' / f'{stamp}_{ver_text}_b{build}'
    logdir.mkdir(parents=True, exist_ok=True)
    log(f'[1/6] 镜像 {Path(args.image).name}：{len(app)} 字节，版本 {ver_text} build {build}；记录目录 {logdir}')

    install_device()
    log('[2/6] 读烧前整片快照（只读）…')
    pre = snapshot(logdir / 'pre.bin', logdir, 'pre_snapshot')

    boot_region = pre[BOOT_ADDR - FLASH_BASE:BOOT_ADDR - FLASH_BASE + BOOT_MAX]
    boot = boot_region.rstrip(b'\xff')
    boot += b'\xff' * ((-len(boot)) % 4)
    if len(boot) < DESC_OFF + 40 or boot[DESC_OFF - 96:DESC_OFF - 88] != LAYOUT_HASH or \
            boot[DESC_OFF - 108:DESC_OFF - 96] != struct.pack('<III', 1, 1, 1):
        sys.exit('板上 Boot 不是预期的已配对 Boot（找不到描述符），停止，不写任何东西')
    desc = struct.pack('<II', len(app) - SIG_TAIL, ver) + hashlib.sha256(app[:-SIG_TAIL]).digest()
    new_boot = boot[:DESC_OFF] + desc + boot[DESC_OFF + 40:]
    diff = [i for i in range(len(boot)) if boot[i] != new_boot[i]]
    if any(not DESC_OFF <= i < DESC_OFF + 40 for i in diff):
        sys.exit('内部错误：Boot 改动超出 40 字节描述符')
    (logdir / 'app.bin').write_bytes(app)
    (logdir / 'boot_paired.bin').write_bytes(new_boot)
    (logdir / 'boot_before.bin').write_bytes(boot)
    log(f'[3/6] 配对 Boot：{len(boot)} 字节，只改描述符 {len(diff)} 字节（旧 {boot[DESC_OFF:DESC_OFF+8].hex()} → 新 {desc[:8].hex()}）')

    if not args.yes:
        log('将要：擦 0x2F6000-0x2FAFFF（Boot 日志/owner）和 B 槽，写 A 槽与 Boot，复位一次。NVDS 不动。')
        if input('确认请输入 FLASH：').strip() != 'FLASH':
            sys.exit('已取消，未写入任何东西')

    # SAM | 2026-11-07 +08:00 | Guard the actual captured Flash and loaded image at the write boundary, after any confirmation wait.
    if preflight is not None:
        preflight(pre, app, logdir)
    log('[4/6] 擦除并写入（J-Link + GR5526 Flash 算法）…')
    # SAM | 2026-11-05 +08:00 | J-Link erase includes its end address; stop before the next page, especially the name store at 0x2FB000.
    # The GR5526 flash algorithm records, per J-Link session, the first programmed address in SCA (0x200000) as the ROM boot
    # target. So A is written in one session and Boot (erased first, so it is really programmed) in a separate, last session.
    code1, text1 = jlink(DEVICE, ['h',
                                  f'erase 0x{CLEAR_ADDR:X} 0x{CLEAR_END - 1:X}',
                                  f'erase 0x{B_ADDR:X} 0x{B_ADDR + SLOT - 1:X}',
                                  f'loadbin {logdir / "app.bin"},0x{A_ADDR:X}',
                                  f'verifybin {logdir / "app.bin"},0x{A_ADDR:X}', 'r', 'g'], logdir / 'flash_app.log')
    code2, text2 = 1, ''
    if not code1:
        # Bench finding (11-01): the SCA boot record is only rewritten reliably by a Boot-only session started while GR runs;
        # read SCA back and repeat the Boot session (max 3 tries) until it points at Boot.
        for attempt in range(3):
            time.sleep(3)
            code2, text2 = jlink(DEVICE, ['h',
                                  f'erase 0x{BOOT_ADDR:X} 0x{BOOT_ADDR + BOOT_MAX - 1:X}',
                                  f'loadbin {logdir / "boot_paired.bin"},0x{BOOT_ADDR:X}',
                                  f'verifybin {logdir / "boot_paired.bin"},0x{BOOT_ADDR:X}',
                                  'r', 'g'], logdir / f'flash_boot_{attempt + 1}.log')
            sca_file = logdir / f'sca_{attempt + 1}.bin'
            jlink('CORTEX-M4', [f'savebin {sca_file},0x{FLASH_BASE:X},0x10'], logdir / f'sca_{attempt + 1}.log', timeout=60)
            sca = sca_file.read_bytes() if sca_file.exists() else b''
            ok = len(sca) == 16 and sca[8:16] == struct.pack('<II', BOOT_ADDR, BOOT_ADDR)
            log(f'   Boot 写入第 {attempt + 1} 次：SCA 启动目标 {"= Boot" if ok else "不对，重试"}')
            if code2 or ok:
                break
    code, text = code1 or code2, text1 + text2
    bad = [l for l in text.splitlines() if re.search(r'error|failed|mismatch|could not', l, re.I)
           and 'will now exit on Error' not in l]
    if text.count('Verify successful') < 2: bad.append('J-Link 没有报告两次 Verify successful')
    if code or bad:
        log('写入过程报错（详见 flash.log）：\n  ' + '\n  '.join(bad[:6]))
        log('板子可能处于半写状态：可用 pre.bin 恢复；先不要断电，把 flash.log 发给开发。')
        sys.exit(1)

    log('[5/6] 读回核对…')
    time.sleep(2)
    post = snapshot(logdir / 'post.bin', logdir, 'post_snapshot')
    o = lambda a: a - FLASH_BASE
    checks = {
        'A 槽 = 签名镜像': post[o(A_ADDR):o(A_ADDR) + len(app)] == app,
        'Boot = 配对 Boot': post[o(BOOT_ADDR):o(BOOT_ADDR) + len(new_boot)] == new_boot,
        'Boot 日志/owner 已清空': post[o(CLEAR_ADDR):o(CLEAR_END)] == b'\xff' * (CLEAR_END - CLEAR_ADDR),
        'B 槽已清空': post[o(B_ADDR):o(B_ADDR) + SLOT] == b'\xff' * SLOT,
        # SAM | 2026-11-04 +08:00 | The flashing never writes NVDS, but the new firmware runs before the readback and may
        # update it (e.g. moving the 1.5.8-1.5.10 name record to its Flash pages marks the NVDS tag deleted: bits 1->0 only).
        # Intact = header unchanged and no bit went 0->1 (no erase); the number of changed bytes is logged.
        'NVDS 完好（只有固件开机后的正常写入）': post[o(NVDS_ADDR):o(NVDS_ADDR) + 4] == pre[o(NVDS_ADDR):o(NVDS_ADDR) + 4] and
            all((b & ~a) == 0 for a, b in zip(pre[o(NVDS_ADDR):], post[o(NVDS_ADDR):])),
        'SCA 启动目标 = Boot(0x2EC000)': post[8:16] == struct.pack('<II', BOOT_ADDR, BOOT_ADDR),
    }
    nv_changed = sum(1 for a, b in zip(pre[o(NVDS_ADDR):], post[o(NVDS_ADDR):]) if a != b)
    if nv_changed:
        log(f'   注意：NVDS 有 {nv_changed} 字节被新固件开机后改写（如姓名记录迁移到 Flash 页），不是烧录写的')
    for k, v in checks.items():
        log(f'   {"OK  " if v else "FAIL"} {k}')
    if not all(checks.values()):
        sys.exit('读回不一致，停止。证据在 ' + str(logdir))

    if args.port.lower() != 'none':
        log(f'[6/6] 读 GR 版本（{args.port}）…')
        try:
            import serial  # optional
        except ImportError:
            serial = None
        text = ''
        if serial:
            try:
                with serial.Serial(args.port, 115200, timeout=0.2) as s:
                    time.sleep(3); s.reset_input_buffer(); s.write(b'fw_version\r\n')
                    end = time.time() + 3
                    while time.time() < end:
                        text += s.read(4096).decode('utf-8', 'replace')
            except Exception as e:
                text = f'串口打不开：{e}'
        else:
            r = subprocess.run(['powershell', '-NoProfile', '-Command',
                                f"$p=[IO.Ports.SerialPort]::new('{args.port}',115200);$p.Open();Start-Sleep 8;$p.ReadExisting()|Out-Null;"
                                "$p.Write(\"fw_version`r`n\");Start-Sleep 3;$p.ReadExisting();$p.Close()"],
                               capture_output=True, text=True, errors='replace', timeout=30)
            text = r.stdout + r.stderr
        line = next((l for l in text.splitlines() if 'FW_VERSION' in l), text.strip()[:200])
        log('   ' + line)
        if not args.keep_name:
            log('[出厂] 清空姓名/房号/园区和字形（name_store clear），再核对为空…')
            if not serial:
                sys.exit('没有 pyserial，出厂清空没做：请在 GR 串口手动执行 name_store clear 和 name_store status')
            out = ''
            try:
                with serial.Serial(args.port, 115200, timeout=0.2) as s:
                    s.reset_input_buffer()
                    for cmd in (b'name_store clear\r\n', b'name_store status\r\n'):
                        s.write(cmd)
                        end = time.time() + 2
                        while time.time() < end:
                            out += s.read(4096).decode('utf-8', 'replace')
            except Exception as e:
                sys.exit(f'出厂清空失败：串口打不开（{e}）')
            st = next((l for l in out.splitlines() if 'resident=' in l), '')
            log('   ' + (st or out.strip()[:200]))
            empty = 'resident=--' in st and 'glyphs=0 ' in st and 'stored_bytes=0' in st
            if '[NAME] cleared' in out and 'glyphs=0 ' in st and 'stored_bytes=0' in st and 'resident=set' in st:
                # SAM | 2026-11-04 +08:00 | Storage is empty but a TEST_DATA build refills a test name in RAM (bench 16:2x).
                sys.exit('存储已清空，但这版固件开着 TEST_DATA（测试名只在内存里，会显示在屏幕上）：出厂固件必须关掉 TEST_DATA 再烧')
            if '[NAME] cleared' not in out or not empty:
                sys.exit('出厂清空没有确认（name_store status 不是空的）：请检查后重试')
            log('   OK  姓名/房号/园区和字形已清空，等后台下发')
    elif not args.keep_name:
        log('注意：没有串口（--port none），出厂清空没做：请在 GR 串口执行 name_store clear 并核对 name_store status 为空')
    log(f'完成。全部记录：{logdir}')


if __name__ == '__main__':
    main()

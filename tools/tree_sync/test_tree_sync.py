"""tree_sync 沙盒测试：在临时目录里复制一份 CAT1 源码当“同事侧”和“项目侧”，模拟同事改动，检查工具行为。

SAM | 2026-11-02 +08:00 | 不碰真实目录。用法：python test_tree_sync.py <CAT1 源码目录>
检查：baseline 生成内容存档；pull 跳过受保护文件、只拉同事单边改动；两边都改的文件由 merge 合成；ota_guard 拦下违规。
"""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1])
env = dict(os.environ, PYTHONIOENCODING='utf-8')


def run(tool, *args):
    r = subprocess.run([sys.executable, str(tool / 'tree_sync.py'), *args], capture_output=True, text=True, encoding='utf-8', env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


def edit(p, old, new):
    b = p.read_bytes()
    assert b.count(old.encode()) >= 1, (p.name, old)
    p.write_bytes(b.replace(old.encode(), new.encode(), 1))


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    tool, colleague, ours, arc = td / 'tool', td / 'colleague', td / 'ours', td / 'arc'
    tool.mkdir(); arc.mkdir()
    for f in ('tree_sync.py', 'merge3.py', 'ota_guard.py'):
        shutil.copy2(HERE / f, tool / f)
    shutil.copytree(SRC, colleague / 'Air780EGH'); shutil.copytree(SRC, ours / 'Air780EGH')
    c = json.loads((HERE / 'sync_config.json').read_text(encoding='utf-8'))
    c.update({k: str(v) for k, v in zip([k for k in c if k.endswith('_root')], [colleague, ours])})
    c['archive_dir'] = str(arc)
    c['areas'] = [a for a in c['areas'] if a['name'] == 'cat1']
    (tool / 'sync_config.json').write_text(json.dumps(c, ensure_ascii=False), encoding='utf-8')
    C, O = colleague / 'Air780EGH', ours / 'Air780EGH'

    out = run(tool, 'baseline')
    assert 'tree_sync_base_' in out and list(arc.glob('tree_sync_base_*.zip')), out
    # 同事：改受保护文件、单边改 ntp.lua、和我们各改 sip.lua 相隔两行的不同行
    edit(C / 'ota_store.lua', '\n', '\n-- colleague edit\n')
    edit(C / 'ntp.lua', '[NTPSYNC]', '[NTPSYNC2]')
    edit(C / 'sip.lua', 'SIP_CONFIG.sip_username = user_cfg.username', 'SIP_CONFIG.sip_username = user_cfg.user')
    edit(O / 'sip.lua', 'SIP_CONFIG.sip_server_addr = user_cfg.sip_url', 'SIP_CONFIG.sip_server_addr = tostring(user_cfg.sip_url)')
    out = run(tool, 'scan')
    assert 'BLOCK=' in out and 'BLOCK=0' not in out, out  # ota_store.lua 被改 -> R1
    out = run(tool, 'pull', '--yes')
    assert '跳过（OTA 受保护' in out and 'ota_store.lua' in out, out
    assert (O / 'ntp.lua').read_bytes() == (C / 'ntp.lua').read_bytes(), 'single-side change pulled'
    assert b'colleague edit' not in (O / 'ota_store.lua').read_bytes(), 'protected file untouched'
    assert list(arc.glob('tree_sync_pull_*.zip')), 'backup before overwrite'
    out = run(tool, 'merge')
    merged = sorted((tool / 'reports').glob('merge_*/merged/sip.lua'))
    assert merged, out
    m = merged[-1].read_text(encoding='utf-8')
    assert 'user_cfg.user\n' in m.replace('\r', '') and 'tostring(user_cfg.sip_url)' in m, 'both edits kept'
    assert '<<<<<<<' not in m, 'separate-line edits merge cleanly'
    # 两边改同一行 -> 冲突标记
    edit(O / 'sip.lua', 'user_cfg.username', 'user_cfg.uname')
    out = run(tool, 'merge')
    m = sorted((tool / 'reports').glob('merge_*/merged/sip.lua'))[-1].read_text(encoding='utf-8')
    assert '<<<<<<< OURS' in m, 'same-line edits must conflict'
    print('PASS baseline/scan/pull(protected skipped, backup)/merge(clean + conflict)')

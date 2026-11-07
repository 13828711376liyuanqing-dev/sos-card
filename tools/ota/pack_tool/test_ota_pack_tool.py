"""SAM | 2026-10-30 10:46 +08:00 | Self-test of YpOtaPack_Tool/YpOtaPack.exe run from a copy of the folder (as on another PC), for the
range 1.5.2 -> 1.5.3, which is NOT in the packager's built-in list: so the signed authorization file is what admits it.
Full chain with the standalone tools: CAT1 sources -> cat1 (sota + review) ; GR image -> Gr5526Tool sign ; auth ; pack ; verify ; faults."""
import base64
import glob
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KEYS = ROOT / 'tools/toolkit/test_keys'
SRC = ROOT / 'Air780EGH'
GR_TOOL = ROOT / 'tools/gr_release/GR5526_Tool/Gr5526Tool.exe'
# SAM | 2026-11-04 +08:00 | The 1.5.2 payload (438472 signed) is above the 393216 OTA red line the tools now enforce; derive the
# samples from the board-verified 1.5.10 b14 image. Its marker has a 2-digit build, so the samples use builds 70/80 (same length).
SIGNED_152 = Path(glob.glob(str(ROOT / 'firmware_releases/ota_1.5.9_to_1.5.10_20261104_1201/1_GR*/*_signed.bin'))[0])
ID_OLD = b'YP001_FW|GR5526|001.005.010|14|END'


def other_public_xml(path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    n = rsa.generate_private_key(65537, 2048).public_key().public_numbers().n
    path.write_text(f'<RSAKeyValue><Modulus>{base64.b64encode(n.to_bytes(256, "big")).decode()}</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>', encoding='utf-8')


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tool = tmp / 'tool'
        shutil.copytree(HERE / 'YpOtaPack_Tool', tool)
        exe = str(tool / 'YpOtaPack.exe')
        before = set(Path(tempfile.gettempdir()).glob('yp_*'))
        priv, pub = KEYS / 'OTA_TEST_PRIVATE.key', KEYS / 'OTA_TEST_PUBLIC.xml'

        def run(*args, program=exe):
            r = subprocess.run([program] + [str(a) for a in args], capture_output=True, text=True, encoding='utf-8', errors='replace')
            return r.returncode, r.stdout

        # ---- target sources: the repo sources with the version set to 1.5.3 / build 70 ----
        def make_source(name, build):
            s = tmp / name
            s.mkdir()
            for f in list(SRC.glob('*.lua')) + list(SRC.glob('*.mp3')):
                shutil.copy2(f, s / f.name)
            (s / 'soc').mkdir(); shutil.copy2(SRC / 'soc' / 'LuatOS-SoC_V2052_Air780EGH_113.soc', s / 'soc')
            m = (s / 'main.lua').read_bytes().decode('utf-8')
            # set the identity whatever version the repository is at today (the test must not depend on it)
            m = re.sub(r'(?m)^VERSION = "[0-9.]+"', 'VERSION = "001.005.003"', m)
            m = re.sub(r'(?m)^PRODUCT_VERSION = "[0-9.]+"', 'PRODUCT_VERSION = "1.5.3"', m)
            m = re.sub(r'(?m)^FW_RELEASE_BUILD = \d+', 'FW_RELEASE_BUILD = %d' % build, m)
            m = re.sub(r"(?m)^OTA_TRIAL_SOURCE='[0-9.]+'", "OTA_TRIAL_SOURCE='1.5.2'", m)
            m = re.sub(r"(?m)^OTA_TRIAL_TARGET='[0-9.]+'", "OTA_TRIAL_TARGET='1.5.3'", m)
            (s / 'main.lua').write_bytes(m.encode('utf-8'))
            return s
        src = make_source('src', 70)

        # 1. cat1: sources -> sota + review.json; refuses when main.lua is not at the target version
        old_src = tmp / 'src_old'; shutil.copytree(src, old_src)
        (old_src / 'main.lua').write_bytes((old_src / 'main.lua').read_bytes().replace(b'PRODUCT_VERSION = "1.5.3"', b'PRODUCT_VERSION = "1.5.2"'))
        code, log = run('cat1', '--source', old_src, '--out', tmp / 'c_old')
        assert code == 1 and '目标版本' in log and not list((tmp / 'c_old').glob('*.sota')), log
        code, log = run('cat1', '--source', src, '--out', tmp / 'cat', '--basis', 'self-test', '--host-check', 'host', '--not-verified', 'device')
        assert code == 0, log
        sota = next((tmp / 'cat').glob('*.sota')); review = tmp / 'cat/review.json'
        assert (tmp / 'cat' / (sota.name + '.json')).exists() and review.exists() and '001.005.003' in sota.name, log
        rv = json.loads(review.read_text(encoding='utf-8'))
        assert rv['source_version'] == '1.5.2' and rv['target_version'] == '1.5.3' and 'main.lua' not in rv['source_sha256'] and rv['native_installation_accepted'] is False

        # 2. GR images for 1.5.3 (b70 and a different b80), signed by the standalone GR tool
        payload = SIGNED_152.read_bytes()[:-904]
        for build in (70, 80):
            p = tmp / f'gr_{build}.bin'; p.write_bytes(payload.replace(ID_OLD, f'YP001_FW|GR5526|001.005.003|{build}|END'.encode()))
            code, log = run('sign', p, '--out', tmp / f'gr{build}', '--private', priv, '--public', pub, program=str(GR_TOOL)); assert code == 0, log
        gr7, gr8 = tmp / 'gr70/GR5526_1.5.3_b70_signed.bin', tmp / 'gr80/GR5526_1.5.3_b80_signed.bin'
        assert gr7.exists() and gr8.exists()

        # 3. auth needs explicit confirmations; then it is created and verifiable
        common = ['--gr', gr7, '--cat', sota, '--review', review, '--source', '1.5.2', '--private', priv, '--public', pub]
        code, log = run('auth', *common, '--out', tmp / 'a0.json'); assert code == 1 and '授权必须明确确认' in log and not (tmp / 'a0.json').exists(), log
        code, log = run('auth', *common[:6], '--source', '1.5.3', *common[8:], '--out', tmp / 'a1.json', '--reviewed', '--boot-verified'); assert code == 1 and '必须高于' in log, log
        code, log = run('auth', *common, '--out', tmp / 'auth.json', '--reviewed', '--boot-verified', '--basis', 'self-test'); assert code == 0, log
        code, log = run('auth', *common, '--out', tmp / 'auth.json', '--reviewed', '--boot-verified'); assert code == 1 and '已存在' in log, log

        # 4. pack: must name the file <prefix>_<from>---<to>_<suffix>.zip and pass every check
        pack = lambda out, gr=gr7, **kw: run('pack', '--gr', gr, '--cat', sota, '--review', kw.get('review', review), '--auth', kw.get('auth', tmp / 'auth.json'),
                                                   '--free', kw.get('free', 462848), '--out', out, '--private', priv, '--public', kw.get('public', pub),
                                                   '--prefix', kw.get('prefix', 'YP001'), '--suffix', kw.get('suffix', 'FIRST'))
        code, log = pack(tmp / 'out')
        assert code == 0, log
        zips = list((tmp / 'out').glob('*.zip'))
        assert [z.name for z in zips] == ['YP001_1.5.2---1.5.3_FIRST.zip'] and not list((tmp / 'out').glob('trial_work_*')) and not list((tmp / 'out').glob('verify_*'))
        z = zips[0]; assert 0 < z.stat().st_size <= 2097152 and 'MD5' in log and 'GR5526/payload.bin' in log and 'CAT1/payload.sota' in log
        # 4a. only the private key file is given (no --public): the public half is derived and the package is the same kind
        code, log = run('pack', '--gr', gr7, '--cat', sota, '--review', review, '--auth', tmp / 'auth.json', '--free', 462848, '--out', tmp / 'out_np', '--private', priv)
        assert code == 0 and len(list((tmp / 'out_np').glob('*.zip'))) == 1, log
        code, log = run('pack', '--gr', gr7, '--cat', sota, '--review', review, '--auth', tmp / 'auth.json', '--free', 462848, '--out', tmp / 'out_np2', '--private', pub)
        assert code == 1 and '私钥' in log, log
        # 4b. the same signed image given as .hex gives the same package (decoded to the equal BIN)
        def to_ihex(data, base=0x00202000):
            out, hi = [], None
            for off in range(0, len(data), 16):
                addr = base + off
                if addr >> 16 != hi:
                    hi = addr >> 16; rec = bytes([2, 0, 0, 4, hi >> 8, hi & 255]); out.append(':' + (rec + bytes([(-sum(rec)) & 255])).hex().upper())
                chunk = data[off:off + 16]; rec = bytes([len(chunk), (addr >> 8) & 255, addr & 255, 0]) + chunk
                out.append(':' + (rec + bytes([(-sum(rec)) & 255])).hex().upper())
            out.append(':00000001FF'); return chr(13).join(out) + chr(13)
        gr7_hex = tmp / 'gr70/GR5526_1.5.3_b70_signed.hex'; gr7_hex.write_text(to_ihex(gr7.read_bytes()), encoding='ascii')
        code, log = pack(tmp / 'out_hex', gr=gr7_hex); assert code == 0, log
        zh = list((tmp / 'out_hex').glob('*.zip'))
        assert len(zh) == 1 and not list(Path(tempfile.gettempdir()).glob('yp_gr_*.bin')), log
        # 5. verify: with the authorization it passes; without it the range is not admitted
        assert run('verify', '--zip', z, '--public', pub, '--auth', tmp / 'auth.json')[0] == 0
        code, log = run('verify', '--zip', z, '--public', pub); assert code == 1 and '版本范围' in log, log
        # 6. pack faults: refused, no package written
        wrong_pub = tmp / 'other_pub.xml'; other_public_xml(wrong_pub)
        tampered = json.loads((tmp / 'auth.json').read_text(encoding='utf-8')); tampered['record']['target_version'] = '1.5.4'
        (tmp / 'tampered.json').write_text(json.dumps(tampered), encoding='utf-8')
        edited = tmp / 'review2.json'; edited.write_bytes(review.read_bytes().replace(b'self-test', b'changed!!!'))
        bad = {
            'name_dashes': dict(prefix='A---B'), 'name_chars': dict(suffix='a/b'), 'tampered_auth': dict(auth=tmp / 'tampered.json'),
            'other_key': dict(public=wrong_pub), 'review_changed': dict(review=edited), 'too_little_space': dict(free=380000),
            # SAM | 2026-11-04 +08:00 | enough for the old rule (image + 16384 = 389352) but under the red line (image + 32768 = 405736)
            'under_red_line_space': dict(free=400000), 'no_space_value': dict(free='x'),
        }
        for name, kw in bad.items():
            out = tmp / ('o_' + name)
            code, log = pack(out, **kw)
            assert code == 1 and 'ERROR' in log and not list(out.glob('*.zip')), (name, log)
        code, log = pack(tmp / 'o_gr8', gr=gr8); assert code == 1 and '授权文件里的' in log and not list((tmp / 'o_gr8').glob('*.zip')), log
        old_sota = Path(glob.glob(str(ROOT / 'Air780EGH/_ota_release/ota152_20261029/target/native/*.sota'))[0])
        code, log = run('pack', '--gr', gr7, '--cat', old_sota, '--review', review, '--auth', tmp / 'auth.json', '--free', 462848, '--out', tmp / 'o_oldcat', '--private', priv, '--public', pub)
        assert code == 1 and not list((tmp / 'o_oldcat').glob('*.zip')), log
        code, log = pack(tmp / 'out'); assert code == 1 and '已存在' in log, log          # never overwrites a package
        # 7. no staged key / contract copies are left behind
        assert set(Path(tempfile.gettempdir()).glob('yp_keys_*')) <= before and set(Path(tempfile.gettempdir()).glob('yp_contracts_*')) <= before
    print('PASS YpOtaPack.exe (from a copied folder, range 1.5.2->1.5.3 admitted only by the signed authorization): cat1 builds sota+review (refuses a source not at '
          'the target version); GR image signed by Gr5526Tool; auth needs explicit confirmations; pack writes YP001_1.5.2---1.5.3_FIRST.zip (lists files/sizes/MD5, <=2 MiB); '
          'verify passes with the authorization and refuses the range without it; refuses --- in names, bad characters, tampered authorization, other key, changed review, '
          'too little CAT1 space, authorization for another GR image, wrong CAT1 package, overwrite; staged keys removed')


if __name__ == '__main__':
    main()

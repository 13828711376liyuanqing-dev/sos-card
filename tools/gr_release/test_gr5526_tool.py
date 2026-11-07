"""SAM | 2026-10-30 10:42 +08:00 | Self-test of GR5526_Tool/Gr5526Tool.exe, run from a copy of the tool folder (as on another PC).
Inputs are derived from the board-verified signed 1.5.10 image (1.5.2 until 2026-11-04), written as a plain BIN and as a GCC/objcopy-style HEX
(32-byte records), so the result does not depend on the compiler that produced them."""
import base64
import glob
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KEYS = ROOT / 'tools/toolkit/test_keys'
# SAM | 2026-11-04 +08:00 | The 1.5.2 image (438472 signed) is above the 393216 OTA red line the tool now enforces; use the
# board-verified 1.5.10 b14 image of the 2026-11-04 whole-device OTA.
SIGNED_152 = Path(glob.glob(str(ROOT / 'firmware_releases/ota_1.5.9_to_1.5.10_20261104_1201/1_GR*/*_signed.bin'))[0])
ID_RE = re.compile(rb'YP001_FW\|GR5526\|001\.005\.010\|14\|END')


def gcc_hex(data, base=0x202000, size=32):
    out, hi = [], None
    for off in range(0, len(data), size):
        a = base + off
        if a >> 16 != hi:
            hi = a >> 16
            r = bytes([2, 0, 0, 4, hi >> 8, hi & 255]); out.append(':' + r.hex().upper() + '%02X' % (-sum(r) & 255))
        c = data[off:off + size]; r = bytes([len(c), (a >> 8) & 255, a & 255, 0]) + c
        out.append(':' + r.hex().upper() + '%02X' % (-sum(r) & 255))
    out.append(':00000001FF')
    return '\r\n'.join(out) + '\r\n'


def other_public_xml(path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    n = rsa.generate_private_key(65537, 2048).public_key().public_numbers().n
    mod = base64.b64encode(n.to_bytes(256, 'big')).decode()
    path.write_text(f'<RSAKeyValue><Modulus>{mod}</Modulus><Exponent>AQAB</Exponent></RSAKeyValue>', encoding='utf-8')


def main():
    payload = SIGNED_152.read_bytes()[:-904]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tool = tmp / 'tool'
        shutil.copytree(HERE / 'GR5526_Tool', tool)
        exe = str(tool / 'Gr5526Tool.exe')
        temp_before = set(Path(tempfile.gettempdir()).glob('gr5526_keys_*'))

        def run(*args):
            r = subprocess.run([exe] + [str(a) for a in args], capture_output=True, text=True, encoding='utf-8', errors='replace')
            return r.returncode, r.stdout

        good_bin, good_hex = tmp / 'app.bin', tmp / 'app.hex'
        good_bin.write_bytes(payload); good_hex.write_text(gcc_hex(payload), encoding='ascii')
        priv, pub = KEYS / 'OTA_TEST_PRIVATE.key', KEYS / 'OTA_TEST_PUBLIC.xml'
        sign = lambda f, out, *x: run('sign', f, '--out', out, '--private', priv, '--public', pub, *x)

        # 1. check: BIN and GCC-style HEX, paired, with version expectations
        code, log = run('check', good_hex, '--pair', good_bin, '--expect-version', '1.5.10')
        assert code == 0 and '内容一致' in log and '1.5.10' in log, log
        assert run('check', good_bin)[0] == 0
        # 1a. only the private key file is chosen: the public half is derived (signing works without --public; a non-key file is refused)
        code, log = run('sign', good_hex, '--out', tmp / 'o_priv', '--private', priv, '--expect-version', '1.5.10'); assert code == 0, log
        signed_np = next((tmp / 'o_priv').glob('*_signed.bin')); assert run('verify', signed_np, '--public', pub)[0] == 0
        code, log = run('sign', good_hex, '--out', tmp / 'o_badkey', '--private', pub); assert code == 1 and '私钥' in log and not (tmp / 'o_badkey').exists(), log
        # 1b. size: an oversized HEX/BIN is refused with the actual size, the limit and the excess
        big_hex = tmp / 'big.hex'; big_hex.write_text(gcc_hex(bytes(441464 + 100), size=16), encoding='ascii')
        code, log = run('check', big_hex); assert code == 1 and '441564 字节' in log and '441464' in log and '100 字节' in log, log
        big_bin = tmp / 'big.bin'; big_bin.write_bytes(bytes(441464 + 5))
        code, log = run('check', big_bin); assert code == 1 and '441469 字节' in log and '5 字节' in log, log
        low_hex = tmp / 'low.hex'; low_hex.write_text(gcc_hex(bytes(64), base=0x200000, size=16), encoding='ascii')
        code, log = run('check', low_hex); assert code == 1 and '应用区之前' in log, log
        # 2. sign (both formats) -> verify with the tool -> the existing signed file verifies too
        code, log = sign(good_hex, tmp / 'o1', '--format', 'both', '--expect-version', '1.5.10')
        assert code == 0, log
        sb, sh = tmp / 'o1/GR5526_1.5.10_b14_signed.bin', tmp / 'o1/GR5526_1.5.10_b14_signed.hex'
        assert sb.exists() and sh.exists() and (tmp / 'o1/GR5526_1.5.10_b14_signed_record.json').exists()
        assert sb.read_bytes()[:-904] == payload and len(sb.read_bytes()) == len(SIGNED_152.read_bytes())
        rec = json.loads((tmp / 'o1/GR5526_1.5.10_b14_signed_record.json').read_text(encoding='utf-8'))
        assert rec['firmware']['product_version'] == '1.5.10' and rec['key_fingerprint'] and 'private' not in json.dumps(rec).lower()
        assert run('verify', sb, '--public', pub)[0] == 0 and run('verify', sh, '--public', pub)[0] == 0
        assert run('verify', SIGNED_152, '--public', pub)[0] == 0           # signature made yesterday still verifies
        # 3. output not overwritten without --force
        assert sign(good_hex, tmp / 'o1')[0] == 1 and sign(good_hex, tmp / 'o1', '--force')[0] == 0
        # 4. input faults
        (tmp / 'bad_sum.hex').write_text(gcc_hex(payload).replace(':20', ':21', 1), encoding='ascii')
        (tmp / 'no_eof.hex').write_text(gcc_hex(payload).replace(':00000001FF\r\n', ''), encoding='ascii')
        (tmp / 'no_id.bin').write_bytes(ID_RE.sub(b'X' * len(ID_RE.search(payload).group()), payload))
        (tmp / 'two_id.bin').write_bytes(payload + ID_RE.search(payload).group())
        (tmp / 'app.elf').write_bytes(payload)
        (tmp / 'huge.bin').write_bytes(payload + b'\xff' * (441464 - len(payload) + 100))   # over the GR slot
        # SAM | 2026-11-04 +08:00 | under the slot but over the 393216 OTA red line (signed = body + 904)
        (tmp / 'over_red.bin').write_bytes(payload + b'\xff' * (393216 - 904 - len(payload) + 100))
        (tmp / 'wrong_range.hex').write_text(':020000040030CA\r\n:0400000000112233' + '%02X' % (-(4 + 0x00 + 0x11 + 0x22 + 0x33) & 255) + '\r\n:00000001FF\r\n', encoding='ascii')
        (tmp / 'bad_vector.bin').write_bytes(b'\x00' * 8 + payload[8:])
        low = ID_RE.sub(b'YP001_FW|GR5526|001.005.001|5|END', payload)
        (tmp / 'v151.bin').write_bytes(low)
        for name in ('bad_sum.hex', 'no_eof.hex', 'no_id.bin', 'two_id.bin', 'app.elf', 'huge.bin', 'over_red.bin', 'wrong_range.hex', 'bad_vector.bin'):
            code, log = sign(tmp / name, tmp / ('x_' + name))
            assert code == 1 and 'ERROR' in log and not (tmp / ('x_' + name)).exists(), (name, log)
        # 5. already signed input cannot be signed again; hex/bin mismatch; version rules
        code, log = sign(sb, tmp / 'x_signed'); assert code == 1 and '已经是带签名' in log, log
        code, log = run('check', good_bin, '--pair', tmp / 'no_id.bin'); assert code == 1, log
        code, log = run('check', good_bin, '--expect-version', '1.5.3'); assert code == 1 and '不符' in log, log
        code, log = run('check', tmp / 'v151.bin', '--prev', good_bin); assert code == 1 and '低于上一版' in log, log
        same_ver_new_build = ID_RE.sub(b'YP001_FW|GR5526|001.005.002|5|END', payload)
        (tmp / 'b5.bin').write_bytes(same_ver_new_build)
        code, log = run('check', tmp / 'b5.bin', '--prev', good_bin); assert code == 1 and 'build' in log, log
        code, log = run('check', good_bin, '--prev', tmp / 'v151.bin'); assert code == 0 and '1.5.1/b5' in log, log
        # 6. key / contract faults
        wrong_pub = tmp / 'other_pub.xml'; other_public_xml(wrong_pub)
        code, log = run('sign', good_bin, '--out', tmp / 'x_key', '--private', priv, '--public', wrong_pub)
        assert code == 1 and 'ERROR' in log and not list((tmp / 'x_key').glob('*') if (tmp / 'x_key').exists() else []), log
        code, log = run('sign', good_bin, '--out', tmp / 'x_nokey', '--private', tmp / 'missing.key', '--public', pub); assert code == 1, log
        code, log = run('sign', good_bin, '--out', tmp / 'x_nolayout', '--private', priv, '--public', pub, '--layout', tmp / 'missing.json'); assert code == 1, log
        bad_layout = tmp / 'layout.json'; bad_layout.write_text('{"changed":true}', encoding='utf-8')
        assert run('verify', sb, '--public', pub, '--layout', bad_layout)[0] == 1                 # contract mismatch is detected
        assert run('verify', sb, '--public', wrong_pub)[0] == 1                                    # untrusted public key
        assert run('verify', sb, '--public', pub, '--pin', '0' * 64)[0] == 1                       # pinned fingerprint mismatch
        tampered = bytearray(sb.read_bytes()); tampered[1000] ^= 1; (tmp / 'tampered.bin').write_bytes(bytes(tampered))
        assert run('verify', tmp / 'tampered.bin', '--public', pub)[0] == 1                        # payload changed after signing
        # 7. the staged private key never survives, and nothing key-like lands in the output
        assert set(Path(tempfile.gettempdir()).glob('gr5526_keys_*')) == temp_before
        assert not [p for p in (tmp / 'o1').iterdir() if p.suffix in ('.key', '.xml')]
    print('PASS Gr5526Tool.exe (run from a copied folder): BIN and GCC-style HEX checked and paired; sign -> bin+hex+record, readback-verified, '
          'verifies (including the board-verified 11-04 signed 1.5.10 file); refuses bad checksum/EOF/identity (none, duplicate)/ELF/oversize/over the OTA red line/out-of-range/bad vectors/'
          're-signing/overwrite; version rules (expect, lower, build); wrong key pair, missing key or contract; verify detects contract, key, pin and tamper; '
          'staged private key removed')


if __name__ == '__main__':
    main()

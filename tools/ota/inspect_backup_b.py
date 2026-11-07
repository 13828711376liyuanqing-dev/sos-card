"""SAM | 2026-10-23 +08:00 | Compare occupied candidate B bytes to archived HEX without exposing data or granting erase permission."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
backup = ROOT / 'logs/ota_inventory_20261023_10895a6b23664e0297fa2d985c2785a3/flash.bin'
data = backup.read_bytes()
assert len(data) == 1048576
assert hashlib.sha256(data).hexdigest() == '883d8fcd7c1817f581e8a9ae9e5b2c27479b353cc2b779de7d55853b83b0cbf4'
occupied = {a: data[a-0x200000] for a in range(0x277000, 0x2ec000) if data[a-0x200000] != 255}
reports = []
paths = list((ROOT / 'firmware_releases').glob('*/GR5526/YP001_GR5526.hex'))
paths += list((ROOT / 'logs').glob('gsensor_*/main/YP001_GR5526.hex'))
paths += [ROOT / 'logs/hardware_debug/before_diag.hex']
# SAM | 2026-10-23 +08:00 | Historical application images are provenance only,
# never build inputs. Include pre-UART diagnostic backups omitted by the first pass.
paths += list((ROOT / 'logs/uart4_txraw_20261014/before').glob('ble_app_uart_c/Keil_6/Objects/*.hex'))
paths += [ROOT/'ble_app_uart_c/GCC/out--/ble_app_uart_c.hex']
paths += list((Path('D:/CODEX/_archive/YP001_交付同步工具_20261102/backups')).glob('*/ble_app_uart_c/Keil_6/Objects/*.hex'))
paths += list((ROOT/'Keil_v6_gcc_verified/Objects').glob('*.hex'))
paths += list((ROOT/'ble_app_uart_c/GCC/out').glob('*.hex'))
paths += [p for p in (ROOT/'logs').rglob('*.hex')
          if p.name in ('YP001_GR5526.hex','ble_app_uart_c.hex') and p.stat().st_size>1000000]
seen=set()
for path in sorted(set(p for p in paths if p.is_file())):
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest()
    if fingerprint in seen: continue
    seen.add(fingerprint)
    memory = {}
    upper = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = bytes.fromhex(line[1:])
        assert line.startswith(':') and sum(record) % 256 == 0
        count, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        assert len(record) == count + 5
        if kind == 4:
            upper = int.from_bytes(record[4:6], 'big') << 16
        elif kind == 2:
            upper = int.from_bytes(record[4:6], 'big') << 4
        elif kind == 0:
            if upper+address+count>0x277000 and upper+address<0x2ec000:
                memory.update({upper+address+i: v for i, v in enumerate(record[4:-1])})
    covered = sum(a in memory for a in occupied)
    matched = sum(memory.get(a) == v for a, v in occupied.items())
    reports.append({'hex': str(path.relative_to(ROOT)), 'covered': covered, 'matched': matched,
                    'occupied_total': len(occupied), 'fully_explained': matched == len(occupied)})
result = {'backup_sha256': hashlib.sha256(data).hexdigest(), 'erase_authorized': False,
          'comparisons': reports,
          'note': 'A match is provenance evidence only; unknown bytes remain protected.'}
out = ROOT / 'logs/ota_integrated_progress_20261023/b_provenance.json'
out.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))

"""SAM | 2026-10-23 +08:00 | One selected undeployed layout must match all release/Boot limits."""
import json,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class Consistency(unittest.TestCase):
 def test_contracts_and_protection(self):
  a=(ROOT/'tools/ota/boot/layout_candidate.json').read_bytes()
  self.assertEqual(a,(ROOT/'tools/toolkit/contracts/layout_candidate.json').read_bytes())
  p=json.loads(a);d={v['name']:v for v in p['regions']}
  self.assertFalse(p['approved'])
  self.assertEqual((d['a']['start'],d['a']['size'],d['b']['start'],d['b']['size']),(0x202000,0x6c000,0x280000,0x6c000))
  self.assertEqual((d['preserved']['start'],d['preserved']['size']),(0x26e000,0x12000))
  self.assertIs(d['preserved']['ota_writable'],False)
 def test_compiled_limits(self):
  p=ROOT/'ble_app_uart_c/Src/user/ota/yp001_ota_layout.h'
  h=p.read_text(encoding='utf-8-sig')
  expected={'YP_OTA_A':0x202000,'YP_OTA_B':0x280000,'YP_OTA_SLOT_BYTES':442368,'YP_OTA_PRESERVE_START':0x26e000,'YP_OTA_PRESERVE_BYTES':0x12000,'YP_OTA_SIGNATURE_BYTES':904}
  for k,v in expected.items():
   m=re.search(r'#define\s+'+k+r'\s+(0x[0-9a-fA-F]+|[0-9]+)[uU]?\b',h)
   self.assertIsNotNone(m,k);self.assertEqual(int(m[1],0),v,k)
  self.assertEqual(p.read_bytes(),(ROOT/'SVN交付_YP001_GR5526_20261001/ble_app_uart_c/Src/user/ota/yp001_ota_layout.h').read_bytes())
  cs=(ROOT/'tools/ota/portable/PackCore.cs').read_text(encoding='utf-8-sig')
  py=(ROOT/'tools/ota/gr_native_inspect.py').read_text(encoding='utf-8-sig')
  self.assertEqual(int(re.search(r'GrSlot=(\d+)',cs)[1]),442368)
  self.assertEqual(int(re.search(r'SLOT_BYTES = (\d+)',py)[1]),442368)
if __name__=='__main__':unittest.main()

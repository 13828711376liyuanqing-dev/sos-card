"""SAM | 2026-10-21 +08:00 | Reject candidate overlaps and image overflow before any provisioning is considered."""
import copy,json,unittest
from pathlib import Path
from check_layout import assess
PLAN=json.loads((Path(__file__).parent/'boot/layout_candidate.json').read_text())
class LayoutTests(unittest.TestCase):
 # SAM | 2026-10-23 +08:00 | Preserve the entire unknown tail instead of authorizing its erase.
 def gap_plan(self):
  return copy.deepcopy(PLAN)
 def test_preserved_gap_fits_real_compact_image(self):
  p=self.gap_plan();r=assess(p,408864,0x202000,0x202000+408864,0x2ec000,36280)
  self.assertFalse(r['install_enabled'])
  self.assertEqual(r['candidate_slot_slack_with_sdk_envelope'],32600)
 def test_preserved_gap_cannot_be_writable(self):
  p=self.gap_plan();p['regions'][2]['ota_writable']=True
  with self.assertRaises(ValueError):assess(p,408864,0x202000,0x202000+408864)
 def test_preserved_gap_cannot_hide_unknown_bytes(self):
  p=self.gap_plan();p['regions'][2]['size']-=4096
  with self.assertRaises(ValueError):assess(p,408864,0x202000,0x202000+408864)
 def test_old_large_baseline_rejected_in_smaller_slots(self):
  with self.assertRaises(ValueError):assess(self.gap_plan(),477536,0x202000,0x276960)
 def test_valid(self):
  r=assess(PLAN,408864,0x202000,0x202000+408864,0x2ec000,33768)
  self.assertFalse(r['install_enabled']);self.assertEqual(r['candidate_slot_slack_with_sdk_envelope'],32600)
 # SAM | 2026-10-23 +08:00 | Only the undeployed OTA metadata allocation moves;
 # preserve A/B and NVDS while reserving one extra sector for real Boot entry.
 def test_candidate_boot_growth_preserves_application_and_user_regions(self):
  d={r['name']:r for r in PLAN['regions']}
  self.assertEqual((d['a']['start'],d['b']['start'],d['a']['size']),(0x202000,0x280000,0x6c000))
  self.assertEqual((d['boot']['start'],d['boot']['size']),(0x2ec000,0xa000))
  self.assertEqual((d['scratch']['start'],d['coordinator1']['start']),(0x2f6000,0x2fa000))
  self.assertEqual((d['nvds']['start'],d['nvds']['size']),(0x2fe000,0x2000))
  self.assertEqual(d['unallocated']['size'],0x3000)
 def test_overflow(self):
  with self.assertRaises(ValueError):assess(PLAN,479000,0x202000,0x276f18,0x2ec000,33768)
 def test_boot_overflow(self):
  with self.assertRaises(ValueError):assess(PLAN,408864,0x202000,0x202000+408864,0x2ec000,40961)
 def test_old_boot_overlap(self):
  with self.assertRaises(ValueError):assess(PLAN,408864,0x202000,0x202000+408864,0x204000,33768)
 def test_boot_signature_margin(self):
  with self.assertRaises(ValueError):assess(PLAN,408864,0x202000,0x202000+408864,0x2ec000,40057)
 def test_overlap(self):
  p=copy.deepcopy(PLAN);p['regions'][2]['start']-=4096
  with self.assertRaises(ValueError):assess(p,408864,0x202000,0x202000+408864)
 def test_nvds_moved(self):
  p=copy.deepcopy(PLAN);p['regions'][-1]['start']-=4096
  with self.assertRaises(ValueError):assess(p,408864,0x202000,0x202000+408864)
 def test_app_entry(self):
  with self.assertRaises(ValueError):assess(PLAN,477536,0x204000,0x278960)
 def test_cannot_self_approve(self):
  p=copy.deepcopy(PLAN);p['approved']=True
  with self.assertRaises(ValueError):assess(p,408864,0x202000,0x202000+408864)
if __name__=='__main__':unittest.main()

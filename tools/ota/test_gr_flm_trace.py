"""SAM | 2026-10-24 +08:00 | Test actual FLM control flow on host; mocked hardware is never counted as device acceptance."""
import struct
import unittest
from pathlib import Path
from gr_flm_trace import FlmTrace, ROOT, BUFFER

class FlmTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out=ROOT/'firmware_releases/gr_first_deploy_20261024_NOT_FLASHABLE'
        cls.snapshot=(ROOT/'logs/ota_sequential_20261024/device_readonly/gr_current_flash_1m.bin').read_bytes()
        cls.app=(out/'GR_BASELINE_1.0.2_signed.bin').read_bytes()
        cls.boot=(out/'BOOT_NOT_FLASHABLE.bin').read_bytes()
    def test_separate_downloads_route_to_last_component(self):
        for order in [('app','boot'),('boot','app')]:
            trace=FlmTrace(self.snapshot)
            for name in order:
                payload,address=(self.app,0x202000) if name=='app' else (self.boot,0x2ec000)
                trace.download(payload,address)
                words=struct.unpack_from('<8I',trace.flash)
                self.assertEqual(words[:4],(len(payload),sum(payload)&0xffffffff,address,address))
                for start,size in [(0x6e000,0x12000),(0xfe000,0x2000)]:
                    self.assertEqual(trace.flash[start:start+size],self.snapshot[start:start+size])
    def test_sparse_merge_writes_invalid_contiguous_rom_span(self):
        trace=FlmTrace(self.snapshot)
        trace.download_segments([(0x202000,self.app),(0x2ec000,self.boot)])
        words=struct.unpack_from('<8I',trace.flash)
        self.assertEqual(words[0],len(self.app)+len(self.boot))
        self.assertNotEqual(words[1],sum(trace.flash[0x2000:0x2000+words[0]])&0xffffffff)
    def test_failed_final_verify_may_still_write_sca(self):
        trace=FlmTrace(self.snapshot)
        trace.download(self.app,0x202000)
        trace.flash[8192+len(self.app)-1]^=1
        trace.u.mem_write(0x1e54,struct.pack('<8I',0,1,0,0,0,0,0,1))
        first=len(trace.events);last_result=None
        for offset in range(0,len(self.app),1024):
            block=self.app[offset:offset+1024];trace.u.mem_write(BUFFER,block)
            last_result=trace.call(0x6e,0x202000+offset,len(block),BUFFER)
        self.assertNotEqual(last_result,0x202000+len(self.app))
        self.assertTrue(any(e['kind']=='erase' and e['start']==0x200000 for e in trace.events[first:]))
        words=struct.unpack_from('<8I',trace.flash)
        # Verify's error return is real, yet it writes a checksum of the corrupt
        # flash bytes. ROM checksum alone therefore cannot replace byte readback.
        self.assertEqual(words[1],sum(trace.flash[8192:8192+len(self.app)])&0xffffffff)
        self.assertNotEqual(words[1],sum(self.app)&0xffffffff)

if __name__=='__main__':unittest.main()

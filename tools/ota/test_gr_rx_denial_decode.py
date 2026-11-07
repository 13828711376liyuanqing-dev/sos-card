"""SAM | 2026-10-25 +08:00 | Verify old/new raw evidence is decoded without padding or losing the first-denial peer context."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import unittest

DECODER=Path(__file__).with_name('decode_gr_rx_denial.py')
OUT=Path(__file__).resolve().parents[2]/'logs/ota_peer_sync_20261025/decode_fixtures'
OUT.mkdir(parents=True,exist_ok=True)


class DecodeTests(unittest.TestCase):
    def decode(self,words):
        path=OUT/(self._testMethodName+'.bin');path.write_bytes(struct.pack('<'+'I'*len(words),*words))
        r=subprocess.run([sys.executable,str(DECODER),str(path)],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr+r.stdout)
        return json.loads(r.stdout)

    def test_legacy_fifth_evidence_remains_valid(self):
        out=self.decode([1,2,16,699140,770,0,260,15,2,429256,216576,212992,1,0xffffffff,2,1,429256])
        self.assertEqual(out['causes'],['peer'])
        self.assertEqual(out['durable'],212992)

    def test_extended_snapshot_identifies_ip_downgrade_and_previous_mqtt(self):
        out=self.decode([1,2,16,200,0,0,0,15,2,429256,216576,212992,1,0xffffffff,2,1,429256]+
                        [1,3,200,0,200,19,1,4,0,100,0,0])
        self.assertEqual(out['peer']['network'],'ip')
        self.assertEqual(out['peer']['transport_ready'],True)
        self.assertEqual(out['peer']['source'],'network_ip')
        self.assertEqual(out['peer']['previous_network'],'mqtt')

    def test_timeout_survives_partial_hello_resync(self):
        out=self.decode([1,1,16,20302,0,0,0,15,2,429256,216576,212992,1,0xffffffff,2,1,429256]+
                        [1,0,20302,0,20302,1,0,0,0,20301,20301,4])
        self.assertEqual(out['peer']['source'],'hello')
        self.assertEqual(out['peer']['last_loss_source'],'rx_timeout')
        self.assertEqual(out['peer']['last_loss_ms'],20301)

    def test_short_or_mixed_reads_are_rejected(self):
        for n in (0,67,69,115,117):
            path=OUT/('bad_'+str(n)+'.bin');path.write_bytes(bytes(n))
            r=subprocess.run([sys.executable,str(DECODER),str(path)],capture_output=True)
            self.assertNotEqual(r.returncode,0)


if __name__=='__main__':
    unittest.main()

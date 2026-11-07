"""SAM | 2026-10-24 +08:00 | Gate Boot-only readback independently of application verification and activation."""
import struct
import unittest
from gr_deployment_check import boot_readback

class BootReadbackTests(unittest.TestCase):
    def setUp(self):
        self.app=bytes(range(256))*4
        boot=bytearray(bytes(range(256))*19)
        struct.pack_into('<6I',boot,0x200,0x47525858,1,0x5526,0x2ec000,0x2ec000,0)
        boot[0x218:0x21c]=bytes([1,1,0,0])
        self.boot=bytes(boot)
        self.before=bytearray(b'\xff'*0x100000)
        self.before[:32]=struct.pack('<8I',len(self.app),sum(self.app),0x202000,0x202000,11,836,0,0)
        self.before[8192:8192+len(self.app)]=self.app
        self.before[0x6e000]=17;self.before[0xfe000]=23
        self.after=bytearray(self.before)
        self.after[:32]=struct.pack('<8I',len(self.boot),sum(self.boot),0x2ec000,0x2ec000,11,836,0,0)
        self.after[0xec000:0xec000+len(self.boot)]=self.boot
    def test_exact_boot_does_not_authorize_activation(self):
        report=boot_readback(bytes(self.before),bytes(self.after),self.app,self.boot)
        self.assertTrue(report['boot_bytes_verified'])
        self.assertTrue(report['user_regions_unchanged'])
        self.assertFalse(report['boot_activation_authorized'])
    def test_application_and_every_unplanned_region_protected(self):
        for at in [8192,0x6e000,0x80000,0xf6000,0xf7000,0xf9000,0xfb000,0xfe000]:
            with self.subTest(at=hex(at)):
                after=bytearray(self.after);after[at]^=1
                with self.assertRaises(ValueError):boot_readback(bytes(self.before),bytes(after),self.app,self.boot)
    def test_misroute_length_checksum_config_and_sca_extra_rejected(self):
        for at in [0,4,8,12,16,20,4096]:
            after=bytearray(self.after);after[at]^=1
            with self.assertRaises(ValueError):boot_readback(bytes(self.before),bytes(after),self.app,self.boot)
    def test_unknown_boot_or_sca_data_is_not_permission_to_erase(self):
        for at in [32,4096,0xec000,0xf5fff]:
            before=bytearray(self.before);before[at]=1
            with self.assertRaises(ValueError):boot_readback(bytes(before),bytes(self.after),self.app,self.boot)
    def test_boot_corruption_tail_size_and_snapshot_rejected(self):
        for at in [0xec000,0xec000+len(self.boot)]:
            after=bytearray(self.after);after[at]^=1
            with self.assertRaises(ValueError):boot_readback(bytes(self.before),bytes(after),self.app,self.boot)
        for boot in [b'',b'x'*0xa001]:
            with self.assertRaises(ValueError):boot_readback(bytes(self.before),bytes(self.after),self.app,boot)
        with self.assertRaises(ValueError):boot_readback(bytes(self.before[:-1]),bytes(self.after),self.app,self.boot)
    def test_preexisting_app_mismatch_rejected(self):
        before=bytearray(self.before);before[8192]^=1
        with self.assertRaises(ValueError):boot_readback(bytes(before),bytes(self.after),self.app,self.boot)
    def test_only_compiled_boot_check_and_delay_bits_may_change(self):
        boot=bytearray(self.boot);boot[0x219]=0
        after=bytearray(self.after);after[0xec000:0xec000+len(boot)]=boot
        struct.pack_into('<I',after,4,sum(boot))
        struct.pack_into('<I',after,20,0x144)
        self.assertTrue(boot_readback(bytes(self.before),bytes(after),self.app,bytes(boot))['boot_bytes_verified'])
        for offset in [20,24,28]:
            changed=bytearray(after);changed[offset]^=1
            with self.assertRaises(ValueError):boot_readback(bytes(self.before),bytes(changed),self.app,bytes(boot))

if __name__=='__main__':unittest.main()

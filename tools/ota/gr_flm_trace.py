"""SAM | 2026-10-24 +08:00 | Execute pinned FLM code on a host with mocked flash callbacks; no device access or policy approvals."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DEPS=ROOT/'logs/ota_flm_host_20261024/deps'
sys.path.insert(0,str(DEPS))
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R9, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

PIN='e2fe1d5e72df1531373700bcfacad06ea7aa9c533357ffafcdf25fe1f45f3ae0'
BASE=0x200000
BUFFER=0x10000000
STOP=0x1ff00

class FlmTrace:
    def __init__(self,snapshot):
        data=Path('C:/Keil_v5/ARM/Flash/GR5xxx_16MB_Flash.FLM').read_bytes()
        if hashlib.sha256(data).hexdigest()!=PIN or len(snapshot)!=0x100000:
            raise ValueError('FLM_OR_SNAPSHOT_IDENTITY')
        self.flash=bytearray(snapshot)
        self.events=[]
        self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
        self.u.mem_map(0,0x20000)
        self.u.mem_map(BUFFER,0x100000)
        self.u.mem_map(0x20000000,0x20000)
        self.u.mem_map(0x30010000,0x1000)
        phoff=struct.unpack_from('<I',data,28)[0]
        phsize,phcount=struct.unpack_from('<HH',data,42)
        for i in range(phcount):
            kind,offset,address,_,filesize,_,_,_=struct.unpack_from('<8I',data,phoff+i*phsize)
            if kind==1:self.u.mem_write(address,data[offset:offset+filesize])
        # Match the non-CAIRO 32-byte SCA observed on the GR5526; only hardware
        # callback table/geometry is supplied by the host, not Verify/ProgramPage.
        self.u.mem_write(0x1e74,struct.pack('<8I',0xb88,0x10001,0x10011,0x10021,0x10031,0x10041,0x10051,0x1485))
        self.u.mem_write(0x1e94,struct.pack('<10I',BASE,0x100000,*([0xffffffff,0]*4)))
        self.u.reg_write(UC_ARM_REG_R9,0x1e50)
        self.u.hook_add(UC_HOOK_CODE,self.callback,begin=0x10000,end=0x10070)
        self.u.hook_add(UC_HOOK_CODE,self.callback,begin=0x398,end=0x398)
        self.u.hook_add(UC_HOOK_CODE,self.callback,begin=STOP,end=STOP)

    def callback(self,u,address,size,unused):
        if address==STOP:
            u.emu_stop();return
        a=u.reg_read(UC_ARM_REG_R0);b=u.reg_read(UC_ARM_REG_R1);n=u.reg_read(UC_ARM_REG_R2)
        if address==0x398:
            result=0xb88
        elif address==0x10030:
            if a%4096 or a+4096>len(self.flash):raise ValueError('ERASE_RANGE')
            self.flash[a:a+4096]=b'\xff'*4096
            self.events.append(dict(kind='erase',start=BASE+a,bytes=4096));result=0
        elif address==0x10040:
            if not n or a+n>len(self.flash):raise ValueError('WRITE_RANGE')
            payload=bytes(u.mem_read(b,n))
            if any((old&new)!=new for old,new in zip(self.flash[a:a+n],payload)):
                raise ValueError('FLASH_NEEDS_ERASE')
            self.flash[a:a+n]=payload
            self.events.append(dict(kind='write',start=BASE+a,bytes=n));result=0
        elif address==0x10050:
            if a+n>len(self.flash):raise ValueError('READ_RANGE:'+hex(a)+'/'+hex(n))
            u.mem_write(b,bytes(self.flash[a:a+n]));result=0
        elif address==0x10020:
            raise ValueError('FULL_CHIP_ERASE_FORBIDDEN')
        elif address in (0x10000,0x10010):
            result=0  # hardware init/uninit, no flash effect
        else:
            raise ValueError('UNEXPECTED_CALLBACK:'+hex(address))
        u.reg_write(UC_ARM_REG_R0,result)
        u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))

    def call(self,entry,a=0,b=0,c=0):
        u=self.u
        for register,value in [(UC_ARM_REG_R0,a),(UC_ARM_REG_R1,b),(UC_ARM_REG_R2,c),
                (UC_ARM_REG_SP,0x2001fff0),(UC_ARM_REG_LR,STOP|1)]:
            u.reg_write(register,value)
        u.emu_start(entry|1,STOP,count=12000000)
        if u.reg_read(UC_ARM_REG_PC)!=STOP:raise ValueError('FLM_EXECUTION_LIMIT')
        return u.reg_read(UC_ARM_REG_R0)

    def download(self,payload,start):
        return self.download_segments([(start,payload)])

    def download_segments(self,segments):
        first=len(self.events)
        # Keil Init(program) clears the ProgramPage byte counter. Reset the
        # documented per-download state as a fresh algorithm instance would.
        self.u.mem_write(0x1e54,struct.pack('<8I',0,1,0,0,0,0,0,1))
        for start,payload in segments:
            for address in range(start,start+len(payload),4096):
                if self.call(0x40,address):raise ValueError('ERASE_FAILED')
        for start,payload in segments:
            for offset in range(0,len(payload),1024):
                block=payload[offset:offset+1024];self.u.mem_write(BUFFER,block)
                if self.call(0x2a6,start+offset,len(block),BUFFER):raise ValueError('PROGRAM_FAILED')
        for start,payload in segments:
            for offset in range(0,len(payload),1024):
                block=payload[offset:offset+1024];self.u.mem_write(BUFFER,block)
                if self.call(0x6e,start+offset,len(block),BUFFER)!=start+offset+len(block):
                    raise ValueError('VERIFY_FAILED')
        return self.events[first:]

def main():
    out=ROOT/'firmware_releases/gr_first_deploy_20261024_NOT_FLASHABLE'
    snapshot=(ROOT/'logs/ota_sequential_20261024/device_readonly/gr_current_flash_1m.bin').read_bytes()
    app=(out/'GR_BASELINE_1.0.2_signed.bin').read_bytes()
    boot=(out/'BOOT_NOT_FLASHABLE.bin').read_bytes()
    results=[]
    for order in [('app','boot'),('boot','app')]:
        trace=FlmTrace(snapshot);stages=[]
        for component in order:
            payload,start=(app,0x202000) if component=='app' else (boot,0x2ec000)
            events=trace.download(payload,start)
            for a,n in [(0x26e000,0x12000),(0x2fe000,0x2000)]:
                if trace.flash[a-BASE:a-BASE+n]!=snapshot[a-BASE:a-BASE+n]:raise ValueError('PROTECTED_CHANGED')
            stages.append(dict(component=component,sca_words=list(struct.unpack_from('<8I',trace.flash)),
                sca_events=[e for e in events if e['start']<0x202000],
                operation_count=len(events),protected_unchanged=True))
        results.append(dict(order=list(order),stages=stages))
    merged=FlmTrace(snapshot)
    merged.download_segments([(0x202000,app),(0x2ec000,boot)])
    merged_words=list(struct.unpack_from('<8I',merged.flash))
    if merged_words[0]!=len(app)+len(boot) or merged_words[2]!=0x202000:
        raise ValueError('UNEXPECTED_MERGED_TRACE')
    # Sparse merged image is NOT a single contiguous ROM-checkable application.
    merged_checksum=sum(merged.flash[0x2000:0x2000+merged_words[0]])&0xffffffff
    merged_invalid=dict(sca_words=merged_words,rom_span_sum=merged_checksum,
        checksum_matches=merged_checksum==merged_words[1],flash_ready=False)
    if merged_invalid['checksum_matches']:raise ValueError('MERGED_HAZARD_NOT_REPRODUCED')
    report=dict(schema='YP001_PINNED_FLM_HOST_TRACE_V1',flm_sha256=PIN,
        device_access=False,hardware_callbacks_mocked=True,hardware_acceptance=False,
        flash_ready=False,results=results,merged_sparse_image=merged_invalid,
        mailbox_code='Unmodified PARAMETER_ACC_BALI_B0; mapped host mailbox memory',
        scope='Generic non-CAIRO APP_INFO path; hardware identification/init/SPI are mocked')
    (out/'flm_host_trace.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()

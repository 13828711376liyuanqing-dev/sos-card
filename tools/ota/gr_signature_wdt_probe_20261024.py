# SAM | 2026-10-24 +08:00 | Bind existing probe to rebuilt WDT baseline and disassembled return addresses.
"""SAM | 2026-10-24 +08:00 | Invoke only the deployed baseline's existing read-only verifier, with RAM/register restoration. Never downloads or erases Flash."""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from gr_gdb_probe import Rsp,probe_plan

ROOT=Path(__file__).resolve().parents[2]
FUNCTION=0x233be1
# SAM | 2026-10-24 +08:00 | One-shot return checkpoints identify the first
# failing prerequisite without changing the signed firmware or its guards.
CHECKPOINTS={0x233c3a:'trailer_read',0x22b8f6:'security_status',
             0x22b904:'watchdog_service',0x233c66:'image_auth',
             0x1fc3c:'hal_watchdog_entry',0x1fd00:'hal_watchdog_error'}

def run(execute):
    out=ROOT/'logs/ota_wdt_fix_20261024'
    stage=ROOT/'firmware_releases/baseline_wdt_fix_20261024/STAGE1_WDT'
    signed=(stage/'SIGNED_INPUT.bin').read_bytes()
    axf=(ROOT/'firmware_releases/baseline_wdt_fix_20261024/Objects/YP001_GR5526.axf').read_bytes()
    if hashlib.sha256(axf).hexdigest()!='ed660efee8a1776f19dbb9fe61c5eca68906961872ed9359c22c8ff9f78b7653':
        raise ValueError('SYMBOL_SOURCE_CHANGED')
    evidence=json.loads((stage/'stage1_device_readback.json').read_text())
    if (not evidence['baseline_bytes_verified'] or not evidence['user_regions_unchanged'] or
            hashlib.sha256(signed).hexdigest()!=evidence['baseline_sha256']):
        raise ValueError('DEPLOYED_BASELINE_NOT_BOUND')
    log=open(out/'signature_probe_server.log','wb')
    server=subprocess.Popen(['C:/Program Files/SEGGER/JLink/JLinkGDBServerCL.exe',
        '-device','Cortex-M4','-if','SWD','-speed','1000','-port','13331',
        '-swoport','13332','-telnetport','13333','-localhostonly','-noreset','-noir',
        '-nohalt','-singlerun','-nogui'],stdout=log,stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW)
    c=None;saved=None;backup=None;plan=None;mutated=False;breakpoint=False;halted=False
    checkpoints=set()
    result=dict(schema='YP001_BASELINE_HARDWARE_SIGNATURE_PROBE_V1',flash_written=False,
        executed=False,registers_restored=False,ram_restored=False,device_signature_verified=False)
    try:
        for _ in range(35):
            if server.poll() is not None:raise ValueError('SERVER_EXITED')
            try:c=Rsp(13331);break
            except OSError:time.sleep(.15)
        if c is None:raise ValueError('SERVER_NOT_READY')
        c.command('qSupported:qXfer:features:read+')
        xml=c.command('qXfer:features:read:target.xml:0,2000')
        if not xml.startswith(b'l'):raise ValueError('REGISTER_SCHEMA_INCOMPLETE')
        regs={x.attrib['name']:int(x.attrib['regnum']) for x in ET.fromstring(xml[1:]).iter('reg')}
        def readreg(name):
            raw=c.command('p%x'%regs[name])
            if not re.fullmatch(b'[0-9a-fA-F]{8}',raw):raise ValueError('REGISTER_READ:'+name)
            return int.from_bytes(bytes.fromhex(raw.decode()),'little')
        def write_reg(name,value):
            raw=struct.pack('<I',value).hex()
            if c.command('P%x=%s'%(regs[name],raw))!=b'OK':raise ValueError('REGISTER_WRITE:'+name)
        def write_ram(address,data):
            if not plan or address<plan['scratch_start'] or address+len(data)>plan['scratch_start']+plan['scratch_bytes']:
                raise ValueError('RAM_WRITE_OUTSIDE_BACKUP')
            for offset in range(0,len(data),512):
                block=data[offset:offset+512]
                if c.command('M%x,%x:%s'%(address+offset,len(block),block.hex()))!=b'OK':raise ValueError('RAM_WRITE')
        c.interrupt();halted=True
        # SAM | 2026-10-24 +08:00 | Wait at pinned application service when halted in ROM idle; retain original context guards.
        if readreg('pc')<0x100000:
            at=0x230744
            if c.command('Z1,%x,2'%at)!=b'OK':raise ValueError('APP_WAIT_BREAKPOINT')
            try:c.command('c')
            finally:c.command('z1,%x,2'%at)
        values={name:readreg(name) for name in ['pc','sp','xpsr','primask','control']}
        result['observed_context']={name:hex(value) for name,value in values.items()}
        plan=probe_plan(values['pc'],values['sp'],values['xpsr'])
        if not execute:return result
        if values['pc']<0x202000:
            shoff=struct.unpack_from('<I',axf,32)[0]
            shsize,shcount=struct.unpack_from('<HH',axf,46)
            matched=False
            for i in range(shcount):
                _,kind,flags,address,offset,size=struct.unpack_from('<6I',axf,shoff+i*shsize)
                if kind==1 and flags&4 and address<=values['pc'] and values['pc']+8<=address+size:
                    pos=offset+values['pc']-address
                    matched=c.memory(values['pc'],8)==axf[pos:pos+8]
                    break
            if not matched:raise ValueError('RAM_CODE_DOES_NOT_MATCH_PINNED_AXF')
        payload=signed[:-904]
        off=(FUNCTION&~1)-0x202000
        if c.memory(FUNCTION&~1,64)!=payload[off:off+64] or c.memory(0x202000+len(payload),904)!=signed[-904:]:
            raise ValueError('TARGET_FUNCTION_OR_SIGNATURE_CHANGED')
        saved=c.command('g')
        if not re.fullmatch(b'[0-9a-fA-F]+',saved):raise ValueError('REGISTERS_NOT_RESTORABLE')
        if c.command(b'G'+saved)!=b'OK':raise ValueError('REGISTERS_ROUNDTRIP_REJECTED')
        backup=c.memory(plan['scratch_start'],plan['scratch_bytes'])
        if readreg('pc')!=values['pc']:raise ValueError('TARGET_RESET_DURING_BACKUP')
        if c.command('Z1,%x,2'%plan['return_pc'])!=b'OK':raise ValueError('RETURN_BREAKPOINT')
        for at in CHECKPOINTS:
            if c.command('Z1,%x,2'%at)!=b'OK':raise ValueError('CHECKPOINT_BREAKPOINT')
            checkpoints.add(at)
        breakpoint=True;mutated=True
        write_reg('primask',1);write_reg('basepri',0)
        write_ram(plan['output'],bytes(40))
        write_reg('sp',plan['call_sp']);write_reg('r0',1000002);write_reg('r1',plan['output'])
        write_reg('lr',plan['return_pc']|1);write_reg('xpsr',0x01000000);write_reg('pc',FUNCTION&~1)
        result['executed']=True
        started=time.monotonic();result['checkpoints']=[]
        for _ in range(len(CHECKPOINTS)+1):
            c.command('c');halted=True
            at=readreg('pc')
            if at==plan['return_pc']:break
            if at not in checkpoints:raise ValueError('UNEXPECTED_DEBUG_STOP')
            # SAM | 2026-10-24 +08:00 | Capture actual HAL rejection inputs; never
            # change watchdog state or accept an error as successful refresh.
            point=dict(stage=CHECKPOINTS[at],return_code=readreg('r0'))
            if at in (0x1fc3c,0x1fd00):
                point['handle_words']=list(struct.unpack('<4I',c.memory(0x20021cc4,16)))
                point['wdt_status']=int.from_bytes(c.memory(0x4000a738,4),'little')
                point['r4']=readreg('r4')
            result['checkpoints'].append(point)
            c.command('z1,%x,2'%at);checkpoints.remove(at)
        result['call_elapsed_seconds']=round(time.monotonic()-started,3)
        if readreg('pc')!=plan['return_pc'] or readreg('xpsr')&511:raise ValueError('FUNCTION_DID_NOT_RETURN')
        returned=readreg('r0');image=c.memory(plan['output'],40)
        result['return_code']=returned
        size,version=struct.unpack_from('<II',image)
        result.update(image_bytes=size,version_number=version,payload_sha256=image[8:].hex())
        result['device_signature_verified']=(returned==0 and size==len(payload) and version==1000002
            and image[8:]==hashlib.sha256(payload).digest())
        return result
    finally:
        try:
            if c and mutated:
                try:c.interrupt()
                except Exception:pass
                write_ram(plan['scratch_start'],backup)
                result['ram_restored']=c.memory(plan['scratch_start'],len(backup))==backup
                if c.command(b'G'+saved)!=b'OK':raise ValueError('REGISTER_RESTORE_FAILED')
                result['registers_restored']=c.command('g')==saved
            if c and breakpoint:c.command('z1,%x,2'%plan['return_pc'])
            if c:
                for at in checkpoints:c.command('z1,%x,2'%at)
            if c and mutated and not result['registers_restored']:
                # Do not leave uncertain debug context running. The deployed
                # baseline was independently read back and is the recovery image.
                c.command('qRcmd,'+b'reset'.hex())
                result['recovery_reset_requested']=True
            if c:c.command('D')
        finally:
            if c:c.close()
            try:server.wait(timeout=3)
            except subprocess.TimeoutExpired:server.terminate();server.wait(timeout=3)
            log.close()
            (stage/('signature_probe_history_%d.json'%time.time_ns())).write_text(json.dumps(result,indent=2),encoding='utf-8')
            (stage/'signature_device_probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute-readonly-probe',action='store_true')
    args=p.parse_args();print(json.dumps(run(args.execute_readonly_probe),indent=2))

if __name__=='__main__':main()

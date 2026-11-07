"""SAM | 2026-10-27 +08:00 | Decode the 64-byte sequence-last installation error snapshot; never touches a device."""
from pathlib import Path
import argparse,json,struct

STAGES={1:'durable_owner',2:'boot_open',3:'validation_receipt',4:'boot_generation',5:'image_descriptors',
        6:'final_commit_gates',7:'boot_activate_auth_or_journal',10:'validation_prerequisite_or_boot_open',
        11:'running_auth_or_source_version',12:'candidate_native_validation',13:'validation_owner_or_progress',
        14:'validation_called_with_flash_authority',15:'validation_boot_open_or_generation',16:'validation_internal_stage'}
GATES=('unknown','unstable','power','battery','alarm','call','activity','peer')

def decode(data):
    if len(data)!=64:raise ValueError('EXPECTED_EXACT_64_BYTES')
    w=struct.unpack('<16I',data)
    if w[0]!=1:return {'published':False,'publication_word':w[0]}
    stage=w[2];boot=w[5] if w[5]!=0xffffffff else None
    return dict(published=True,failure_count=w[1],stage=stage,stage_name=STAGES.get(stage,'unknown_stage'),
        epoch=w[3],owner_phase=w[4],boot_state=boot,boot_generation=w[6] if boot is not None else None,
        gate_mask=w[7],gate_reasons=[name for bit,name in enumerate(GATES) if w[7]&(1<<bit)] if stage==6 else None,
        unknown_gate_bits=w[7]&~255 if stage==6 else None,
        observed_clock_ms=w[8],battery_age_ms=w[9],keys_age_ms=w[10],motion_age_ms=w[11],seen_bits=w[12],
        old_version=w[13],new_version=w[14],foreground_clock_ms=w[15],
        scope='First internal branch snapshot; served clocks are not physical crypto/Flash durations; stage 7 does not distinguish its authenticator and journal subcalls')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('snapshot',type=Path);args=p.parse_args()
    print(json.dumps(decode(args.snapshot.read_bytes()),indent=2))

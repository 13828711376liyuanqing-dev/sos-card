"""SAM | 2026-10-27 +08:00 | Prevent misleading stage/mask interpretation of future first-error captures."""
import struct
from decode_install_error import decode

assert decode(bytes(64))['published'] is False
w=[1,3,6,4,3,1,2,64|128,10000,100,10,500,15,1000002,1005000,9990]
d=decode(struct.pack('<16I',*w))
assert d['stage_name']=='final_commit_gates' and d['gate_reasons']==['activity','peer'] and d['motion_age_ms']==500
w[2]=12;w[5]=0xffffffff;w[7]=0
d=decode(struct.pack('<16I',*w))
assert d['stage_name']=='candidate_native_validation' and d['boot_state'] is None and d['gate_reasons'] is None
try:decode(bytes(63))
except ValueError as e:assert str(e)=='EXPECTED_EXACT_64_BYTES'
else:raise AssertionError('SHORT_SNAPSHOT_ACCEPTED')
print('PASS install first-error decoder: publication, commit mask, validation stage, absent Boot and short input')

"""SAM | 2026-10-21 +08:00 | Read-only candidate layout/HEX/Map preflight; never authorizes installation or emits firmware."""
from pathlib import Path
import argparse,json,re,hashlib
# SAM | 2026-10-23 +08:00 | Actual SDK104 trailer size is compiled/offset-checked
# by test_gr_flash.py; do not keep describing its known 904 bytes as an estimate.
SIGNATURE_BYTES=904

def assess(p,app_bytes,app_start,app_end,boot_base=None,boot_size=None):
 def require(ok,msg):
  if not ok:raise ValueError(msg)
 require(p.get('approved') is False and p.get('status')=='candidate_do_not_flash','candidate cannot self-approve')
 require((p['base'],p['capacity'],p['sector'])==(0x200000,0x100000,4096),'unsupported geometry')
 names=['sca','a','b','boot','scratch','journal0','journal1','coordinator0','coordinator1','unallocated','nvds']
 # SAM | 2026-10-23 +08:00 | Alternative candidate reserves unknown old bytes;
 # geometry approval remains false and does not update firmware/packager pins.
 if any(v.get('name')=='preserved' for v in p['regions']):names.insert(2,'preserved')
 regions=p['regions'];require([v['name']for v in regions]==names,'missing, duplicate or unordered regions')
 cursor=p['base']
 for v in regions:
  a,n=v['start'],v['size'];require(type(a)is int and type(n)is int and n>0 and a%4096==0 and n%4096==0,'invalid sector geometry')
  require(a==cursor and n<=p['base']+p['capacity']-a,'gap, overlap or overflow');cursor=a+n
 require(cursor==0x300000,'incomplete layout')
 d={v['name']:v for v in regions};a=d['a'];b=d['b'];boot=d['boot']
 if 'preserved' in d:
  gap=d['preserved']
  require((gap['start'],gap['size'])==(0x26e000,0x12000) and gap.get('ota_writable') is False,'unknown tail protection changed')
  require((a['size'],b['start'],b['size'])==(0x6c000,0x280000,0x6c000),'preserved-gap slot geometry changed')
 require((d['sca']['start'],d['sca']['size'])==(0x200000,8192),'SCA changed')
 require((d['nvds']['start'],d['nvds']['size'])==(0x2fe000,8192),'NVDS changed')
 require(a['start']==0x202000 and a['size']==b['size'],'existing A entry or slot mismatch')
 require(all(type(x)is int for x in [app_bytes,app_start,app_end]) and app_bytes>0,'invalid image counters')
 require(app_start==a['start'] and app_end>app_start and app_bytes<=app_end-app_start,'unexpected app geometry')
 span=app_end-app_start
 require(span+SIGNATURE_BYTES<=a['size'],'app plus signature envelope exceeds slot')
 if boot_base is not None or boot_size is not None:
  require(type(boot_base)is int and type(boot_size)is int and boot_size>0,'invalid Boot geometry')
  # SAM | 2026-10-21 +08:00 | Budget signature/metadata for Boot too; raw link success alone cannot approve its storage envelope.
  require(boot_base==boot['start'] and boot_size+SIGNATURE_BYTES<=boot['size'],'Boot plus signature envelope outside candidate protected region')
 return {'install_enabled':False,'layout_approved':False,'status':'CANDIDATE_GEOMETRY_OK','app_bytes':app_bytes,'app_span':span,'slot_bytes':a['size'],'candidate_slot_slack_with_sdk_envelope':a['size']-span-SIGNATURE_BYTES,'boot_region_bytes':boot['size'],'unallocated_bytes':d['unallocated']['size'],'note':'904-byte signature budget is not installation acceptance; no provisioning or Flash IO'}

def read_hex(p):
 base=0;data={};ended=False
 for line in p.read_text().splitlines():
  if not line.strip():continue
  if ended:raise ValueError('records after EOF')
  if not line.startswith(':'):raise ValueError('invalid HEX record')
  b=bytes.fromhex(line[1:]);n=b[0]
  if len(b)!=n+5 or sum(b)%256:raise ValueError('HEX checksum/length')
  off=int.from_bytes(b[1:3],'big');kind=b[3];v=b[4:4+n]
  if kind==4:
   if n!=2:raise ValueError('bad linear address')
   base=int.from_bytes(v,'big')<<16
  elif kind==2:
   if n!=2:raise ValueError('bad segment address')
   base=int.from_bytes(v,'big')<<4
  elif kind==0:
   for i,x in enumerate(v):
    a=base+off+i
    if a in data and data[a]!=x:raise ValueError('conflicting HEX bytes')
    data[a]=x
  elif kind==1:
   if n:raise ValueError('invalid EOF')
   ended=True
  elif kind not in (3,5):raise ValueError('unknown HEX record')
 if not ended or not data:raise ValueError('empty/incomplete HEX')
 return len(data),min(data),max(data)+1

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--app-hex',type=Path,required=True);parser.add_argument('--boot-map',type=Path)
 parser.add_argument('--layout',type=Path,default=Path(__file__).parent/'boot/layout_candidate.json');args=parser.parse_args()
 plan=json.loads(args.layout.read_text());bb=bs=None
 if args.boot_map:
  text=args.boot_map.read_text(errors='replace');m=re.search(r'Load Region LR_FLASH \(Base: 0x([0-9a-f]+), Size: 0x([0-9a-f]+)',text,re.I)
  if not m:raise ValueError('no Boot LR_FLASH in Map')
  bb,bs=(int(x,16)for x in m.groups())
 result=assess(plan,*read_hex(args.app_hex),bb,bs);result['app_hex_sha256']=hashlib.sha256(args.app_hex.read_bytes()).hexdigest()
 print(json.dumps(result,indent=2))

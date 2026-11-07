"""SAM | 2026-10-27 21:30 +08:00 | Decode the saved R6 evidence window without exporting business payloads."""
from pathlib import Path
import json,re,sys,zlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
import numpy as np

def run(folder,ch,start_seconds=185,end_seconds=280):
 unit=1048576;rate=10000000;period=rate/460800
 samples=int((folder/str(ch)/'channel.ini').read_text().splitlines()[2]);mapping={}
 for row in (folder/str(ch)/'files.ini').read_text().splitlines():
  plane,index,name=row.split(',');mapping[int(plane)*64+int(index)]=folder/name
 def block(i):
  p=mapping.get(i)
  if p is None:return bytes([255])*unit
  raw=p.read_bytes();assert len(raw)==unit;return raw
 startblock=int(start_seconds*rate//(unit*8));endblock=min(int(end_seconds*rate//(unit*8))+1,(samples+unit*8-1)//(unit*8))
 prev=255;cursor=startblock*unit*8;data=bytearray();times=[];bad=0
 for i in range(startblock,endblock):
  current=block(i);raw=np.frombuffer(current+block(i+1)[:64],dtype=np.uint8);old=raw<<1;old[1:]|=raw[:-1]>>7;old[0]|=prev>>7;fall=(~raw)&old;start=i*unit*8
  def bit(n):return (int(raw[(n-start)>>3])>>((n-start)&7))&1
  for j in np.flatnonzero(fall[:unit]):
   mask=int(fall[j])
   for k in range(8):
    if not mask&(1<<k):continue
    edge=start+int(j)*8+k
    if edge<cursor or edge+10*period>=samples or bit(round(edge+period*.5))!=0:continue
    value=sum(bit(round(edge+(1.5+x)*period))<<x for x in range(8))
    if bit(round(edge+period*9.5))!=1:bad+=1;cursor=edge+round(period);continue
    data.append(value);times.append(edge/rate);cursor=edge+round(period*9.6)
  prev=current[-1]
 events=[]
 for match in re.finditer(rb'OTA_CTL=([^\r\n]{1,1500})|OTA_HANDOFF_RESUME[^\r\n]{0,120}|INSTALL_RECOVERY_QUERY_FAILED|OTA_GR=([^\r\n]{1,1500})',bytes(data)):
  raw=match.group(0);event={'seconds':round(times[match.start()],3),'type':'unknown'}
  if raw.startswith((b'OTA_CTL=',b'OTA_GR=')):
   event['type']='OTA_CTL' if raw.startswith(b'OTA_CTL=') else 'OTA_GR'
   try:
    obj=json.loads(raw.split(b'=',1)[1]);event.update({k:obj[k] for k in ('op','phase','reason','epoch') if k in obj})
   except Exception:event['parse']='invalid'
  elif raw.startswith(b'OTA_HANDOFF_RESUME'):event['type']='HANDOFF_COMMAND'
  else:event['type']='QUERY_FAILED_RESULT'
  events.append(event)
 frames=[];payload=bytes(data);pos=0
 while True:
  pos=payload.find(b'OTA2',pos)
  if pos<0 or pos+24>len(payload):break
  size=int.from_bytes(payload[pos+20:pos+22],'little');end=pos+28+size
  if size<=512 and end<=len(payload):
   b=payload[pos:end];frames.append({'seconds':round(times[pos],3),'type':b[5],
    'session':int.from_bytes(b[8:12],'little'),'sequence':int.from_bytes(b[12:16],'little'),
    'offset':int.from_bytes(b[16:20],'little'),'size':len(b),
    'crc_ok':zlib.crc32(b[:-4])==int.from_bytes(b[-4:],'little')})
  pos+=4
 bus=[]
 for match in re.finditer(rb'BUS_CMD=([^\r\n]{1,1500})',payload):
  try:
   obj=json.loads(match.group(1));op=obj.get('op')
   if op=='hello':bus.append({'seconds':round(times[match.start()],3),'op':'hello'})
  except Exception:pass
 return {'channel':ch,'range_seconds':[start_seconds,end_seconds],'bytes_decoded':len(data),'framing_rejections':bad,'events':events},frames,bus

if __name__=='__main__':
 p=Path(sys.argv[1]);start=int(sys.argv[3]) if len(sys.argv)>3 else 185;end=int(sys.argv[4]) if len(sys.argv)>4 else 280
 decoded=[run(p,c,start,end) for c in (0,1)];actual=[x[0] for x in decoded]
 if (start,end)==(185,280):
  expected=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8-sig'));assert actual==expected,'RECOVERED_CAPTURE_DOES_NOT_MATCH_PRIOR_DECODE'
 result={'matching_prior_summary':True if (start,end)==(185,280) else None,'channels':actual,'frames':{str(c):decoded[c][1] for c in (0,1)},'hello':{str(c):decoded[c][2] for c in (0,1)}}
 (ROOT/f'logs/r6_install_only_once_20261027/recovered_window_{start}_{end}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False))

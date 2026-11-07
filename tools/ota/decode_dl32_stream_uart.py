"""SAM | 2026-10-26 +08:00 | Decode sparse DL32 bit-packed cache in 1MiB blocks, keeping RAM bounded; never touch live cache or device state."""
from pathlib import Path
import json,sys,zlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
import numpy as np

def decode(folder,ch,out):
    meta=(folder/str(ch)/'channel.ini').read_text().splitlines();samples=int(meta[2]);unit=1048576
    mapping={}
    for row in (folder/str(ch)/'files.ini').read_text().splitlines():
        plane,index,name=row.split(',');mapping[int(plane)*64+int(index)]=folder/name
    def block(i):
        p=mapping.get(i)
        if p is None:return bytes([255])*unit
        data=p.read_bytes();assert len(data)==unit,(str(p),len(data));return data
    data=bytearray();times=[];bad=0;cursor=0;period=10000000/460800;previous_byte=255
    for i in range((samples+unit*8-1)//(unit*8)):
        current=block(i);raw=np.frombuffer(current+block(i+1)[:64],dtype=np.uint8)
        previous=raw<<1;previous[1:]|=raw[:-1]>>7;previous[0]|=previous_byte>>7
        falling=(~raw)&previous;start=i*unit*8
        bit=lambda n:(int(raw[(n-start)>>3])>>((n-start)&7))&1
        for byte in np.flatnonzero(falling[:unit]):
            mask=int(falling[byte])
            for k in range(8):
                if not mask&(1<<k):continue
                edge=start+int(byte)*8+k
                if edge<cursor or edge+10*period>=samples:continue
                if bit(round(edge+period*.5))!=0:continue
                value=sum(bit(round(edge+(1.5+j)*period))<<j for j in range(8))
                if bit(round(edge+period*9.5))!=1:bad+=1;cursor=edge+round(period);continue
                data.append(value);times.append(edge/10000000);cursor=edge+round(period*9.6)
        previous_byte=current[-1]
    payload=bytes(data);(out/f'D{ch}.bin').write_bytes(payload)
    (out/f'D{ch}_times.json').write_text(json.dumps(times),encoding='utf-8')
    frames=[];at=0
    while True:
        at=payload.find(b'OTA2',at)
        if at<0:break
        if at+24>len(payload):break
        length=int.from_bytes(payload[at+20:at+22],'little');end=at+28+length
        if length<=512 and end<=len(payload):
            b=payload[at:end];frames.append(dict(time=times[at],type=b[5],session=int.from_bytes(b[8:12],'little'),
              sequence=int.from_bytes(b[12:16],'little'),offset=int.from_bytes(b[16:20],'little'),bytes=len(b),
              crc32=zlib.crc32(b[:-4])==int.from_bytes(b[-4:],'little')))
        at+=4
    (out/f'D{ch}_frames.json').write_text(json.dumps(frames,indent=2),encoding='utf-8')
    return dict(channel=ch,seconds=samples/10000000,decoded_bytes=len(payload),framing_rejections=bad,frames=frames)

if __name__=='__main__':
    folder=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=True,parents=True)
    result={'mapping':'plane*64+index, 1MiB blocks, LSB-first','channels':[decode(folder,ch,out) for ch in (0,1)],'analog_margin_proven':False}
    (out/'decode.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    for c in result['channels']:
        print('D',c['channel'],'seconds',c['seconds'],'bytes',c['decoded_bytes'],'bad',c['framing_rejections'])
        print(json.dumps([f for f in c['frames'] if f['type']>=240],indent=2))

"""SAM | 2026-10-25 +08:00 | Decode archived DL32 sparse bit-packed samples only; never touch live cache."""
from pathlib import Path
import json,hashlib
import numpy as np
R=Path(__file__).resolve().parents[2];D=R/'logs/r5_live_20261025';m=json.loads((D/'status_capture.json').read_text());root=Path(m['archive'])
def decode(channel):
    folder=root/str(channel);count=int((folder/'channel.ini').read_text().splitlines()[2]);raw=np.full((count+7)//8,255,dtype=np.uint8)
    for row in (folder/'files.ini').read_text().splitlines():
        plane,index,name=row.split(',');assert plane=='0';data=(root/name).read_bytes();start=int(index)*1048576
        n=min(len(data),len(raw)-start)
        if n>0:raw[start:start+n]=np.frombuffer(data[:n],dtype=np.uint8)
    previous=raw<<1;previous[1:]|=raw[:-1]>>7;previous[0]|=1
    falling=(~raw)&previous;del previous
    period=10000000/460800;cursor=0;output=[];times=[];bad=0
    bit=lambda at:(int(raw[at>>3])>>(at&7))&1
    for byte in np.flatnonzero(falling):
        mask=int(falling[byte])
        for k in range(8):
            if not(mask&(1<<k)):continue
            edge=int(byte)*8+k
            if edge<cursor or edge+10*period>=count:continue
            if bit(round(edge+period*.5))!=0:continue
            value=sum(bit(round(edge+(1.5+i)*period))<<i for i in range(8))
            if bit(round(edge+period*9.5))!=1:bad+=1;cursor=edge+round(period);continue
            output.append(value);times.append(round(edge/10000000,7));cursor=edge+round(period*9.6)
    payload=bytes(output);(D/('status_D'+str(channel)+'.bin')).write_bytes(payload)
    text=payload.decode('utf-8',errors='replace');selected=[line[:1100] for line in text.splitlines() if any(k in line for k in ('FW_VERSION','FOTA_STATUS','OTA_REASON=','OTA_PROGRESS=','OTA_STEP='))]
    return {'channel':channel,'bytes':len(payload),'framing_rejections':bad,'first_byte_seconds':times[0] if times else None,'last_byte_seconds':times[-1] if times else None,'sha256':hashlib.sha256(payload).hexdigest(),'selected_lines':selected,'query_present':b'FW_VERSION\r\n' in payload,'fota_query_present':b'FOTA_STATUS\r\n' in payload}
result={'capture':m,'channels':[decode(0),decode(1)],'analog_margin_proven':False,'ota_started':False}
(D/'uart_decode.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))

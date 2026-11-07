"""SAM | 2026-10-25 +08:00 | Decode legacy 68-byte or peer-extended 116-byte RAM evidence; no device access."""
import json,struct,sys
from pathlib import Path
data=Path(sys.argv[1]).read_bytes()
if len(data) not in (68,116): raise SystemExit('Expected exactly 68 legacy or 116 peer-evidence bytes; never pad a short read')
v=struct.unpack('<17I',data[:68])
names=['unknown_input_or_call','alarm','call','activity','peer','provision','owner_load','phase','epoch','owner_identity','hash','progress','total','watchdog']
out=dict(sequence=v[0],denials=v[1],mask=hex(v[2]),causes=[s for i,s in enumerate(names) if v[2]&(1<<i)],
 clock_ms=v[3],battery_age_ms=v[4],keys_age_ms=v[5],motion_age_ms=v[6],sample_flags=hex(v[7]),
 epoch=v[8],total=v[9],accepted=v[10],durable=v[11],gate_bits=hex(v[12]),watchdog=v[13],owner_epoch=v[14],owner_phase=v[15],saved_total=v[16])
if v[0]!=1: out['status']='NO_COMMITTED_DENIAL'
else: out['status']='FIRST_DENIAL_RECORDED'
# SAM | 2026-10-25 +08:00 | Preserve legacy output; decode only a complete appended peer record.
if len(data)==116:
    p=struct.unpack('<12I',data[68:])
    networks=['unknown','no_sim','registering','ip','mqtt','offline']
    calls=['idle','dialing','incoming','connected','ended','failed','unknown']
    def network(n):return networks[n] if n<len(networks) else 'unrecognized_'+str(n)
    def source(n):
        names=['init','hello','link_invalidated','uart_rx_lost','rx_timeout','sleep_restore','power_off']
        if n<len(names):return names[n]
        if 16<=n<16+len(networks):return 'network_'+network(n-16)
        return 'unrecognized_'+str(n)
    out['peer']=dict(transport_ready=bool(p[0]),network_code=p[1],network=network(p[1]),
        last_rx_ms=p[2],rx_age_ms=p[3],change_ms=p[4],source_code=p[5],source=source(p[5]),
        previous_transport_ready=bool(p[6]),previous_network_code=p[7],previous_network=network(p[7]),
        call_code=p[8],call=calls[p[8]] if p[8]<len(calls) else 'unrecognized_'+str(p[8]),
        last_hello_ms=p[9],last_loss_ms=p[10],last_loss_source_code=p[11],last_loss_source=source(p[11]))
print(json.dumps(out,indent=2))

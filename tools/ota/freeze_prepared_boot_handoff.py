"""SAM | 2026-10-27 +08:00 | Freeze the original cached Boot project; support ARMCC's one-target-per-line .d files. Never compile or program hardware."""
from pathlib import Path
import datetime,hashlib,json,re,xml.etree.ElementTree as ET
r=Path(__file__).resolve().parents[2]
a=r/'logs/r6_install_stages_20261027/boot_handoff'
project=r/'firmware_releases/GR_BOOT_MOTION_BASELINE_20261024/BOOT_BIND_MOTION_BASELINE_FPU_FIX.uvprojx'
o=Path(ET.parse(project).find('.//OutputDirectory').text)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
deps={};stale=[];paths={}
for d in o.glob('*.d'):
 obj=d.with_suffix('.o')
 if not obj.exists():continue
 raw=d.read_text(errors='replace').replace('\\\n',' ')
 text='\n'.join(line.partition(': ')[2] for line in raw.splitlines() if ': ' in line)
 newer=[]
 for token in re.findall(r'"[^\"]+"|(?:\\ |[^\s])+',text):
  token=token.strip('"').replace('\\ ',' ')
  if token=='\\':continue
  if token not in paths:
   p=Path(token);paths[token]=(p if p.is_absolute() else project.parent/p).resolve()
  p=paths[token];assert p.is_file(),str(p)
  if str(p) not in deps:deps[str(p)]=sha(p)
  if p.stat().st_mtime>obj.stat().st_mtime:newer.append(str(p))
 if newer:stale.append({'object':obj.name,'newer_inputs':list(dict.fromkeys(newer))})
review=['tools/ota/boot/yp001_ota_entry.c','tools/ota/boot/yp001_ota_prepared_repair.h','tools/ota/boot/yp001_ota_r6_repair_scope.h','firmware_releases/GR_BOOT_MOTION_BASELINE_20261024/yp001_boot_provision.c']
axf=o/'YP001_OTA_BOOT_CANDIDATE.axf'
state={'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'project':str(project),'project_sha256':sha(project),'output_directory':str(o),'dependencies':deps,'reviewed_sources':{p:sha(r/p) for p in review},'stale_units':stale,'previous_axf_sha256':sha(axf),'gr_app_sha256':sha(r/'firmware_releases/gr_install_stages_20261027/baseline/baseline_signed.bin'),'requires_manual_boot_compile':True,'device_written':False}
assert not (a/'boot_frozen_inputs.json').exists(),'PRESERVE_FROZEN_INPUTS'
(a/'boot_frozen_inputs.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
p=r/'firmware_releases/gr_install_stages_20261027/paired_downloads.json';m=json.loads(p.read_text());m.update(deployment_ready=False,superseded_boot_candidate=True,blocked_reason='Existing PREPARED journal requires exact scoped Boot handoff; descriptor-only candidate must not be deployed');p.write_text(json.dumps(m,indent=2),encoding='utf-8')
print(json.dumps({'boot_project':str(project),'dependencies':len(deps),'stale_units':[x['object'] for x in stale],'gr_recompile_required':False},indent=2))

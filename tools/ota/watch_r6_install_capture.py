"""SAM | 2026-10-27 21:07 +08:00 | Wait for a newly acknowledged DL32 capture before sending the approved R6 command once."""
from pathlib import Path
import datetime,json,re,subprocess,time

ROOT=Path(r'D:\CODEX\sos-card')
APP=Path(r'C:\Users\SamLi\AppData\Roaming\ALIENTEK\ATK-LogicView')
started=datetime.datetime.now()
end=time.monotonic()+120
marker=ROOT/'logs/r6_install_only_once_20261027/command_reserved.json'
if marker.exists():
 print('HOST_COMMAND_ALREADY_RESERVED_DO_NOT_RESEND',flush=True);raise SystemExit(2)
print('WATCHING_FOR_NEW_DL32_START',flush=True)
while time.monotonic()<end:
 logs=list((APP/'log').glob('*.log'))
 if logs:
  s=max(logs,key=lambda x:x.stat().st_mtime).read_bytes().decode('gb18030',errors='replace')
  matches=list(re.finditer(r'(?m)^(\d\d)-(\d\d)-(\d\d)\.\d+:\s*启动采集\s*$',s))
  if matches:
   m=matches[-1];now=datetime.datetime.now();stamp=now.replace(hour=int(m[1]),minute=int(m[2]),second=int(m[3]),microsecond=0);tail=s[m.start():]
   age=(now-stamp).total_seconds()
   invalid=any(x in tail for x in ('应答超时','设备通信异常','采集任务线程退出','用户手动停止任务线程'))
   if stamp>=started-datetime.timedelta(seconds=1) and 0<=age<35 and not invalid and '采集任务线程启动' in tail and '收到应答指令:18' in tail:
    sessions=sorted((APP/'temp/memory').glob('*'),key=lambda x:x.stat().st_mtime,reverse=True)
    for d in sessions:
     f=d/'recovery.json'
     if not (d.is_dir() and d.name.isdigit() and f.exists()):continue
     try:captured=datetime.datetime.fromisoformat(json.loads(f.read_text(encoding='utf-8'))['collectDate'])
     except (ValueError,KeyError,OSError):continue
     if abs((captured-stamp).total_seconds())>8:continue
     print('CAPTURE_READY',d.name,'AGE',round(age,1),flush=True)
     raise SystemExit(subprocess.call(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/ota/Invoke-R6InstallOnceLive.ps1'),'-CaptureSession',d.name]))
 time.sleep(.25)
print('CAPTURE_WAIT_TIMEOUT_NO_COMMAND',flush=True)
raise SystemExit(3)

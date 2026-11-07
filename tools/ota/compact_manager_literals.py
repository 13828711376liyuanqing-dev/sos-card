"""SAM | 2026-10-26 +08:00 | Share immutable repeated status/error literals only when the real Luatools compiler proves smaller output; no predicate or message changes."""
from pathlib import Path
import re,collections,subprocess,json

COMPILER='D:/Installers/_temp/tools/luac_64bit.exe'
TOKEN=re.compile(r'''--[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' ''',re.X)

def compact(source: str, work: Path):
    work.mkdir(parents=True,exist_ok=True)
    path=work/'trial.lua';binary=work/'trial.luac'
    def size(text):
        path.write_text(text,encoding='utf-8')
        subprocess.run([COMPILER,'-s','-o',str(binary),str(path)],check=True,capture_output=True)
        return binary.stat().st_size
    counts=collections.Counter(t.group()[1:-1] for t in TOKEN.finditer(source)
        if not t.group().startswith('--') and re.fullmatch('[A-Z][A-Z0-9_]{11,}',t.group()[1:-1]))
    candidates=sorted((s for s,n in counts.items() if n>1),key=lambda s:(-(len(s)-8)*(counts[s]-1),s))
    text=source;initial=current=size(text);kept=[]
    anchor='local M = {}';assert text.count(anchor)==1
    for value in candidates:
        name='K_'+value
        def replace(m):
            token=m.group()
            return name if not token.startswith('--') and token[1:-1]==value else token
        trial=TOKEN.sub(replace,text)
        trial=trial.replace(anchor,anchor+'\nlocal '+name+'='+repr(value),1)
        measured=size(trial)
        if measured<current:
            kept.append({'literal':value,'saved':current-measured});text=trial;current=measured
    if kept:
        text=text.replace(anchor,'-- SAM | 2026-10-26 +08:00 | Intern identical immutable diagnostic/phase strings; all predicates and emitted values are preserved.\n'+anchor,1)
    return text,{'initial_bytes':initial,'final_bytes':current,'saved':initial-current,'shared':kept}

def runtime_gates(text):
    # SAM | 2026-10-26 +08:00 | Keep the same protected idle lookup and evaluation order at all call sites; share one pure boolean adapter.
    assert 'local function business_idle()' not in text
    pattern=r'''invoke\(base,(["'])idle\1\)(==|~=)true'''
    text,n=re.subn(pattern,lambda m:'business_idle()' if m[2]=='==' else 'not business_idle()',text)
    assert n>=10,n
    anchor='    local base=options.port or require("ota_platform").default()'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+"\n    -- SAM | 2026-10-26 +08:00 | Share the unchanged protected business-idle predicate to fit the fixed script partition.\n    local function business_idle() return invoke(base,'idle')==true end")
    text=text.replace('idle=function() return business_idle() end,','idle=business_idle,')
    old='now=function() return mcu and type(mcu.ticks)=="function" and mcu.ticks() or nil end,'
    assert text.count(old)==1
    text=text.replace(old,'-- SAM | 2026-10-26 +08:00 | Reuse the validated clock adapter; the sender still rejects invalid/non-uint clocks.\n            now=monotonic_ms,')
    return text

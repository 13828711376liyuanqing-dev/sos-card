"""SAM | 2026-10-25 +08:00 | Freeze reviewed inputs and run only new combination gates; never compile GR or touch a device."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,datetime,shutil,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[2];OUT=R/'firmware_releases/gr_uart_window_20261025'
PREVIEW=R/'logs/uart_window_20261025/capacity_preview'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(cmd,variant=None):
    env=os.environ.copy();env.pop('OTA_RELEASE_VARIANT',None)
    if variant:env['OTA_RELEASE_VARIANT']=variant
    p=subprocess.run([sys.executable,'-X','utf8']+cmd,cwd=R,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    item={'command':cmd,'variant':variant,'exit':p.returncode,'output':p.stdout+p.stderr}
    if p.returncode:raise RuntimeError(json.dumps(item,ensure_ascii=False))
    return item
def main():
    assert not (OUT/'frozen_inputs.json').exists(),'PRESERVE_FROZEN_COLLECTION'
    results=[];cache=R/'logs/uart_window_20261025/freeze_checks.json'
    test_pin=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((R/'Air780EGH').glob('*.lua')))+b''.join(p.read_bytes() for p in sorted((R/'tools/ota').glob('test_*retire*')))).hexdigest()
    if cache.exists():
        prior=json.loads(cache.read_text(encoding='utf-8'))
        if prior['pin']==test_pin:results=prior['results']
    # The changed business producer needs its whole small suite; UART/owner checks run on both release variants.
    if not results:
        results.append(check(['tools/business/test_cat_business.py']))
        results.append(check(['tools/ota/test_gr_retire_port.py']))
        for kind in ('baseline','target'):
            for test in ('test_uart_flash_window.py','test_business_backpressure.py','test_retire_r4.py','test_trial_budget.py'):
                results.append(check(['tools/ota/'+test],kind))
        cache.write_text(json.dumps({'pin':test_pin,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    capacities={};cat={}
    for kind in ('baseline','target'):
        folder=PREVIEW/kind;current=json.loads((folder/'latest_capacity.json').read_text())
        report=json.loads(Path(current['report']).read_text(encoding='utf-8-sig'))
        assert current['script_bytes']<=524288 and report['native_structure_verified'] and report['decompressed_readback_verified']
        vendor={}
        for name,h in current['source_sha256'].items():
            path=folder/'source'/name
            if not path.exists():
                assert name in ('air1103.lua','es8311.lua','exsipclient.lua','exsipproto.lua'),name
                path=Path('D:/Installers/resource/soc_script/v2026.10.13.20/lib')/name
                vendor[str(path)]=h
            assert digest(path)==h,name
        audit=json.loads((folder/'log_equivalence.json').read_text());assert all(x['nonliteral_bytes_unchanged'] for x in audit)
        for x in audit:assert hashlib.sha256((folder/'source'/x['file']).read_text(encoding='utf-8-sig').encode()).hexdigest()==x['result_sha256']
        capacities[kind]={'bytes':current['script_bytes'],'spare':524288-current['script_bytes'],'report':current['report'],'report_sha256':digest(Path(current['report'])),'vendor_sources':vendor}
        dest=OUT/'cat1'/kind;dest.mkdir(parents=True,exist_ok=True)
        assert not (dest/'source').exists(),'PRESERVE_CAT_SOURCE'
        shutil.copytree(folder/'source',dest/'source',dirs_exist_ok=False)
        shutil.copy2(folder/'log_dictionary.json',dest/'log_dictionary.json')
        shutil.copy2(folder/'log_equivalence.json',dest/'log_equivalence.json')
        cat[kind]={str(p.relative_to(R)):digest(p) for p in (dest/'source').iterdir() if p.is_file()}
    left=OUT/'cat1/baseline/source';right=OUT/'cat1/target/source'
    differing=[p.name for p in left.iterdir() if p.is_file() and p.read_bytes()!=(right/p.name).read_bytes()]
    assert differing==['main.lua'],differing
    expected=(left/'main.lua').read_text(encoding='utf-8').replace('VERSION = "001.000.002"','VERSION = "001.005.000"').replace('PRODUCT_VERSION = "1.0.2"','PRODUCT_VERSION = "1.5.0"').replace('FW_RELEASE_BUILD = 3','FW_RELEASE_BUILD = 4')
    assert expected==(right/'main.lua').read_text(encoding='utf-8')
    projects={};inputs={}
    for kind,name in [('baseline','YP001_BASELINE_UART_RECOVERY_20261025.uvprojx'),('target','YP001_TARGET_USB_BENCH_20261024.uvprojx')]:
        project=R/'ble_app_uart_c/Keil_6'/name;x=E.parse(project).getroot()
        obj=Path(x.findtext('.//OutputDirectory'));assert obj.is_dir()
        assert 'YP001_OTA_USB_BENCH_TEST=1' in x.findtext('.//Cads/VariousControls/Define')
        # Hash actual project source/library inputs and direct include-directory headers, preserving existing caches/settings.
        paths=[project]
        if project.with_suffix('.uvoptx').exists():paths.append(project.with_suffix('.uvoptx'))
        for f in x.findall('.//FilePath'):
            path=(project.parent/f.text).resolve();assert path.is_file(),path;paths.append(path)
        incs=x.findtext('.//TargetCommonOption/IncludePath','')+';'+x.findtext('.//Cads/VariousControls/IncludePath','')
        for inc in incs.split(';'):
            if inc:
                directory=(project.parent/inc).resolve()
                paths.extend(directory.glob('*.h'))
        scatter=x.findtext('.//LDads/ScatterFile','')
        if scatter:paths.append((project.parent/scatter).resolve())
        for path in paths:
            assert path.is_relative_to(R),'NONWORKSPACE_BUILD_INPUT: '+str(path)
            inputs[str(path.relative_to(R))]=digest(path)
        projects[kind]={'project':str(project),'object_dir':str(obj),'output':x.findtext('.//OutputName'),'version':'1.0.2' if kind=='baseline' else '1.5.0','build':3 if kind=='baseline' else 4}
    sources={str(p.relative_to(R/'ble_app_uart_c/Src')):digest(p) for p in (R/'ble_app_uart_c/Src').rglob('*') if p.is_file() and p.suffix.lower() in ('.c','.h','.s','.sct')}
    frozen={'time':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'phase':'SOURCE_FROZEN_AWAIT_MANUAL_F7','projects':projects,'inputs':inputs,'sources':sources,'cat_sources':cat,'capacity':capacities,'required_symbols':{'g_cat_uart_first_fault':44,'g_cat_uart_recovery':36,'yp001_ota_rx_denial':116,'g_ota_window_trace':48},'new_attempt_authorized':False,'device_written':False,'physical_timing_accepted':False}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'combination_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for kind,meta in projects.items():
        dest=OUT/kind;dest.mkdir(exist_ok=True)
        (dest/'source_manifest.json').write_text(json.dumps(dict(meta,sources=sources,download_ready=False),indent=2),encoding='utf-8')
    (OUT/'frozen_inputs.json').write_text(json.dumps(frozen,indent=2),encoding='utf-8')
    print(json.dumps({'phase':frozen['phase'],'focused_checks':len(results),'capacity':capacities,'projects':projects},indent=2))
if __name__=='__main__':main()

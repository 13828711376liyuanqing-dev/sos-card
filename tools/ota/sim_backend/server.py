"""SAM | 2026-10-21 +08:00 | Local-only OTA workflow regression console; no device or production platform access."""
import argparse
import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import uuid
# SAM | 2026-10-21 +08:00 | Resolve local upload/packaging modules for the operator console.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sim_backend import release_store

ROOT = Path(__file__).resolve().parents[3]
SUITES = {
    'release_store': ('双组件版本打包/上传归档/坏HEX拒绝', 'test_release_store.py'),
    'prepare_release': ('真实固件测试归档/签名/禁止覆盖', 'test_prepare_release.py'),
    'mqtt_transport': ('本地TCP MQTT/HTTP磁盘联通/结果补报', 'test_mqtt_transport.py'),
    'platform_flow': ('协议映射/GR至CAT1顺序任务/结果补报', 'test_platform_flow.py'),
    'disk_download': ('磁盘检查点/二进制续传/断网恢复', 'test_disk_download.py'),
    'package_http': ('真实HTTP/Range续传/Lua签名校验', 'test_package_http.py'),
    'signed_manifest': ('测试信任域/真实签名/篡改拒绝', 'test_signed_manifest.py'),
    'cat_manager': ('CAT1任务/串行授权/恢复', 'test_cat_manager.py'),
    'runtime': ('CAT1运行时/重启保护/结果上报', 'test_runtime.py'),
    'download': ('下载续传/坏包/数据保持', 'test_download.py'),
    'gr_coordinator': ('GR协调器/安全条件/持久化故障', 'run_gr_coordinator_tests.py'),
    'gr_flash': ('GR交换后端/服务失败/用户区保护', 'test_gr_flash.py'),
    'gr_handoff': ('GR跳转/看门狗故障', 'test_gr_sdk_handoff.py'),
    'layout': ('候选布局边界', 'test_layout.py'),
}
LOCK = threading.Lock()
STATE = {'running': False, 'report': None, 'error': None}
TOKEN = secrets.token_urlsafe(32)

def selected_suites(names):
    if not isinstance(names, list) or not names or any(not isinstance(n, str) or n not in SUITES for n in names):
        raise ValueError('请选择已登记的测试组')
    return list(dict.fromkeys(names))

def source_hashes():
    paths = list((ROOT/'Air780EGH').glob('ota_*.lua'))
    paths += list((ROOT/'tools/ota/boot').glob('*.[ch]'))
    paths += list((ROOT/'ble_app_uart_c/Src/user/ota').glob('*.[ch]'))
    # SAM | 2026-10-21 +08:00 | Include harness inputs so changing assertions cannot masquerade as identical evidence.
    for pattern in ('*.py', '*.c', '*.ps1'):
        paths += list((ROOT/'tools/ota').glob(pattern))
    paths += [Path(__file__).resolve(), Path(__file__).parent/'index.html']
    paths += list((Path(__file__).parent).glob('*.py'))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}

def run_suites(names, directory, execute=subprocess.run):
    names = selected_suites(names)
    directory.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    report = {'mode': 'HOST_SIMULATION_ONLY', 'device_verified': False,
              'crypto_verified': False, 'production_install_enabled': False,
              'started': datetime.datetime.now().astimezone().isoformat(),
              'results': [], 'source_sha256': before, 'directory': str(directory)}
    for name in names:
        title, script = SUITES[name]
        command = [sys.executable, str(ROOT/'tools/ota'/script)]
        try:
            result = execute(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace', timeout=180,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            code, output = result.returncode, result.stdout or ''
        except subprocess.TimeoutExpired as exc:
            # SAM | 2026-10-21 +08:00 | Preserve progress before timeout so failures remain diagnosable.
            partial = exc.output or ''
            if isinstance(partial, bytes):
                partial = partial.decode('utf-8', errors='replace')
            code, output = -1, partial + '\n' + str(exc)
        except OSError as exc:
            code, output = -1, str(exc)
        (directory/(name+'.log')).write_text(output, encoding='utf-8')
        report['results'].append({'id': name, 'title': title, 'exit_code': code,
                                  'passed': code == 0, 'log': output})
    report['source_unchanged'] = before == source_hashes()
    report['passed'] = report['source_unchanged'] and all(x['passed'] for x in report['results'])
    report['finished'] = datetime.datetime.now().astimezone().isoformat()
    (directory/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# OTA 本地模拟回归', '', '仅主机测试；未验收真实签名、MQTT平台或实板OTA。', '',
             f"总体：{'通过' if report['passed'] else '失败'}；源码期间未变化：{report['source_unchanged']}", '',
             '| 测试组 | 结果 |', '|---|---|']
    lines += [f"| {x['title']} | {'通过' if x['passed'] else '失败'} |" for x in report['results']]
    (directory/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return report

def worker(names):
    directory = ROOT/'logs/ota_sim_backend'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    try:
        report = run_suites(names, directory)
        with LOCK:
            STATE['report'] = report
    except Exception as exc:
        with LOCK:
            STATE['error'] = str(exc)
    finally:
        with LOCK:
            STATE['running'] = False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, content, kind='application/json; charset=utf-8'):
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.local_host():
            return self.send(403, '{}')
        if self.path == '/':
            page = (Path(__file__).parent/'index.html').read_text(encoding='utf-8')
            return self.send(200, page.replace('__TOKEN__', TOKEN), 'text/html; charset=utf-8')
        if self.path == '/api/status':
            with LOCK:
                data = dict(STATE, suites={k:v[0] for k,v in SUITES.items()})
            return self.send(200, json.dumps(data, ensure_ascii=False))
        if self.path == '/api/releases':
            return self.send(200,json.dumps(release_store.releases(),ensure_ascii=False))
        if self.path.startswith('/packages/'):
            try:
                path=release_store.archive(self.path[len('/packages/'):])
                body=path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','application/zip')
                self.send_header('Content-Disposition','attachment; filename="'+path.name+'"')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            except (ValueError,OSError,KeyError):self.send(404,'{}')
            return
        self.send(404, '{}')

    def do_POST(self):
        if not self.local_host() or self.headers.get('X-OTA-Token') != TOKEN:
            return self.send(403, '{}')
        if self.path == '/api/upload':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=release_store.LIMIT:raise ValueError('文件为空或超过16MiB')
                data=self.rfile.read(length)
                if len(data)!=length:raise ValueError('上传未完整接收')
                entry=release_store.upload(data,self.headers.get('X-Component'),self.headers.get('X-Source-Version'),
                    self.headers.get('X-Target-Version'),self.headers.get('X-Package-Type'))
                return self.send(201,json.dumps(entry,ensure_ascii=False))
            except (ValueError,OSError,TypeError) as exc:
                return self.send(400,json.dumps({'error':str(exc)},ensure_ascii=False))
        if self.path != '/api/run':
            return self.send(404, '{}')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError('请求大小错误')
            names = selected_suites(json.loads(self.rfile.read(size)).get('suites'))
        except (ValueError, AttributeError):
            return self.send(400, '{"error":"invalid request"}')
        with LOCK:
            if STATE['running']:
                return self.send(409, '{"error":"测试正在运行"}')
            STATE.update(running=True, error=None, report=None)
        threading.Thread(target=worker, args=(names,), daemon=True).start()
        self.send(202, '{"accepted":true}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-all', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.run_all:
        worker(list(SUITES))
        print(json.dumps(STATE, ensure_ascii=False, indent=2))
        sys.exit(0 if STATE['report'] and STATE['report']['passed'] else 1)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'OTA本地模拟后台：http://127.0.0.1:{server.server_port}（Ctrl+C停止）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

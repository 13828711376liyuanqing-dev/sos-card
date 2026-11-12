"""SAM | 2026-11-02 +08:00 | Run the real Air780EGH/resident_name.lua under Lua 5.4 (lupa) with LuatOS stubs:
platform residentNameMsg -> CAT1 lines -> fed into the real GR C code (test_name_push.exe) -> NAME_RES back to CAT1
-> residentNameReply. Also checks rejection, stale Seq, and GR 'need' handling (resend from RAM vs ask platform)."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'logs' / 'cat1_antenna_20261010' / 'python_deps'))
sys.path.insert(0, str(ROOT / 'tools' / 'glyph_maker'))
from lupa import lua54  # noqa: E402
import glyphlib as G  # noqa: E402

SRC = ROOT / 'Air780EGH'
WEB = {}
OUT = ROOT / 'logs' / 'name_push_20261102'
fails = []


def bus(lines):
    return [l for l in lines if l.startswith('BUS_EVT=')]


def holds(lines):
    return [l.strip() for l in lines if l.startswith('[OTA_HOLD]')]


def check(cond, what):
    print(('PASS ' if cond else 'FAIL ') + what)
    if not cond:
        fails.append(what)


def runtime():
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    sent, published = [], []

    def py_encode(v):
        def conv(x):
            if lua54.lua_type(x) == 'table':
                keys = list(x.keys())
                if keys and all(isinstance(k, int) for k in keys):
                    return [conv(x[k]) for k in sorted(keys)]
                return {k: conv(x[k]) for k in keys}
            return x
        return json.dumps(conv(v), ensure_ascii=False, separators=(',', ':'))

    def py_decode(s):
        def conv(x):
            if isinstance(x, dict):
                return L.table_from({k: conv(v) for k, v in x.items()})
            if isinstance(x, list):
                return L.table_from([conv(v) for v in x])
            return x
        return conv(json.loads(s))

    L.globals().py_encode = py_encode
    L.globals().py_decode = py_decode
    L.globals().py_sent = lambda line: sent.append(line) or True
    L.globals().py_pub = lambda *a: published.append(list(a))
    import hashlib
    L.globals().py_md5hex = lambda h: hashlib.md5(bytes.fromhex(h)).hexdigest().upper()
    L.globals().py_md5 = lambda s: hashlib.md5(s.encode('utf-8') if isinstance(s, str) else bytes(s)).hexdigest().upper()
    L.globals().py_http = lambda url: WEB.get(url, (404, ''))
    L.execute(f"package.path = [[{SRC.as_posix()}]] .. '/?.lua;' .. package.path")
    L.execute(r'''
        json = {encode = py_encode, decode = py_decode}
        log = {info = function() end, warn = function() end}
        mobile = {imei = function() return "860123456789024" end}
        crypto = {md5 = function(s) return py_md5hex((s:gsub('.', function(c) return string.format('%02x', c:byte()) end))) end}
        -- fake file system: never touch real files from the host test
        FS = {["/log/app.log"] = 2000, ["/log/app.log.bak"] = 1000, ["/log/ble.ini"] = 300}
        EVENTS = {}
        io.fileSize = function(f) return FS[f] end
        os.remove = function(f) if FS[f] then FS[f] = nil; EVENTS[#EVENTS + 1] = "rm " .. f; return true end return nil end
        http = {request = function(m, url) EVENTS[#EVENTS + 1] = "http"; return {wait = function() local c, b = py_http(url); return c, {}, b end} end}
        _G.at_cmd_handlers = {}
        package.loaded.ota_runtime = {instance = function() return {status = function() return {phase = "IDLE"} end} end}
        auto_reply = false   -- true: GR answers name_end immediately, inside the send loop (as on the real board)
        _G.uart_send_raw = function(l)
            local r = py_sent(l)
            if auto_reply and l:find('"op":"name_end"', 1, true) then
                local id = l:match('"id":(%d+)')
                _G.at_cmd_handlers["NAME_RES="]('NAME_RES={"op":"result","id":' .. id .. ',"ok":true,"err":0,"i":0}')
            end
            return r
        end
        tasks, waiting = {}, {}
        sys = {}
        function sys.taskInit(f) local co = coroutine.create(f); tasks[#tasks+1] = co; return co end
        function sys.wait(ms) coroutine.yield({wait = ms}) end
        function sys.waitUntil(topic, ms) local r = coroutine.yield({topic = topic}); if r then return true, r end return false end
        function sys.publish(topic, a, b, c, d)
            if topic == "RESIDENT_NAME_RES" then
                -- LuatOS semantics: an event published while nobody waits for it is lost
                local w = false
                for _, v in pairs(waiting) do if v == "topic" then w = true end end
                if w then pending = a end
            else py_pub(topic, a, b, c, d) end
        end
        -- run every task until it blocks; deliver a pending NAME_RES to whoever waits for it
        function step()
            for _ = 1, 200 do
                local any = false
                for i = #tasks, 1, -1 do
                    local co = tasks[i]
                    if coroutine.status(co) == "dead" then table.remove(tasks, i) else
                        local arg, run = nil, true
                        if waiting[co] == "topic" then
                            if pending then arg = pending; pending = nil
                            elseif timeout_now then timeout_now = false
                            else run = false end
                        end
                        if run then
                            local ok, y = coroutine.resume(co, arg)
                            if not ok then error(y) end
                            waiting[co] = y and y.topic and "topic" or nil
                            any = true
                        end
                    end
                end
                if not any then return end
            end
        end
        function tick() timeout_now = true; step() end
    ''')
    mod = L.execute('return (require("resident_name"))')
    return L, mod, sent, published


def gr_answer(lines, name):
    """Feed CAT1-produced lines to the real GR C code and return its NAME_RES lines."""
    f = OUT / 'cat1_lines.txt'
    f.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (OUT / 'cat1_lines.txt.hex').write_text((OUT / 'lines.txt.hex').read_text(encoding='utf-8'), encoding='utf-8')
    exe = OUT / 'test_name_push.exe'
    env_path = r'D:\Program Files\GUI Guider\environment\mingw\bin'
    import os
    r = subprocess.run([str(exe), str(f), name.encode().hex(), str(OUT / 'lines_big.txt')], capture_output=True, timeout=30,
                       env=dict(os.environ, PATH=env_path + os.pathsep + os.environ['PATH']))
    out = (r.stdout + r.stderr).decode('utf-8', 'replace')
    return r.returncode, out


def main():
    name = '欧阳䶮𠮷'   # 11-03: characters in the device font are no longer pushed, so use ones that are not
    glyphs = G.resident_glyphs(name, '泰康之家·鹏园')
    msg = G.platform_msg(name, '1#1-102', '泰康之家·燕园', 1730500000, glyphs)
    L, mod, sent, pub = runtime()
    lua_msg = L.globals().py_decode(json.dumps(msg, ensure_ascii=False))

    # 1. platform message -> lines identical (as JSON) to what glyph_maker predicts
    mod.on_platform(lua_msg)
    L.globals().step()
    expect = G.bus_lines(msg, txn=1)
    got = bus(sent)
    check(holds(sent)[:1] == ['[OTA_HOLD] 1'], 'power hold [OTA_HOLD] 1 sent before the first data line')
    check(len(got) == len(expect), f'CAT1 sent {len(got)} lines (expect {len(expect)})')
    check(all(json.loads(a[8:]) == json.loads(b[8:]) for a, b in zip(got, expect)), 'lines equal glyph_maker output')
    check(max(len(l.encode()) for l in got) < 400, 'every line < 400 B')

    # 2. those exact lines through the real GR code
    rc, out = gr_answer(got, name)
    check(rc == 0 and 'ALL PASS' in out, 'GR C code accepts CAT1 lines (commit + byte-identical bitmaps)')

    # 3. GR result back -> platform reply ok
    L.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"result","id":1,"ok":true,"err":0,"i":0}')
    L.globals().step()
    rep = [json.loads(p[3]) for p in pub if p[0] == 'SEND_DATA_REQ']
    check(rep and rep[-1]['MsgType'] == 'residentNameReply' and rep[-1]['Result'] == 'ok', 'platform gets residentNameReply ok')
    check(pub[-1][2].endswith('860123456789024'), 'reply on the device uplink topic')
    check(holds(sent)[-1:] == ['[OTA_HOLD] 0'] and not mod.held(), 'hold released after the reply (OTA idle)')

    # 4. GR reboot asks for glyphs CAT1 still holds -> resend without platform
    sent.clear(); n_pub = len(pub)
    L.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"need","u":"6B27"}')
    L.globals().step()
    check(len(bus(sent)) == len(expect) and len(pub) == n_pub, 'need for held glyph -> CAT1 resends from RAM, no uplink')

    # 5. need for a glyph CAT1 does not hold -> residentNameNeed to platform
    L.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"result","id":2,"ok":true,"err":0,"i":0}')
    L.globals().step()
    L.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"need","u":"73FA"}')
    L.globals().step()
    rep = [json.loads(p[3]) for p in pub if p[0] == 'SEND_DATA_REQ']
    check(rep[-1]['MsgType'] == 'residentNameNeed' and rep[-1]['Missing'] == ['73FA'], 'unknown glyph -> residentNameNeed')

    # 6. invalid and stale messages
    bad = dict(msg, Glyphs=[dict(msg['Glyphs'][0], S=24)])
    sent.clear(); mod.on_platform(L.globals().py_decode(json.dumps(bad, ensure_ascii=False))); L.globals().step()
    rep = [json.loads(p[3]) for p in pub if p[0] == 'SEND_DATA_REQ']
    check(not bus(sent) and rep[-1]['Result'] == 'bad', 'bad glyph size rejected, nothing sent to GR')
    stale = dict(msg, Seq=1)
    mod.on_platform(L.globals().py_decode(json.dumps(stale, ensure_ascii=False))); L.globals().step()
    rep = [json.loads(p[3]) for p in pub if p[0] == 'SEND_DATA_REQ']
    check(not bus(sent) and rep[-1]['Result'] == 'stale', 'older Seq rejected')
    # 6b. A set GR cannot keep is refused here. SAM | 2026-11-04 +08:00 | GR record limit 4000 B (Flash pages; was 1000 B):
    # 28 full 40x40 glyphs make 28 x 216 + 20 = 6068 B.
    big = [G.Glyph(0x4E00 + i, 32, [[1] * 40 for _ in range(40)], 0, 0, 512) for i in range(28)]
    big_msg = G.platform_msg('阿卜杜拉买买提江', '1#1-102', '', 1730500200, big, max_store=0)
    sent.clear(); mod.on_platform(L.globals().py_decode(json.dumps(big_msg, ensure_ascii=False))); L.globals().step()
    rep = [json.loads(p[3]) for p in pub if p[0] == 'SEND_DATA_REQ']
    check(not bus(sent) and rep[-1]['Result'] == 'bad' and rep[-1]['Err'] == 'store', f'record {G.store_bytes(big)} B > 4000 refused (store)')
    # SAM | 2026-11-04 +08:00 | Every non-ASCII Name/Campus character is pushed now (user rule), so a 0-glyph message is an
    # English name with an empty (or ASCII) campus.
    local_msg = G.platform_msg('Anna Smith', '1#1-102', '', 1730500300, G.resident_glyphs('Anna Smith', ''))
    sent.clear(); mod.on_platform(L.globals().py_decode(json.dumps(local_msg, ensure_ascii=False))); L.globals().step()
    check(len(local_msg['Glyphs']) == 0 and len(bus(sent)) == 2 and '"g":0' in bus(sent)[0], 'English name, no campus -> 0 glyphs, delivered')
    # 5-character name + 11-character campus (the largest the user allows) fits the 4 KB storage space
    full = G.resident_glyphs('欧阳䶮𠮷华', '泰康之家·燕园养老社区')
    check(len(full) == 21 and G.store_bytes(full) <= G.MAX_STORE_BYTES, f'5-char name + 11-char campus: {len(full)} glyphs, {G.store_bytes(full)} B <= 4000')
    L.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"result","id":%d,"ok":true,"err":0,"i":0}' % json.loads(bus(sent)[0][8:])['id'])
    L.globals().step(); L.globals().tick()

    # 7. GR never answers -> 3 attempts then fail reply
    L2, mod2, sent2, pub2 = runtime()
    mod2.on_platform(L2.globals().py_decode(json.dumps(msg, ensure_ascii=False)))
    for _ in range(40):
        L2.globals().tick()
    rep = [json.loads(p[3]) for p in pub2 if p[0] == 'SEND_DATA_REQ']
    check(len(bus(sent2)) == 3 * len(expect) and rep and rep[-1]['Result'] == 'fail', 'no GR answer -> 3 tries then fail')

    # 8. one-file delivery by URL (platform residentNameUrl or bench `cat_at NAME_URL=`)
    body = json.dumps(dict(msg, Seq=msg['Seq'] + 100), ensure_ascii=False, separators=(',', ':'))
    import hashlib
    md5 = hashlib.md5(body.encode('utf-8')).hexdigest()
    WEB['http://x/ok.json'] = (200, body)   # lupa hands it to Lua as UTF-8 bytes
    WEB['http://x/other.json'] = (200, '{"a":1}')
    L3, mod3, sent3, pub3 = runtime()
    replies = []
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/ok.json,' + md5, lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(any(r.startswith('OK ') for r in replies) and len(bus(sent3)) == len(expect), 'NAME_URL with MD5 -> downloaded, lines sent to GR')
    replies.clear(); sent3.clear()
    L3.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"result","id":1,"ok":true,"err":0,"i":0}'); L3.globals().step()
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/ok.json,' + '0' * 32, lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(replies[-1] == 'FAIL MD5' and not bus(sent3), 'wrong MD5 -> refused, nothing sent')
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/other.json', lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(replies[-1] == 'FAIL NOT_RESIDENT_NAME_JSON', 'non residentNameMsg file -> refused')
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/missing.json', lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(replies[-1] == 'FAIL HTTP_404', 'HTTP 404 -> refused')
    # JSON only (zip support removed 2026-11-03): md5 from the URL query still enforced; a zip is refused
    import zipfile, io
    raw = json.dumps(dict(msg, Seq=msg['Seq'] + 200), ensure_ascii=False, separators=(',', ':'))
    jmd5 = hashlib.md5(raw.encode('utf-8')).hexdigest()
    WEB['http://x/f?fileId=1&md5=' + jmd5] = (200, raw)
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('residentNameMsg.json', raw)
    WEB['http://x/name.zip'] = (200, zb.getvalue())
    L3.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"result","id":2,"ok":true,"err":0,"i":0}'); L3.globals().step()
    replies.clear(); sent3.clear()
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/f?fileId=1&md5=' + jmd5, lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(any(r.startswith('OK ') for r in replies) and len(bus(sent3)) == len(expect), 'JSON + md5 from URL -> lines sent to GR')
    WEB['http://x/bad?md5=' + '1' * 32] = (200, raw)
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/bad?md5=' + '1' * 32, lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(replies[-1] == 'FAIL MD5', 'md5 in URL is enforced')
    L3.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/name.zip', lambda *a: replies.append(' '.join(map(str, a))))
    L3.globals().step()
    check(replies[-1] == 'FAIL NOT_RESIDENT_NAME_JSON', 'zip no longer accepted (JSON only)')
    rep3 = [json.loads(p[3]) for p in pub3 if p[0] == 'SEND_DATA_REQ']
    check(rep3[-1]['Result'] == 'download', 'download failure reported to platform')

    # 9. an OTA in flight owns the shared GR lock: name delivery must not release it
    L4, mod4, sent4, pub4 = runtime()
    L4.execute('package.loaded.ota_runtime = {instance = function() return {status = function() return {phase = "DOWNLOADING"} end} end}')
    mod4.on_platform(L4.globals().py_decode(json.dumps(msg, ensure_ascii=False)))
    L4.globals().step()
    L4.globals().at_cmd_handlers['NAME_RES=']('NAME_RES={"op":"result","id":1,"ok":true,"err":0,"i":0}')
    L4.globals().step()
    check(not mod4.held() and '[OTA_HOLD] 0' not in holds(sent4), 'OTA busy -> name delivery never sends [OTA_HOLD] 0')

    # 10. board finding 2026-11-02: GR replies before CAT1 starts waiting -> must still count as success (one attempt)
    L5, mod5, sent5, pub5 = runtime()
    L5.execute('auto_reply = true')
    mod5.on_platform(L5.globals().py_decode(json.dumps(msg, ensure_ascii=False)))
    L5.globals().step()
    rep5 = [json.loads(p[3]) for p in pub5 if p[0] == 'SEND_DATA_REQ']
    check(len(bus(sent5)) == len(expect) and rep5 and rep5[-1]['Result'] == 'ok' and not mod5.held(),
          'GR answers instantly -> one attempt, reply ok, hold released')

    # 11. download command clears the logs first (user rule 2026-11-03), keeps ble.ini; not during an OTA
    L6, mod6, sent6, pub6 = runtime()
    WEB['http://x/clear.json'] = (200, json.dumps(msg, ensure_ascii=False))
    rr = []
    L6.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/clear.json', lambda *a: rr.append(' '.join(map(str, a))))
    L6.globals().step()
    ev = list(L6.eval('EVENTS').values())
    check('LOG_CLEARED 3000B' in rr and ev[:3] == ['rm /log/app.log', 'rm /log/app.log.bak', 'http'],
          'logs removed before the download starts, 3000 B reported')
    check(L6.eval('FS["/log/ble.ini"]') == 300, '/log/ble.ini (business data) kept')
    L7, mod7, sent7, pub7 = runtime()
    L7.execute('package.loaded.ota_runtime = {instance = function() return {status = function() return {phase = "DOWNLOADING"} end} end}')
    rr = []
    L7.globals().at_cmd_handlers['NAME_URL=']('NAME_URL=http://x/clear.json', lambda *a: rr.append(' '.join(map(str, a))))
    L7.globals().step()
    check('LOG_CLEARED 0B' in rr and L7.eval('FS["/log/app.log"]') == 2000, 'OTA in flight -> logs not touched')

    print('ALL PASS' if not fails else f'{len(fails)} FAIL')
    return 1 if fails else 0


if __name__ == '__main__':
    raise SystemExit(main())

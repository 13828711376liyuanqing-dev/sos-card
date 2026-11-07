"""SAM | 2026-10-26 +08:00 | Replay preserved wire bytes through production GR parsers; never contact hardware."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/r6_causal_audit_20261026"
LIVE = ROOT / "logs/r6_handoff_20261026/mqtt_live/decode"


def main():
    raw = (LIVE / "D0.bin").read_bytes()
    times = json.loads((LIVE / "D0_times.json").read_text())
    parts = []
    events = []
    for match in re.finditer(rb"BUS_EVT=([^\r\n]+)\r\n", raw):
        if not 109 < times[match.start()] < 109.3:
            continue
        body = json.loads(match[1])
        # Never copy real device identity or user state into generated source.
        if "imei" in body:
            body["imei"] = "123456789012345"
        for key in set(body) - {"op", "imei", "alarm_active", "alarm_id", "state", "active", "id", "component_version", "product_build_version", "build", "epoch", "csq"}:
            raise AssertionError(f"unreviewed fixture key: {key}")
        parts.append("BUS_EVT=" + json.dumps(body, separators=(",", ":")) + "\r\n")
        events.append({"op":body["op"],"time":times[match.start()],"preceding_boundary":raw[match.start()-2:match.start()] == b"\r\n"})
    assert [x["op"] for x in events] == ["hello", "alarm_state", "network", "call", "time", "signal"]
    assert not events[0]["preceding_boundary"]
    fixture = "".join(parts)
    harness = r'''
#include "yp001_business.h"
#include "yp001_ota_wire.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x);exit(1);}}while(0)
bool yp_business_port_time(uint32_t t){return t>1577836800U;}
bool yp_business_port_send(const char *p,size_t n){return p&&n;}
static char text[1024];static size_t used;static unsigned hello_lines,wire_frames;
static void text_sink(const uint8_t *p,size_t n,void *ctx){
 (void)ctx;while(n--){char c=(char)*p++;
  if(c=='\n'){text[used]=0;if(strstr(text,"\"op\":\"hello\""))++hello_lines;
   (void)yp_business_handle_line(text,used);used=0;
  }else if(c!='\r'){CHECK(used<sizeof(text)-1);text[used++]=c;}
 }
}
static void frame_sink(const uint8_t *p,size_t n,void *ctx){(void)p;(void)n;(void)ctx;++wire_frames;}
static void feed(yp001_ota_mux *m,const char *p){
 while(*p)yp001_ota_mux_feed(m,(uint8_t)*p++,109200,text_sink,frame_sink,0);
}
static void run(const char *fixture,int boundary){
 yp001_ota_mux mux={0};yp_business_init();used=hello_lines=wire_frames=0;
 yp_business_observation_clock(109000);yp_business_transport_lost_from(YP_PEER_UART_RX_LOST);
 yp001_ota_mux_lost(&mux);if(boundary)feed(&mux,"\r\n");feed(&mux,fixture);
 const yp_business_status_t *s=yp_business_status();
 CHECK(s->network==YP_NET_MQTT&&s->call==YP_CALL_IDLE&&!s->alarm_active);
 CHECK(wire_frames==0);CHECK(hello_lines==(unsigned)boundary);
 CHECK(s->transport_ready==(boundary!=0));
 printf("%s hello=%u transport=%u mqtt=%u call_idle=%u peer_stable=%u\n",
   boundary?"BOUNDARY_CONTROL":"DEPLOYED_CAPTURE",hello_lines,s->transport_ready,
   s->network==YP_NET_MQTT,s->call==YP_CALL_IDLE,
   s->transport_ready&&s->network==YP_NET_MQTT);
}
int main(void){const char *fixture=FIXTURE;run(fixture,0);run(fixture,1);return 0;}
'''.replace("FIXTURE", json.dumps(fixture))
    OUT.mkdir(exist_ok=True)
    source = OUT / "r6_resync_replay.c"
    source.write_text(harness,encoding="utf-8")
    gcc = Path("D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe")
    env = dict(os.environ, PATH=str(gcc.parent)+os.pathsep+os.environ.get("PATH",""))
    cjson = ROOT / "ble_app_uart_c/Src/external/cJSON-1.7.19"
    business = ROOT / "ble_app_uart_c/Src/user/business"
    ota = ROOT / "ble_app_uart_c/Src/user/ota"
    exe = OUT / "r6_resync_replay.exe"
    command = [str(gcc),"-std=c99","-Wall","-Wextra","-Werror","-DYP_BUSINESS_HOST_TEST",
               "-I"+str(business),"-I"+str(ota),"-I"+str(cjson),str(source),
               str(business/"yp001_business.c"),str(ota/"yp001_ota_wire.c"),str(cjson/"cJSON.c"),"-o",str(exe)]
    subprocess.run(command,check=True,env=env,capture_output=True,text=True)
    result = subprocess.run([str(exe)],check=True,env=env,capture_output=True,text=True)
    record = {"captured_events":events,"fixture_identity_redacted":True,
              "production_sources":[str(business/"yp001_business.c"),str(ota/"yp001_ota_wire.c")],
              "results":result.stdout.splitlines(),"device_access":False,
              "raw_capture_sha256":hashlib.sha256(raw).hexdigest(),
              "scope":"Replay assumes recorded UART loss enters existing quarantine before first recovery hello; it does not measure the original interrupt stall."}
    (OUT/"resync_replay.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
    print(json.dumps(record,indent=2))


if __name__ == "__main__":
    main()

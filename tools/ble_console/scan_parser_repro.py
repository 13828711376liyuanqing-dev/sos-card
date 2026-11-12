"""SAM | 2026-11-05 +08:00 | Execute current SDK parser functions on host to reproduce scan memory hazards; no board access."""
from pathlib import Path
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / 'SDK/components/libraries/ble/ble_scanner'
OUT = ROOT / 'logs/ble_scan_parser_repro'
OUT.mkdir(parents=True, exist_ok=True)
source = (SDK / 'ble_scanner.c').read_text(encoding='utf-8-sig')
header = (SDK / 'ble_scanner.h').read_text(encoding='utf-8-sig')

def function(name):
    start = source.index('static void ' + name + '(')
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

types = '\n'.join(re.findall(r'typedef struct\s*\{[^{}]*\}\s*(?:ble_data_t|ble_scanner_uuid_t|ble_scanner_adv_type_t|ble_scanner_single_rec_t|ble_scanner_parse_rec_t|ble_scanner_parse_report_t);', header))
defines = '\n'.join(line for line in header.splitlines() if re.match(r'#define (AD_TYPE_NUM_MAX|UUID_\w+)\s', line))
prefix = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
typedef int ble_gap_adv_report_type_t;
typedef struct { uint8_t addr_type; struct { uint8_t addr[6]; } gap_addr; } ble_gap_bdaddr_t;
typedef struct { int adv_type; int8_t rssi; ble_gap_bdaddr_t broadcaster_addr; uint8_t *data; uint16_t length; } ble_gap_evt_adv_report_t;
#define BLE_GAP_AD_TYPE_FLAGS 1
#define BLE_GAP_AD_TYPE_MORE_16_BIT_UUID 2
#define BLE_GAP_AD_TYPE_COMPLETE_LIST_16_BIT_UUID 3
#define BLE_GAP_AD_TYPE_MORE_32_BIT_UUID 4
#define BLE_GAP_AD_TYPE_COMPLETE_LIST_32_BIT_UUID 5
#define BLE_GAP_AD_TYPE_MORE_128_BIT_UUID 6
#define BLE_GAP_AD_TYPE_COMPLETE_LIST_128_BIT_UUID 7
#define BLE_GAP_AD_TYPE_SHORTENED_NAME 8
#define BLE_GAP_AD_TYPE_COMPLETE_NAME 9
#define BLE_GAP_AD_TYPE_APPEARANCE 0x19
#define BLE_GAP_AD_TYPE_MANU_SPECIFIC_DATA 0xff
'''
main = r'''
static int failures;
#define CHECK(ok, name) do { printf("%s %s\n", (ok)?"PASS":"FAIL",name); failures += !(ok); } while(0)
int main(void) {
    /* Oversized backing storage keeps reproduction deterministic after the array boundary. */
    union { max_align_t alignment; unsigned char bytes[4096]; } storage;
    memset(&storage,0,sizeof(storage));
    ble_scanner_parse_rec_t *records=(void*)storage.bytes;
    memset(storage.bytes+sizeof(*records),0xa5,64);
    for(unsigned i=0;i<AD_TYPE_NUM_MAX+1;i++) ble_scanner_parse_record(0xee,NULL,0,records);
    unsigned char expected[64];memset(expected,0xa5,sizeof(expected));
    CHECK(records->type_count<=AD_TYPE_NUM_MAX && !memcmp(storage.bytes+sizeof(*records),expected,64),"unknown_AD_record_capacity_and_canary");
    ble_scanner_uuid_t uuids={0};uint8_t uuid[]={1,2,3,4};
    ble_scanner_uuid_encode(uuid,4,UUID_32_BIT_BYTES,&uuids);
    CHECK(uuids.uuid_32_bit_count==1 && !memcmp(&uuids.uuid_32_bit[0],uuid,4) && uuids.uuid_16_bit[0]==0,"UUID32_destination_integrity");
    uint8_t truncated[]={5,BLE_GAP_AD_TYPE_COMPLETE_NAME,0,0,0,0};
    ble_gap_evt_adv_report_t report={0};report.data=truncated;report.length=2;
    ble_scanner_parse_report_t parsed;
    ble_scanner_data_parse(&report,&parsed);
    CHECK(!parsed.adv_type_parsed.local_name && parsed.local_name.length==0,"truncated_AD_must_not_publish_out_of_packet_slice");
    memset(&storage,0,sizeof(storage));
    ble_scanner_parse_report_t *many=(void*)storage.bytes;
    memset(storage.bytes+sizeof(*many),0xa5,64);
    uint8_t fields[22];for(unsigned i=0;i<sizeof(fields);i+=2){fields[i]=1;fields[i+1]=0xee;}
    report.data=fields;report.length=sizeof(fields);ble_scanner_data_parse(&report,many);
    CHECK(many->other_parse_rec.type_count<=AD_TYPE_NUM_MAX && !memcmp(storage.bytes+sizeof(*many),expected,64),"full_legacy_packet_11_unknown_fields_preserves_canary");
    memset(&uuids,0,sizeof(uuids));ble_scanner_uuid_encode(uuid,1,UUID_16_BIT_BYTES,&uuids);
    CHECK(uuids.uuid_16_bit_count==0,"partial_UUID_not_copied");
    uint8_t normal[]={2,1,6,6,9,'Y','P','0','0','1'};
    report.data=normal;report.length=sizeof(normal);
    ble_scanner_data_parse(&report,&parsed);
    CHECK(parsed.flag==6 && parsed.local_name.length==5 && !memcmp(parsed.local_name.p_data,"YP001",5),"valid_flags_and_name");
    return failures?1:0;
}
'''
unit = '#include <stddef.h>\n' + prefix + defines + '\n' + types
unit += '\nstatic struct { struct { ble_gap_bdaddr_t peer_addr; } conn_param; } s_scanner_env;\n'
unit += '\n'.join(function(name) for name in ['ble_scanner_uuid_encode', 'ble_scanner_parse_record', 'ble_scanner_data_parse']) + main
cfile = OUT / 'current_sdk_parser.c'
cfile.write_text(unit, encoding='utf-8')
gcc = Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ['PATH'])
exe = OUT / 'scan_parser_repro.exe'
subprocess.run([str(gcc), '-std=c11', '-Wall', '-Wextra', str(cfile), '-o', str(exe)], check=True, env=env)
result = subprocess.run([str(exe)], capture_output=True, text=True, env=env)
(OUT / 'result.txt').write_text(result.stdout + result.stderr + f'EXIT={result.returncode}\n', encoding='utf-8')
print(result.stdout, end='')
raise SystemExit(result.returncode)

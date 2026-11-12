"""SAM | 2026-11-06 +08:00 | Compile the actual protocol and bounded stream queue on the host."""
from pathlib import Path
import os
import subprocess

root = Path(__file__).resolve().parents[2]
out = root / 'logs/factory_serial_tests'
out.mkdir(exist_ok=True)
unit = r'''
#include <assert.h>
#include <stdlib.h>
#undef assert
#define assert(x) do { if (!(x)) { fprintf(stderr,"assert failed: %s at %d\n",#x,__LINE__);exit(1); } } while(0)
#include <stdio.h>
#include "yp001_factory_protocol.h"
#include "yp001_factory_stream.h"
int main(void) {
 ft_request_t r;
 assert(ft_parse("FT SHIP_START 1", &r) && r.op==FT_SHIP_START);
 assert(ft_cli_allowed("charger ship start") && !ft_cli_read_only("charger ship start"));
 assert(ft_parse("FT CAT_ON 1", &r) && r.op==FT_CAT_ON);
 assert(ft_parse("FT CAT_HOLD_ON 2", &r) && r.op==FT_CAT_HOLD_ON);
 assert(ft_parse("FT CAT_HOLD_OFF 3", &r) && r.op==FT_CAT_HOLD_OFF);
 assert(ft_parse("FT CLI 4 cat1_power hold_on", &r) && !strcmp(r.command,"cat1_power hold_on"));
 assert(!ft_parse("FT CLI 4 ", &r));
 assert(!ft_parse("FT INFO 1 extra", &r));
 assert(ft_cli_read_only("fw_version") && !ft_cli_read_only("fw_version verify"));
 assert(ft_cli_allowed("cat1_power on") && !ft_cli_allowed("name_store clear"));
 assert(!ft_cli_allowed("cat1_power on; name_store clear"));
 char line[1100]; memset(line,'x',sizeof(line)); memcpy(line,"FT CLI 1 ",9);
 line[9+1023]=0;assert(ft_parse(line,&r));line[9+1023]='x';line[9+1024]=0;assert(!ft_parse(line,&r));
 ft_stream_t q={0};uint8_t data[256],saved[64];memset(data,0xab,sizeof(data));
 assert(ft_stream_push(&q,data,256)==256);memset(data,1,sizeof(data));
 assert(ft_stream_pop(&q,saved,64)==64 && saved[0]==0xab);
 for(int i=0;i<40;i++)ft_stream_push(&q,data,256);
 assert(q.dropped>0);unsigned count=0,n;
 while((n=ft_stream_pop(&q,saved,64))!=0) {assert(n<=64);count+=n;}
 assert(count<=FT_STREAM_CAPACITY-1);
 ft_stream_reset(&q);assert(!q.dropped&&!ft_stream_pop(&q,saved,64));
 puts("PASS strict FT/CLI limits, command policy, deep copy, bounded overflow and reset");
}
'''
(out/'test.c').write_text(unit,encoding='utf-8')
gcc=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
subprocess.run([str(gcc),'-std=c11','-Wall','-Wextra','-I',str(root/'ble_app_uart_c/Src/user/factory'),str(out/'test.c'),'-o',str(out/'test.exe')],env=env,check=True)
subprocess.run([str(out/'test.exe')],env=env,check=True)

/* SAM | 2026-11-02 +08:00 | Host-test stub: only the IMEI length is used by yp001_business.c.
 * SAM | 2026-11-08 +08:00 | Colleague business.c also persists g_config / g_bind_msg and calls start_sos_process(bool). */
#pragma once
#include <stdbool.h>
#define IMEI_BUF_LEN 15
void start_sos_process(bool bStart);
typedef struct { char pad[512]; } ParaConfig_t;
typedef struct { int CmdType; char call_out[33]; char call_in[5][20]; } ParaBindMsg_t;
extern ParaConfig_t g_config;
extern ParaBindMsg_t g_bind_msg;

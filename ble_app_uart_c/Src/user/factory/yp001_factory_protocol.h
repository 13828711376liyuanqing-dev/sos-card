/* SAM | 2026-10-13 15:00 +08:00 | Strict factory request whitelist and
 * expiring physical-key permission because BLE is not a general CLI. */
#ifndef YP001_FACTORY_PROTOCOL_H
#define YP001_FACTORY_PROTOCOL_H
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
/* SAM | 2026-11-08 20:30 +08:00 | Append one-command shipping while preserving existing FT1 operation numbers and CLI bounds. */
#define FT_LINE_CAPACITY 1056U
typedef enum { FT_INFO, FT_UNLOCK, FT_PAGE, FT_CAT_OFF, FT_SHIP_PREP,
    FT_SHIP_STATUS, FT_SHIP_CONFIRM, FT_SHIP_CANCEL, FT_CAT_ON, FT_CAT_HOLD_ON, FT_CAT_HOLD_OFF, FT_CAT_STATUS, FT_SERIAL_ON, FT_SERIAL_OFF, FT_CLI, FT_SHIP_START } ft_op_t;
typedef struct { ft_op_t op; uint32_t seq, arg; const char *command; } ft_request_t;
static inline bool ft_number(const char **p,uint32_t *v) {
    uint32_t n=0; const char *s=*p;
    if (*s<'0'||*s>'9') return false;
    while (*s>='0'&&*s<='9') {
        uint32_t d=(uint32_t)(*s-'0');
        if (n>(0xffffffffU-d)/10U) return false;
        n=n*10U+d; ++s;
    }
    *v=n; *p=s; return true;
}
static inline const char *ft_name(ft_op_t op) {
    static const char *const names[]={"INFO","UNLOCK","PAGE","CAT_OFF","SHIP_PREP","SHIP_STATUS","SHIP_CONFIRM","SHIP_CANCEL","CAT_ON","CAT_HOLD_ON","CAT_HOLD_OFF","CAT_STATUS","SERIAL_ON","SERIAL_OFF","CLI","SHIP_START"};
    return names[op];
}
static inline bool ft_parse(const char *line,ft_request_t *r) {
    if (!line||!r||strlen(line)>=FT_LINE_CAPACITY||strncmp(line,"FT ",3)) return false;
    const char *p=line+3; unsigned op;
    for (op=0;op<=FT_SHIP_START;++op) {
        size_t n=strlen(ft_name((ft_op_t)op));
        if (!strncmp(p,ft_name((ft_op_t)op),n)&&p[n]==' ') { p+=n+1; break; }
    }
    if (op>FT_SHIP_START||!ft_number(&p,&r->seq)||!r->seq) return false;
    r->op=(ft_op_t)op; r->arg=0; r->command=NULL;
    if (op==FT_CLI) {
        if (*p++!=' '||!*p||strlen(p)>1023U) return false;
        r->command=p; return true;
    }
    if (strlen(line)>63U) return false;
    if (op==FT_PAGE||op==FT_SHIP_CONFIRM) {
        if (*p++!=' '||!ft_number(&p,&r->arg)) return false;
        if ((op==FT_PAGE&&r->arg>=6U)||(op==FT_SHIP_CONFIRM&&!r->arg)) return false;
    }
    return !*p;
}
static inline bool ft_lease_valid(bool granted,uint32_t since,uint32_t now) {
    return granted && (uint32_t)(now-since)<60000U;
}
/* SAM | 2026-11-06 +08:00 | Reviewed short maintenance commands exclude user-data erasure and long blocking diagnostics. */
static inline bool ft_cli_read_only(const char *s) {
    static const char *const queries[]={"help","fw_version","ble_status","cat1_power status","charger status","charger ship status","ota_storage","yp_motion","business status","log status","beacon_ctrl status","name_store status","epd_refresh status","sleep_test status"};
    for (unsigned i=0;i<sizeof(queries)/sizeof(queries[0]);++i) if (!strcmp(s,queries[i])) return true;
    return false;
}
static inline bool ft_cli_allowed(const char *s) {
    /* SAM | 2026-11-08 20:30 +08:00 | Single-command shipping keeps its hardware guards in GR. */
    static const char *const commands[]={"charger ship start","cat1_power on","cat1_power off","cat1_power key","cat1_power reset","cat1_power hold_on","cat1_power hold_off","charger ship prepare","charger ship cancel","log on","log off","beacon_ctrl on","beacon_ctrl off",
        /* SAM | 2026-11-12 +08:00 | Factory deep-sleep current test (user decision): forced entry, no key lease; CAT1/EPD rails off, G-sensor kept, 300 s rescue. */
        "sleep_test enter force"};
    if (ft_cli_read_only(s)) return true;
    for (unsigned i=0;i<sizeof(commands)/sizeof(commands[0]);++i) if (!strcmp(s,commands[i])) return true;
    const char *prefix="charger ship confirm ";size_t n=strlen(prefix);uint32_t token;
    if (strncmp(s,prefix,n)) return false;
    const char *p=s+n;
    return ft_number(&p,&token) && token && !*p;
}
#endif

/* SAM | 2026-10-27 +08:00 | Host-only bridge around the unchanged production GR coordinator/mux; Flash IO and operation duration are modeled, protocol state transitions are real. */
#define YP_TEST_EXTERNAL_QUIET 1
#define yp001_ota_port_reply fixture_reply
#define yp001_ota_port_poll fixture_port_poll
#define main historical_coordinator_suite
#include "test_gr_coordinator.c"
#undef main
#undef yp001_ota_port_reply
#undef yp001_ota_port_poll

static uint32_t replay_clock, operation_ms=15;
static unsigned operations, qread, qwrite;
static unsigned reset_polls,nested_attempts;
static bool nested_test;
static uint8_t queue_bytes[32][1100];
static size_t queue_lengths[32];
static yp001_ota_mux replay_mux;

uint32_t yp001_uart_clock_ms(void){return replay_clock;}
int yp001_ota_random(uint8_t out[16]){memset(out,0x35,16);return 0;}
void yp001_ota_measure_begin(uint32_t kind,uint32_t token){assert(kind&&token);}
void yp001_ota_measure_end(void){}
bool yp001_ota_port_retire(const yp001_ota_record*r){(void)r;return false;}
void yp001_ota_port_wire(const uint8_t*p,size_t n){
    (void)p;(void)n;assert(yp001_ota_flash_allowed());
    ++operations;replay_clock+=operation_ms;
    if(nested_test){++nested_attempts;yp001_ota_service_pending();assert(yp001_ota_flash_allowed());}
}
void yp001_ota_port_poll(void){++reset_polls;fixture_port_poll();}
void yp001_ota_port_reply(const char*s,size_t n){
    assert(qwrite-qread<32&&n<=1100);
    fixture_reply(s,n);memcpy(queue_bytes[qwrite%32],s,n);queue_lengths[qwrite%32]=n;++qwrite;
}

/* SAM | 2026-10-27 +08:00 | Including the production C file exposes its static quiet state to this host-only DLL; it is never part of a Keil firmware input. */
#include "../../ble_app_uart_c/Src/user/ota/yp001_ota.c"

static void rx_frame(const uint8_t*p,size_t n,void*ctx){(void)ctx;yp001_ota_dispatch_wire(p,n);}
static void rx_text(const uint8_t*p,size_t n,void*ctx){(void)p;(void)n;(void)ctx;}
#define API __declspec(dllexport)
API void BR_reset(void){
    replay_clock=0;operations=qread=qwrite=0;operation_ms=15;
    reset_polls=nested_attempts=0;nested_test=false;
    memset(&nv,0,sizeof nv);load_result=0;store_ok=true;
    gates=(yp001_ota_gates){true,true,true,false,false,false,true,70};
    memset(&replay_mux,0,sizeof replay_mux);yp001_ota_init();
    memset((void*)g_ota_quiet_trace,0,sizeof g_ota_quiet_trace);
    memset((void*)g_ota_quiet_first_timeout,0,sizeof g_ota_quiet_first_timeout);
}
API void BR_time(uint32_t at){replay_clock=at;}
API uint32_t BR_now(void){return replay_clock;}
API uint32_t BR_phase(void){return quiet.phase;}
API uint32_t BR_token(void){return quiet.token;}
API uint32_t BR_operations(void){return operations;}
API uint32_t BR_reset_polls(void){return reset_polls;}
API uint32_t BR_nested_attempts(void){return nested_attempts;}
API void BR_nested(uint32_t enabled){nested_test=enabled!=0;}
API void BR_operation_ms(uint32_t ms){operation_ms=ms;}
API void BR_alarm(uint32_t enabled){gates.alarm=enabled!=0;}
API void BR_poll(void){yp001_ota_poll();}
API void BR_pending(void){yp001_ota_service_pending();}
API void BR_feed(const uint8_t*data,uint32_t n){
    uint32_t i;for(i=0;i<n;i++)yp001_ota_mux_feed(&replay_mux,data[i],replay_clock,rx_text,rx_frame,0);
}
API uint32_t BR_pop(uint8_t*out,uint32_t cap){
    size_t n;if(qread==qwrite)return 0;n=queue_lengths[qread%32];assert(n<=cap);
    memcpy(out,queue_bytes[qread%32],n);++qread;return (uint32_t)n;
}
#ifdef REPLAY_STANDALONE
/* SAM | 2026-10-27 +08:00 | Installed MinGW is 32-bit; an isolated line protocol avoids loading a 32-bit DLL into the 64-bit Python runtime. */
int main(void){
    char line[4096];uint8_t data[1100];unsigned value,n,i;
    while(fgets(line,sizeof line,stdin)){
        line[strcspn(line,"\r\n")]=0;
        if(!strcmp(line,"reset")){BR_reset();puts("ok");}
        else if(sscanf(line,"time %u",&value)==1){BR_time(value);puts("ok");}
        else if(sscanf(line,"operation %u",&value)==1){BR_operation_ms(value);puts("ok");}
        else if(sscanf(line,"alarm %u",&value)==1){BR_alarm(value);puts("ok");}
        else if(sscanf(line,"nested %u",&value)==1){BR_nested(value);puts("ok");}
        else if(!strcmp(line,"poll")){BR_poll();puts("ok");}
        else if(!strcmp(line,"pending")){BR_pending();puts("ok");}
        else if(!strcmp(line,"state"))printf("{\"now\":%u,\"phase\":%u,\"token\":%u,\"operations\":%u,\"reset_polls\":%u,\"nested_attempts\":%u}\n",BR_now(),BR_phase(),BR_token(),BR_operations(),BR_reset_polls(),BR_nested_attempts());
        else if(!strcmp(line,"trace")){
            printf("{\"live\":[");for(i=0;i<16;i++)printf("%s%u",i?",":"",(unsigned)g_ota_quiet_trace[i]);
            printf("],\"first\":[");for(i=0;i<16;i++)printf("%s%u",i?",":"",(unsigned)g_ota_quiet_first_timeout[i]);puts("]}");
        }
        else if(!strncmp(line,"feed ",5)){
            n=(unsigned)strlen(line+5);assert(!(n%2)&&n/2<=sizeof data);
            for(i=0;i<n/2;i++){assert(sscanf(line+5+i*2,"%2x",&value)==1);data[i]=(uint8_t)value;}
            BR_feed(data,n/2);puts("ok");
        }else if(!strcmp(line,"pop")){
            n=BR_pop(data,sizeof data);for(i=0;i<n;i++)printf("%02x",data[i]);putchar('\n');
        }else {puts("bad_command");return 2;}
        fflush(stdout);
    }
    return 0;
}
#endif

/* SAM | 2026-10-12 19:23 +08:00 | Fail closed because flash layout, signed packages and business gates are unvalidated. */
#include "yp001_ota_port.h"
#include <string.h>
#include <stddef.h>
#include "hal_flash.h"
#include "gr_soc.h"
#include "yp001_fw_version.h"
#include "yp001_ota_layout.h"
#include "yp001_ota_receive.h"
#include "yp001_ota_app_crypto.h"
#include "yp001_ota_trust.h"
#include <stdio.h>
#include "../yp001_psram_mem.h"
#include "app_aon_wdt.h"
#include "yp001_ota_wire.h"
#include "yp001_ota_retirement.h"
#include "../business/yp001_business.h"
#include "../charger/yp001_charger.h"
/* SAM | 2026-11-07 07:14 +08:00 | Read physical USB status for the user-approved alternative; never enable charging or trust a remote flag. */
bool yp001_ota_port_usb_power(void)
{
    yp001_charger_status_t charge;
    return yp001_charger_display_status(&charge) && yp001_charger_live_input(&charge) &&
        yp001_ota_usb_supply(charge.input_present, charge.power_good,
                            charge.thermal_limit, charge.fault, charge.power_raw);
}
extern void yp001_ota_uart_reply(const char *line, size_t length);
/* SAM | 2026-10-23 +08:00 | Dedicated coordinator pages only. This provisions
 * metadata, NOT B-slot writes or Boot installation. Unknown page contents reject. */
#define OTA_PAGE0 0x002F9000u
#define OTA_PAGE1 0x002FA000u
#define OTA_PAGE_SIZE 4096u
/* SAM | 2026-10-23 +08:00 | Bit31 persists B ownership across jobs; lower bits retain bounded native extent. */
#define OTA_B_OWNED 0x80000000u
#define OTA_RECORD_MAGIC_V1 0x594F5431u
#define OTA_RECORD_MAGIC 0x594F5432u
/* SAM | 2026-10-23 +08:00 | Versioned progress extension preserves readable V1 records without erasing them during load. */
typedef struct {
    uint32_t magic, generation;
    yp001_ota_record record;
    uint32_t crc, commit;
} ota_page_v1;
typedef struct {
    uint32_t magic, generation;
    yp001_ota_record record;
    uint32_t transfer_total, transfer_durable;
    uint32_t crc, commit;
} ota_page_record;
/* SAM | 2026-10-27 +08:00 | Volatile, single-command receipt binds actual signed A/B, durable owner/progress and Boot generation. Never restored from Flash or shared across commands. */
static struct {
    /* SAM | 2026-11-07 09:13 +08:00 | Post-swap receipts acknowledge the running target only; they cannot authorize another install. */
    bool installed;
    unsigned stage;
    uint32_t owner_generation,total,b_generation,boot_generation;
    yp001_ota_record owner;
    yp_boot_image old_image,new_image;
} install_check;
static uint32_t b_generation;
/* SAM | 2026-11-06 +08:00 | Keep the current command failure stage visible after receipt revocation. */
static unsigned install_check_last_stage;
static bool install_backend_check;
/* SAM | 2026-10-27 +08:00 | Postboot identity has a separate purpose and is never inherited from pre-install validation. A is immutable to this application; owner/Boot changes revoke this RAM-only receipt. */
static struct {
    bool valid;
    uint32_t boot_generation,boot_state;
    yp001_ota_record owner;
    yp_boot_image actual,old_image,new_image;
} health_check;
static bool health_backend_check;
static bool install_fail(unsigned stage,const yp001_ota_record *record,const yp_boot *boot,uint32_t mask);
void yp001_ota_port_install_check_reset(void)
{
    memset(&install_check,0,sizeof install_check);install_backend_check=false;install_check_last_stage=0;
}
static uint32_t record_crc(const void *data, size_t length)
{
    const uint8_t *p = data;
    uint32_t c = ~0u, i;
    while (length--) {
        c ^= *p++;
        for (i = 0; i < 8; ++i) c = (c >> 1) ^ ((0u - (c & 1u)) & 0xEDB88320u);
    }
    return ~c;
}
bool yp001_ota_port_provisioned(void)
{
    uint32_t id = 0, size = 0;
    hal_flash_get_info(&id, &size);
    return id != 0 && size == 0x100000u && hal_flash_sector_size() == OTA_PAGE_SIZE &&
           nvds_get_start_addr() == 0x002FE000u;
}
/* 0 erased, 1 committed, 2 complete body without commit, -1 unreadable/unknown. */
static int read_page(uint32_t address, ota_page_record *record)
{
    uint8_t bytes[64];
    uint32_t offset, i, n;
    bool empty = true, tail_empty = true;
    memset(record, 0, sizeof(*record));
    for (offset = 0; offset < OTA_PAGE_SIZE; offset += n) {
        n = OTA_PAGE_SIZE - offset;
        if (n > sizeof(bytes)) n = sizeof(bytes);
        if (hal_flash_read(address + offset, bytes, n) != n) return -1;
        for (i = 0; i < n; ++i) {
            if (bytes[i] != 255u) {
                empty = false;
                if (offset + i >= sizeof(*record)) tail_empty = false;
            }
            if (offset + i < sizeof(*record)) ((uint8_t *)record)[offset + i] = bytes[i];
        }
    }
    if (empty) return 0;
    if (tail_empty && record->magic == OTA_RECORD_MAGIC_V1) {
        ota_page_v1 old;
        memcpy(&old, record, sizeof(old));
        for (i=sizeof(old); i<sizeof(*record); ++i)
            if (((uint8_t *)record)[i]!=255u) return -1;
        if (!old.generation || old.crc!=record_crc(&old,offsetof(ota_page_v1,crc))) return -1;
        memset(record,0,sizeof(*record));
        record->magic=OTA_RECORD_MAGIC;record->generation=old.generation;
        record->record=old.record;record->commit=old.commit;
        record->crc=record_crc(record,offsetof(ota_page_record,crc));
    }
    if (!tail_empty || record->magic != OTA_RECORD_MAGIC || !record->generation ||
        record->crc != record_crc(record, offsetof(ota_page_record, crc))) return -1;
    if (record->commit == 0u) return 1;
    return record->commit == UINT32_MAX ? 2 : -1;
}
static int latest(ota_page_record pages[2], int *selected)
{
    int a, b;
    if (!yp001_ota_port_provisioned()) return -1;
    a = read_page(OTA_PAGE0, &pages[0]); b = read_page(OTA_PAGE1, &pages[1]);
    if (a < 0 || b < 0) return -1;
    if (a == 0 && b == 0) { *selected = -1; return 0; }
    if (a != 1 && b != 1) return -1;
    if (a == 1 && b == 1) {
        if (pages[0].generation == pages[1].generation &&
            memcmp(&pages[0], &pages[1], sizeof(pages[0]))) return -1;
        *selected = pages[0].generation >= pages[1].generation ? 0 : 1;
    } else *selected = a == 1 ? 0 : 1;
    if ((a == 2 && (pages[1].generation == UINT32_MAX || pages[0].generation != pages[1].generation + 1u)) ||
        (b == 2 && (pages[0].generation == UINT32_MAX || pages[1].generation != pages[0].generation + 1u))) return -1;
    return 1;
}
int yp001_ota_port_load(yp001_ota_record *record)
{
    ota_page_record pages[2];
    int selected = -1, result;
    if (!record) return -1;
    result = latest(pages, &selected);
    if (result == 1) *record = pages[selected].record;
    else if (result == 0) memset(record, 0, sizeof(*record));
    return result;
}
static bool same_owner(const yp001_ota_record *a,const yp001_ota_record *b)
{
    return a->epoch==b->epoch && !memcmp(a->job,b->job,sizeof(a->job)) &&
        !memcmp(a->hash,b->hash,sizeof(a->hash)) && !memcmp(a->target,b->target,sizeof(a->target)) &&
        !memcmp(a->version,b->version,sizeof(a->version));
}
/* SAM | 2026-10-23 +08:00 | Claiming B is itself guarded at the persistent API boundary, not trusted to a caller's assertion. */
static bool certify_b_empty(void)
{
    uint8_t bytes[64];uint32_t address,i;
    for(address=YP_OTA_B;address<YP_OTA_B+YP_OTA_SLOT_BYTES;address+=sizeof(bytes)){
        if(app_aon_wdt_refresh()!=APP_DRV_SUCCESS || hal_flash_read(address,bytes,sizeof(bytes))!=sizeof(bytes))return false;
        for(i=0;i<sizeof(bytes);i++)if(bytes[i]!=255u)return false;
    }
    return true;
}
static bool store_record(const yp001_ota_record *record, bool progress, uint32_t total,uint32_t durable)
{
    ota_page_record pages[2], next, check;
    int selected = -1, result;
    uint32_t address, zero = 0, prior_total;
    /* SAM | 2026-10-25 +08:00 | Journal mutation requires the peer silence grant. */
    if (!record || !yp001_ota_flash_allowed()) return false;
    result = latest(pages, &selected);
    if (result < 0 || (result == 1 && pages[selected].generation == UINT32_MAX)) return false;
    memset(&next, 0, sizeof(next));
    next.magic = OTA_RECORD_MAGIC;
    next.generation = result == 0 ? 1u : pages[selected].generation + 1u;
    next.record = *record;
    if(result==1)next.transfer_total=pages[selected].transfer_total&OTA_B_OWNED;
    if (result==1 && same_owner(record,&pages[selected].record)) {
        next.transfer_total=pages[selected].transfer_total;
        next.transfer_durable=pages[selected].transfer_durable;
    }
    if (progress) {
        if (result!=1 || !same_owner(record,&pages[selected].record) ||
            record->phase!=OTA_DOWNLOADING || pages[selected].record.phase!=OTA_DOWNLOADING ||
            strcmp(record->target,"GR5526") || total<8u+YP_OTA_SIGNATURE_BYTES || total>YP_OTA_SLOT_BYTES ||
            durable>total || (durable!=total && durable%OTA_PAGE_SIZE)) return false;
        if(!(next.transfer_total&OTA_B_OWNED)&&!certify_b_empty())return false;
        prior_total=next.transfer_total&~OTA_B_OWNED;
        if (!prior_total) { if(durable) return false; }
        else if (prior_total!=total || durable<next.transfer_durable ||
                 durable-next.transfer_durable>OTA_PAGE_SIZE) return false;
        if (prior_total==total && next.transfer_durable==durable && (next.transfer_total&OTA_B_OWNED)) return true;
        next.transfer_total=total|OTA_B_OWNED;next.transfer_durable=durable;
    }
    next.crc = record_crc(&next, offsetof(ota_page_record, crc));
    next.commit = UINT32_MAX;
    address = selected == 0 ? OTA_PAGE1 : OTA_PAGE0;
    /* SAM | 2026-10-27 +08:00 | Only this command's PREPARED-to-PENDING owner transition may retain its read-only receipt. All other attempted journal changes revoke it before IO. */
    if(install_check.stage&&!(result==1&&selected>=0&&install_check.owner_generation==pages[selected].generation&&
       !memcmp(&install_check.owner,&pages[selected].record,sizeof(record[0]))&&
       record->phase==OTA_INSTALL_PENDING&&pages[selected].record.phase==OTA_PREPARED))
        yp001_ota_port_install_check_reset();
    if(install_check.stage){
        yp001_ota_record expected=install_check.owner;expected.phase=OTA_INSTALL_PENDING;
        if(memcmp(&expected,record,sizeof expected))yp001_ota_port_install_check_reset();
    }
    health_check.valid=false;
    if (!hal_flash_erase(address, OTA_PAGE_SIZE) || read_page(address, &check) != 0 ||
        hal_flash_write(address, (const uint8_t *)&next, offsetof(ota_page_record, commit)) != offsetof(ota_page_record, commit) ||
        read_page(address, &check) != 2 || memcmp(&next, &check, sizeof(next))) {yp001_ota_port_install_check_reset();return false;}
    if (hal_flash_write(address + offsetof(ota_page_record, commit), (const uint8_t *)&zero, sizeof(zero)) != sizeof(zero)) {yp001_ota_port_install_check_reset();return false;}
    next.commit = 0;
    if(read_page(address,&check)!=1||memcmp(&next,&check,sizeof next)){yp001_ota_port_install_check_reset();return false;}
    if(install_check.stage){install_check.owner=next.record;install_check.owner_generation=next.generation;}
    return true;
}
bool yp001_ota_port_store(const yp001_ota_record *record)
{
    return store_record(record,false,0,0);
}
bool yp001_ota_port_progress_store(const yp001_ota_record *owner,uint32_t total,uint32_t durable)
{
    return store_record(owner,true,total,durable);
}
bool yp001_ota_port_progress_load(const yp001_ota_record *owner,uint32_t *total,uint32_t *durable)
{
    ota_page_record pages[2];int selected=-1;
    if(!owner||!total||!durable||latest(pages,&selected)!=1||!same_owner(owner,&pages[selected].record)) return false;
    *total=pages[selected].transfer_total&~OTA_B_OWNED;*durable=pages[selected].transfer_durable;
    if (!*total) return *durable==0;
    return *total>=8u+YP_OTA_SIGNATURE_BYTES && *total<=YP_OTA_SLOT_BYTES && *durable<=*total &&
        (*durable==*total || *durable%OTA_PAGE_SIZE==0);
}
/* SAM | 2026-11-07 +08:00 | OTA ignores control activity while measured power and actual alarm/call/link state retain independent safety gates. */
void yp001_ota_port_gates(yp001_ota_gates *gates)
{
    const yp_business_status_t *s=yp_business_status();yp_business_ota_inputs_t inputs;
    /* SAM | 2026-11-07 07:14 +08:00 | USB proof comes from a fresh charger read, not the displayed battery or charging flag. */
    memset(gates,0,sizeof(*gates));yp_business_ota_inputs_with_usb(&inputs,yp001_ota_port_usb_power());
    gates->known=inputs.known&&s->call!=YP_CALL_UNKNOWN;
    gates->stable=inputs.stable;gates->activity=inputs.activity;
    gates->alarm=s->alarm_active;gates->charging=s->charging;gates->battery=s->battery_known?s->battery_percent:255U;
    gates->call=s->call==YP_CALL_DIALING||s->call==YP_CALL_INCOMING||s->call==YP_CALL_CONNECTED||s->call==YP_CALL_UNKNOWN;
    gates->peer_stable=s->transport_ready&&s->network==YP_NET_MQTT;
}
/* SAM | 2026-10-23 20:18 +08:00 | Use fresh measured CAT hello for CAT tasks; never substitute GR's compiled version after GR upgrades first. */
bool yp001_ota_port_source_version(const yp001_ota_record *record, char *version, size_t capacity)
{
    if (!record || !version) return false;
    if(!strcmp(record->target,"CAT1"))return yp_business_cat_version(version,capacity);
    if(strcmp(record->target,"GR5526") || capacity < sizeof(YP001_PRODUCT_VERSION)) return false;
    memcpy(version, YP001_PRODUCT_VERSION, sizeof(YP001_PRODUCT_VERSION));
    return true;
}
/* SAM | 2026-10-23 +08:00 | Recheck physical signed B against owner and progress, including immediately before commit. */
static uint32_t version_number(const char *s)
{
    uint32_t parts[3]={0},v=0;unsigned i=0,digits=0;
    if(!s)return 0;
    while(*s){
        if(*s>='0'&&*s<='9'){v=v*10u+(unsigned)(*s-'0');if(v>999u||++digits>3u)return 0;}
        else if(*s=='.'&&digits&&i<2u){parts[i++]=v;v=0;digits=0;}
        else return 0;
        ++s;
    }
    if(!digits||i<1u)return 0;
    parts[i]=v;
    return parts[0]*1000000u+parts[1]*1000u+parts[2];
}
static bool hash_bytes(const char *s,uint8_t out[32])
{
    unsigned i;if(!s||!memchr(s,0,65)||strlen(s)!=64)return false;
    for(i=0;i<32;i++){
        unsigned a=(unsigned char)s[i*2],b=(unsigned char)s[i*2+1];
        a=(a>='0'&&a<='9')?a-'0':(a>='a'&&a<='f')?a-'a'+10u:(a>='A'&&a<='F')?a-'A'+10u:16u;
        b=(b>='0'&&b<='9')?b-'0':(b>='a'&&b<='f')?b-'a'+10u:(b>='A'&&b<='F')?b-'A'+10u:16u;
        if(a>15u||b>15u)return false;
        out[i]=(uint8_t)((a<<4)|b);
    }
    return true;
}
static bool verified_candidate(const yp001_ota_record *record,yp_boot_image *image)
{
    uint32_t total,durable,version;uint8_t hash[32];
    if(!record||strcmp(record->target,"GR5526")||!hash_bytes(record->hash,hash)||
       !yp001_ota_port_progress_load(record,&total,&durable)||!total||durable!=total)return false;
    version=version_number(record->version);
    return version && !yp001_ota_native_verify(YP_OTA_B,total,hash,version,image);
}
/* SAM | 2026-10-23 22:30 +08:00 | Keep the 904-byte proof in aligned RAM. Durable owner is rechecked per chunk; reboot requires a new proof, never erases user/B data. */
static uint32_t cat_proof_words[226],cat_proof_used;
static yp001_ota_record cat_proof_owner;
/* SAM | 2026-10-23 +08:00 | Completion observations are volatile; only existing coordinator pages persist the final released result. */
static char cat_nonce[33];static yp001_ota_record cat_result_owner;
static uint32_t cat_nonce_at,cat_first_seen,cat_last_seen;static bool cat_observed;
void yp001_ota_port_cat_proof_reset(void){cat_proof_used=0;memset(&cat_proof_owner,0,sizeof cat_proof_owner);cat_nonce[0]=0;cat_observed=false;health_check.valid=false;health_backend_check=false;}
bool yp001_ota_port_cat_proof_present(const yp001_ota_record*r){return r&&cat_proof_used==904&&same_owner(r,&cat_proof_owner);}
bool yp001_ota_port_cat_proof(const yp001_ota_record*r,uint32_t offset,const uint8_t*bytes,uint32_t n,uint32_t*next)
{
    yp001_ota_record current;uint8_t hash[32];uint8_t*proof=(uint8_t*)cat_proof_words;
    if(!r||!bytes||!next||strcmp(r->target,"CAT1")||n==0||n>256||offset>904||n>904-offset||
       yp001_ota_port_load(&current)!=1||!same_owner(r,&current)||
       (current.phase!=OTA_DOWNLOADING&&current.phase!=OTA_PREPARED&&current.phase!=OTA_INSTALL_PENDING))return false;
    if(!same_owner(r,&cat_proof_owner)){if(offset)return false;cat_proof_used=0;cat_proof_owner=*r;}
    if(offset<cat_proof_used){
        if(n>cat_proof_used-offset||memcmp(proof+offset,bytes,n))return false;
    }else{
        if(offset!=cat_proof_used)return false;
        memcpy(proof+offset,bytes,n);cat_proof_used+=n;
    }
    if(cat_proof_used==904&&(!hash_bytes(r->hash,hash)||
       yp001_ota_cat_proof_verify(proof,hash,version_number(r->version)))){cat_proof_used=0;return false;}
    *next=offset+n;return true;
}
bool yp001_ota_port_package_ready(const yp001_ota_record *record)
{
    yp_boot_image image;uint8_t hash[32];
    if(record&&!strcmp(record->target,"CAT1"))return cat_proof_used==904&&same_owner(record,&cat_proof_owner)&&
        hash_bytes(record->hash,hash)&&!yp001_ota_cat_proof_verify((const uint8_t*)cat_proof_words,hash,version_number(record->version));
    /* SAM | 2026-10-27 +08:00 | Reuse only this outstanding activation's exact verified native span, never a generic package-ready flag. */
    return yp001_ota_port_install_check_ready(record)||verified_candidate(record,&image);
}
/* SAM | 2026-10-23 19:26 +08:00 | Application writes ONLY Boot journals. Sector swapping is exclusively executed by the independently routed Boot after reset. */
static const yp_boot_layout boot_layout={0x100000u,4096u,0x2000u,0x80000u,YP_OTA_SLOT_BYTES,0xf6000u,{0xf7000u,0xf8000u},0xfe000u,0x2000u};
static uint32_t boot_work[1024];
static bool boot_reset_armed;
static uint32_t boot_reset_at,health_since;
static bool health_started;
static uint32_t result_check_at;
static bool result_check_started;
extern void hal_nvic_system_reset(void);
static int within(uint32_t a,uint32_t n,uint32_t s,uint32_t size)
{ return n&&a>=s&&a-s<size&&n<=size-(a-s); }
static int journal_area(uint32_t a,uint32_t n)
{ return within(a,n,0xf7000u,4096u)||within(a,n,0xf8000u,4096u); }
static int boot_read(void *ctx,uint32_t a,void *p,uint32_t n)
{
    (void)ctx;
    if(!p||(!journal_area(a,n)&&!within(a,n,0x2000u,YP_OTA_SLOT_BYTES)&&!within(a,n,0x80000u,YP_OTA_SLOT_BYTES))||
       app_aon_wdt_refresh()!=APP_DRV_SUCCESS)return -1;
    return hal_flash_read(0x200000u+a,p,n)==n?0:-1;
}
static int boot_write(void *ctx,uint32_t a,const void *p,uint32_t n)
{
    (void)ctx;if(!yp001_ota_flash_allowed()||!p||!journal_area(a,n)||app_aon_wdt_refresh()!=APP_DRV_SUCCESS)return -1;
    return hal_flash_write(0x200000u+a,p,n)==n?0:-1;
}
static int boot_erase(void *ctx,uint32_t a,uint32_t n)
{
    uint8_t check[64];uint32_t at,i;(void)ctx;
    if(!yp001_ota_flash_allowed()||n!=4096u||a%4096u||!journal_area(a,n)||app_aon_wdt_refresh()!=APP_DRV_SUCCESS||!hal_flash_erase(0x200000u+a,n))return -1;
    for(at=0;at<n;at+=sizeof(check)){
        if(boot_read(0,a+at,check,sizeof(check)))return -1;
        for(i=0;i<sizeof(check);i++)if(check[i]!=255u)return -1;
    }
    return 0;
}
static int boot_auth(void *ctx,uint32_t a,const yp_boot_image *image)
{
    /* SAM | 2026-10-27 +08:00 | Confirm consumes only the executing A identity authenticated in this boot, never the pre-install B receipt. Caller has just rechecked durable Boot generation and health. */
    if(health_backend_check){
        yp001_ota_record owner;
        return health_check.valid&&a==boot_layout.a&&image&&
            !memcmp(image,&health_check.actual,sizeof(*image))&&yp001_ota_port_load(&owner)==1&&
            !memcmp(&owner,&health_check.owner,sizeof owner)?0:-1;
    }
    /* SAM | 2026-10-27 +08:00 | Boot core still calls its mandatory authenticator; only the application short-commit backend may consume this exact command's real A/B validation receipt. Independent Boot keeps its own native authenticator. */
    if(install_backend_check){
        const yp_boot_image *expected=a==boot_layout.a?&install_check.old_image:a==boot_layout.b?&install_check.new_image:NULL;
        return expected&&image&&yp001_ota_port_install_check_ready(&install_check.owner)&&!memcmp(expected,image,sizeof(*image))?0:-1;
    }
    return yp001_ota_image_auth(ctx,0x200000u+a,image);
}
/* The SDK104 SCA BootInfo starts with size/checksum/load/run. Also require the
 * physical Boot's approved provision prefix and identical public contract pins.
 * Merely compiling Boot or changing an application flag cannot satisfy this. */
static bool boot_routed(void)
{
    uint32_t info[6],at;struct {uint32_t layout,inventory,baseline;uint8_t pins[96];} provision;
    if(!yp001_ota_port_provisioned()||hal_flash_read(0x200000u,(uint8_t*)info,sizeof(info))!=sizeof(info)||
       info[2]!=0x2ec000u||info[3]!=0x2ec000u||info[0]<sizeof(provision)||info[0]>0xa000u)return false;
    for(at=0;at<=info[0]-sizeof(provision);at+=4u){
        if(app_aon_wdt_refresh()!=APP_DRV_SUCCESS||hal_flash_read(0x2ec000u+at,(uint8_t*)&provision,sizeof(provision))!=sizeof(provision))return false;
        if(provision.layout==1u&&provision.inventory==1u&&provision.baseline==1u&&
           !memcmp(provision.pins,yp_ota_layout_pin,32)&&!memcmp(provision.pins+32,yp_ota_data_pin,32)&&
           !memcmp(provision.pins+64,yp_ota_public_pin,32))return true;
    }
    return false;
}
static bool boot_open(yp_boot *boot)
{
    yp_boot_backend io={0,boot_read,boot_write,boot_erase,boot_auth};uint32_t slot,at,i;uint8_t bytes[64];
    if(!boot_routed()||yp_boot_open(boot,&boot_layout,&io,boot_work,sizeof(boot_work)))return false;
    if(boot->state==YP_BOOT_EMPTY){
        for(slot=0;slot<2;slot++)for(at=0;at<4096;at+=sizeof(bytes)){
            if(boot_read(0,boot_layout.journal[slot]+at,bytes,sizeof(bytes)))return false;
            for(i=0;i<sizeof(bytes);i++)if(bytes[i]!=255u)return false;
        }
    }
    return true;
}
static bool durable_owner(const yp001_ota_record *record,yp001_ota_phase phase)
{
    yp001_ota_record owner;
    return record&&!strcmp(record->target,"GR5526")&&record->phase==phase&&
        yp001_ota_port_load(&owner)==1&&owner.phase==phase&&same_owner(record,&owner);
}
/* SAM | 2026-10-27 +08:00 | Let a valid, not-yet-activated GR intent regain peer power/status without allowing off/key/reset or authorizing installation. No image writes or crypto in this admission check. */
bool yp001_ota_port_recovery_prepared(const yp001_ota_record *record)
{
    yp_boot boot;
    return !boot_reset_armed&&durable_owner(record,OTA_INSTALL_PENDING)&&boot_open(&boot)&&
        boot.state==YP_BOOT_PREPARED&&!boot.index&&!boot.stage&&!boot.attempts&&
        boot.old_image.version==version_number(record->source_version)&&
        boot.old_image.version==version_number(YP001_PRODUCT_VERSION)&&
        boot.new_image.version==version_number(record->version);
}
/* SAM | 2026-10-27 +08:00 | Check owner/progress without crypto or Flash mutation. B writes and every unrelated owner mutation revoke the command receipt. */
static bool install_owner_current(const yp001_ota_record *record)
{
    ota_page_record pages[2];int selected=-1;
    return record&&install_check.stage&&b_generation==install_check.b_generation&&
        !memcmp(record,&install_check.owner,sizeof(*record))&&latest(pages,&selected)==1&&
        pages[selected].generation==install_check.owner_generation&&
        !memcmp(record,&pages[selected].record,sizeof(*record))&&
        (pages[selected].transfer_total&~OTA_B_OWNED)==install_check.total&&
        pages[selected].transfer_durable==install_check.total;
}
bool yp001_ota_port_install_check_ready(const yp001_ota_record *record)
{
    return install_check.stage==3&&install_owner_current(record);
}
/* SAM | 2026-11-06 +08:00 | Diagnostic reads never refresh samples or authorize installation. */
void yp001_ota_port_activation_evidence(uint32_t out[6])
{
    if(!out)return;
    yp_business_ota_evidence(out);out[5]=install_check_last_stage?install_check_last_stage:install_check.stage;
}
/* SAM | 2026-11-06 +08:00 | Preserve both immutable first-error evidence and this command stage after revoking its volatile receipt. */
static int install_check_fail(unsigned stage,const yp001_ota_record *record,const yp_boot *boot)
{
    (void)install_fail(stage,record,boot,0);yp001_ota_port_install_check_reset();install_check_last_stage=stage;return -1;
}
int yp001_ota_port_install_check_step(const yp001_ota_record *record)
{
    ota_page_record pages[2];int selected=-1;yp_boot boot;
    if(yp001_ota_flash_allowed())return install_check_fail(14,record,NULL);
    if(!install_check.stage){
        if(!record||strcmp(record->target,"GR5526")||
           (record->phase!=OTA_PREPARED&&record->phase!=OTA_INSTALL_PENDING)||
           latest(pages,&selected)!=1||memcmp(record,&pages[selected].record,sizeof(*record))||
           !pages[selected].transfer_durable||pages[selected].transfer_durable!=(pages[selected].transfer_total&~OTA_B_OWNED)||
           !boot_open(&boot))return install_check_fail(10,record,NULL);
        install_check.owner=*record;install_check.owner_generation=pages[selected].generation;
        install_check.total=pages[selected].transfer_durable;install_check.b_generation=b_generation;
        install_check.boot_generation=boot.generation;install_check.stage=1;
        /* SAM | 2026-11-07 09:13 +08:00 | After swap A is the target and B is the rollback image; authenticate the executing target against Boot before acknowledging a replay. */
        install_check.installed=record->phase==OTA_INSTALL_PENDING&&
            (boot.state==YP_BOOT_TRIAL||boot.state==YP_BOOT_CONFIRMED);
        if(install_check.installed){
            install_check.old_image=boot.old_image;
            if(boot.old_image.version!=version_number(record->source_version)||
               boot.new_image.version!=version_number(record->version)||
               yp001_ota_running_image(version_number(YP001_PRODUCT_VERSION),&install_check.new_image)||
               memcmp(&install_check.new_image,&boot.new_image,sizeof(boot.new_image)))return install_check_fail(11,record,&boot);
        }else if(yp001_ota_running_image(version_number(YP001_PRODUCT_VERSION),&install_check.old_image)||
                 install_check.old_image.version!=version_number(record->source_version))return install_check_fail(11,record,&boot);
        return 0;
    }
    if(!install_owner_current(record))return install_check_fail(13,record,NULL);
    if(!boot_open(&boot)||boot.generation!=install_check.boot_generation)return install_check_fail(15,record,NULL);
    if(install_check.stage==1){
        /* SAM | 2026-11-07 09:13 +08:00 | Bind a duplicate to the exact durable package hash in A, not merely the same version or Boot state. No Flash mutation. */
        if(install_check.installed){
            uint8_t hash[32];yp_boot_image actual;
            if(!hash_bytes(record->hash,hash)||
               yp001_ota_native_verify(YP_OTA_A,install_check.total,hash,version_number(record->version),&actual)||
               memcmp(&actual,&install_check.new_image,sizeof actual))return install_check_fail(12,record,&boot);
        }else if(!verified_candidate(record,&install_check.new_image))return install_check_fail(12,record,&boot);
        install_check.stage=2;
        return 0;
    }
    if(install_check.stage==2){install_check.stage=3;return 1;}
    return install_check.stage==3?1:install_check_fail(16,record,&boot);
}
/* SAM | 2026-10-24 +08:00 | No erase/write: require zero durable bytes, an all-FF B slot and no prepared/active Boot intent before cancellation. */
/* SAM | 2026-10-25 +08:00 | Read-only retirement precondition; never erase B or inherit partial bytes into a new owner. */
bool yp001_ota_port_retire(const yp001_ota_record *record)
{
    yp_boot boot;uint32_t total,durable;
    if(!record||strcmp(record->target,"GR5526")||strcmp(YP001_PRODUCT_VERSION,record->source_version)||!durable_owner(record,OTA_DOWNLOADING)||
       !yp001_ota_port_progress_load(record,&total,&durable)||total!=yp001_ota_retirement_size(record)||durable>total||
       /* SAM | 2026-10-26 +08:00 | The approved R5 handoff is only for durable zero; B may retain R4 bytes and must never be erased by retirement. */
       (record->epoch==3&&durable!=0)||
       !boot_open(&boot)||boot_reset_armed)return false;
    return boot.state==YP_BOOT_EMPTY||boot.state==YP_BOOT_CONFIRMED||boot.state==YP_BOOT_REVERTED;
}
bool yp001_ota_port_cancel_empty(const yp001_ota_record *record)
{
    yp_boot boot;uint32_t total,durable;
    if(!durable_owner(record,OTA_DOWNLOADING)||
       !yp001_ota_port_progress_load(record,&total,&durable)||durable||
       !boot_open(&boot)||boot_reset_armed||
       (boot.state!=YP_BOOT_EMPTY&&boot.state!=YP_BOOT_CONFIRMED&&boot.state!=YP_BOOT_REVERTED))return false;
    return certify_b_empty();
}
bool yp001_ota_port_install_prepare(const yp001_ota_record *record)
{
    yp_boot boot;yp_boot_image old,next;
    /* SAM | 2026-11-07 09:13 +08:00 | Prepare accepts only a pre-install receipt authenticated before the short lease; an installed-target acknowledgement cannot prepare Boot. */
    if(install_check.installed||!durable_owner(record,OTA_PREPARED)||!yp001_ota_port_install_check_ready(record)||!boot_open(&boot)||
       boot.generation!=install_check.boot_generation)return false;
    old=install_check.old_image;next=install_check.new_image;
    if(boot.state==YP_BOOT_PREPARED)
        return !memcmp(&boot.old_image,&old,sizeof(old))&&!memcmp(&boot.new_image,&next,sizeof(next));
    install_backend_check=true;
    int result=yp_boot_prepare(&boot,&old,&next);
    install_backend_check=false;
    if(result)return false;
    install_check.boot_generation=boot.generation;return true;
}
/* SAM | 2026-10-27 +08:00 | Preserve the first internal refusal instead of losing all return branches behind boot_commit_failed. No Flash logging, retry or safety changes. */
volatile uint32_t g_ota_install_first_error[16];
static bool install_fail(unsigned stage,const yp001_ota_record *record,const yp_boot *boot,uint32_t mask)
{
    uint32_t evidence[5];unsigned i;
    if(g_ota_install_first_error[1]!=UINT32_MAX)++g_ota_install_first_error[1];
    if(!g_ota_install_first_error[0]){
        yp_business_ota_evidence(evidence);
        g_ota_install_first_error[2]=stage;
        g_ota_install_first_error[3]=record?record->epoch:0;
        g_ota_install_first_error[4]=record?(uint32_t)record->phase:0;
        g_ota_install_first_error[5]=boot?boot->state:UINT32_MAX;
        g_ota_install_first_error[6]=boot?boot->generation:0;
        g_ota_install_first_error[7]=mask;
        for(i=0;i<5;i++)g_ota_install_first_error[8+i]=evidence[i];
        g_ota_install_first_error[13]=boot?boot->old_image.version:0;
        g_ota_install_first_error[14]=boot?boot->new_image.version:0;
        g_ota_install_first_error[15]=yp_business_status()->now_ms;
        g_ota_install_first_error[0]=1;
    }
    return false;
}
static bool install_gates_prechecked;
bool yp001_ota_port_install_commit_prechecked(const yp001_ota_record *record)
{
    bool ok;install_gates_prechecked=true;ok=yp001_ota_port_install_commit(record);install_gates_prechecked=false;return ok;
}
bool yp001_ota_port_install_commit(const yp001_ota_record *record)
{
    yp_boot boot;yp_boot_image old,next;yp001_ota_gates g;uint32_t mask;
    if(!durable_owner(record,OTA_INSTALL_PENDING))return install_fail(1,record,NULL,0);
    if(!boot_open(&boot))return install_fail(2,record,NULL,0);
    if(!yp001_ota_port_install_check_ready(record))return install_fail(3,record,&boot,0);
    if(boot.generation!=install_check.boot_generation)return install_fail(4,record,&boot,0);
    old=install_check.old_image;next=install_check.new_image;
    if(memcmp(&boot.old_image,&old,sizeof(old))||memcmp(&boot.new_image,&next,sizeof(next)))return install_fail(5,record,&boot,0);
    /* SAM | 2026-11-07 09:13 +08:00 | An authenticated already-running target only acknowledges ACTIVATE; retain health progress and never write Boot or arm reset again. */
    if(install_check.installed)return boot.state==YP_BOOT_TRIAL||boot.state==YP_BOOT_CONFIRMED;
    yp001_ota_port_gates(&g);
    /* SAM | 2026-11-07 07:14 +08:00 | Final commit shares >=50-percent OR measured USB policy; mask bit 3 records failed power qualification. */
    mask=(!g.known?1u:0u)|(!g.stable?2u:0u)|
        (g.alarm?16u:0u)|(g.call?32u:0u)|(g.activity?64u:0u)|(!g.peer_stable?128u:0u);
    /* SAM | 2026-11-07 07:14 +08:00 | Fresh power is mandatory even after prechecked admission; Flash-stalled sensor age exemptions cannot hide USB unplug. */
    if(!yp001_ota_commit_power(g.battery))return install_fail(6,record,&boot,mask|8u);
    if(mask&&!install_gates_prechecked)return install_fail(6,record,&boot,mask);
    install_backend_check=true;
    int activation=boot.state==YP_BOOT_INSTALL?0:boot.state==YP_BOOT_PREPARED?yp_boot_activate(&boot):-1;
    install_backend_check=false;
    if(activation)return install_fail(7,record,&boot,0);
    install_check.boot_generation=boot.generation;
    if(!boot_reset_armed){boot_reset_at=yp_business_status()->now_ms;boot_reset_armed=true;}
    return true;
}
/* SAM | 2026-10-23 19:26 +08:00 | Health confirmation uses authenticated executing identity and 120 seconds of observed foreground health, never CAT1's claimed version. */
/* SAM | 2026-10-27 +08:00 | Inspect durable Boot phase before costly authentication: PREPARED/INSTALL cannot produce a health result. No Flash writes or authentication here. */
static bool result_boot(const yp001_ota_record *record,yp_boot *boot)
{
    return durable_owner(record,OTA_INSTALL_PENDING)&&boot_open(boot)&&
        (boot->state==YP_BOOT_TRIAL||boot->state==YP_BOOT_CONFIRMED||boot->state==YP_BOOT_REVERTED)&&
        boot->new_image.version==version_number(record->version)&&
        boot->old_image.version==version_number(record->source_version);
}
static bool health_current(const yp001_ota_record *record,const yp_boot *boot)
{
    return health_check.valid&&!memcmp(record,&health_check.owner,sizeof(*record))&&
        boot->generation==health_check.boot_generation&&boot->state==health_check.boot_state&&
        !memcmp(&boot->old_image,&health_check.old_image,sizeof(boot->old_image))&&
        !memcmp(&boot->new_image,&health_check.new_image,sizeof(boot->new_image));
}
/* SAM | 2026-10-27 +08:00 | One authenticated executing identity per unchanged boot/owner/journal, read-only and outside the Flash lease. Full confirmation still follows 120s of actual health. */
static bool health_identity(const yp001_ota_record *record,const yp_boot *boot)
{
    yp_boot_image actual;const yp_boot_image *expected;
    if(health_current(record,boot))return true;
    health_check.valid=false;health_started=false;
    if(yp001_ota_flash_allowed()||yp001_ota_running_image(version_number(YP001_PRODUCT_VERSION),&actual))return false;
    expected=boot->state==YP_BOOT_REVERTED?&boot->old_image:&boot->new_image;
    if(memcmp(&actual,expected,sizeof actual))return false;
    health_check.owner=*record;health_check.boot_generation=boot->generation;health_check.boot_state=boot->state;
    health_check.actual=actual;health_check.old_image=boot->old_image;health_check.new_image=boot->new_image;
    health_check.valid=true;result_check_started=false;return true;
}
/* SAM | 2026-10-27 +08:00 | Pure health observations do not need UART silence or Flash permission. Unknown inputs, link loss and unobserved gaps restart the full continuous 120s interval. */
static bool health_observe(const yp_boot *boot)
{
    yp_business_ota_inputs_t inputs;const yp_business_status_t *b=yp_business_status();uint32_t now=b->now_ms;
    if(result_check_started&&(uint32_t)(now-result_check_at)>3000u)health_started=false;
    /* SAM | 2026-11-07 07:14 +08:00 | USB-only admission must also complete the existing continuous health interval; unplug makes unknown battery fail again. */
    result_check_at=now;result_check_started=true;yp_business_ota_inputs_with_usb(&inputs,yp001_ota_port_usb_power());
    if(memcmp(&health_check.actual,&boot->new_image,sizeof(boot->new_image))||!inputs.known||
       inputs.activity||b->alarm_active||
       (b->call!=YP_CALL_IDLE&&b->call!=YP_CALL_ENDED)||
       !b->transport_ready||b->network!=YP_NET_MQTT){health_started=false;return false;}
    if(!health_started){health_since=now;health_started=true;return false;}
    return (uint32_t)(now-health_since)>=120000u;
}
bool yp001_ota_port_result_pending(const yp001_ota_record *record)
{
    yp_boot boot;
    if(!result_boot(record,&boot)){health_check.valid=false;health_started=false;return false;}
    if(health_current(record,&boot))return boot.state!=YP_BOOT_TRIAL||health_observe(&boot);
    /* First read/auth pass always yields before acquiring a short confirmation lease, so real foreground inputs can refresh afterward. */
    (void)health_identity(record,&boot);return false;
}
bool yp001_ota_port_result(const yp001_ota_record *record,yp001_ota_record *result)
{
    yp_boot boot;yp_boot_image actual;
    if(!result||!result_boot(record,&boot)||!health_current(record,&boot)){health_started=false;return false;}
    actual=health_check.actual;
    if(boot.state==YP_BOOT_TRIAL){
        if(!health_observe(&boot)||!yp001_ota_flash_allowed())return false;
        health_backend_check=true;int confirmed=yp_boot_confirm(&boot);health_backend_check=false;
        if(confirmed){health_check.valid=false;health_started=false;return false;}
        health_check.boot_generation=boot.generation;health_check.boot_state=boot.state;
        /* SAM | 2026-10-29 21:51 +08:00 | Round-1 defect 3: Boot confirm + owner write in one lease took ~4.4 s against CAT1's 3 s budget. End this lease after the
         * confirm; the next 1 s health pass sees CONFIRMED (result_pending) and writes the owner in its own short lease. Power loss between the
         * two is the same state as before (owner INSTALL_PENDING, Boot CONFIRMED), which the existing result path already resolves. */
        return false;
    }
    *result=*record;
    if(boot.state==YP_BOOT_CONFIRMED&&!memcmp(&actual,&boot.new_image,sizeof(actual)))strcpy(result->outcome,"success");
    else if(boot.state==YP_BOOT_REVERTED&&!memcmp(&actual,&boot.old_image,sizeof(actual)))strcpy(result->outcome,"fail");
    else return false;
    strcpy(result->actual_version,YP001_PRODUCT_VERSION);result->phase=OTA_COMPLETE;return true;
}
bool yp001_ota_port_completed(const yp001_ota_record *record)
{
    yp001_ota_record actual;
    /* SAM | 2026-10-23 +08:00 | CAT cannot reuse GR's Boot result. Require a verified package, fresh independently measured peer, and 120s of challenge-bound confirmed reports. */
    if(record&&!strcmp(record->target,"CAT1")){
        char version[64];const yp_business_status_t *b=yp_business_status();yp001_ota_record current;
        if(!b->transport_ready||b->network!=YP_NET_MQTT||b->alarm_active||
           (b->call!=YP_CALL_IDLE&&b->call!=YP_CALL_ENDED)||
           !yp_business_cat_version(version,sizeof version)||strcmp(version,record->actual_version)){
            cat_observed=false;return false;
        }
        return cat_observed&&same_owner(record,&cat_result_owner)&&
            yp001_ota_port_load(&current)==1&&current.phase==OTA_INSTALL_PENDING&&same_owner(record,&current)&&
            !strcmp(record->outcome,"success")&&!strcmp(record->actual_version,record->version)&&
            (uint32_t)(b->now_ms-cat_last_seen)<=3000u&&(uint32_t)(cat_last_seen-cat_first_seen)>=120000u&&
            yp001_ota_port_cat_proof_present(record);
    }
    return yp001_ota_port_result(record,&actual)&&!strcmp(actual.actual_version,record->actual_version)&&!strcmp(actual.outcome,record->outcome);
}
/* SAM | 2026-10-23 +08:00 | Fresh nonce prevents old result frames surviving GR reset; no new storage region or user-data write. */
bool yp001_ota_port_cat_challenge(const yp001_ota_record*r,char nonce[33])
{
    static const char hex[]="0123456789abcdef";uint8_t random[16];yp001_ota_record current;unsigned i;
    if(!r||!nonce||strcmp(r->target,"CAT1")||r->phase!=OTA_INSTALL_PENDING||
       yp001_ota_port_load(&current)!=1||current.phase!=OTA_INSTALL_PENDING||!same_owner(r,&current)||
       !yp001_ota_port_cat_proof_present(r)||yp001_ota_random(random))return false;
    if(!same_owner(r,&cat_result_owner)){cat_observed=false;cat_result_owner=*r;}
    for(i=0;i<16;i++){cat_nonce[i*2]=hex[random[i]>>4];cat_nonce[i*2+1]=hex[random[i]&15];}
    cat_nonce[32]=0;cat_nonce_at=yp_business_status()->now_ms;memcpy(nonce,cat_nonce,33);return true;
}
bool yp001_ota_port_cat_result(const yp001_ota_record*r,const char *nonce,const char *version,bool confirmed)
{
    char measured[64];yp001_ota_record current;const yp_business_status_t *b=yp_business_status();
    if(!r||!nonce||!version||!cat_nonce[0]||strcmp(nonce,cat_nonce)||!same_owner(r,&cat_result_owner)||
       (uint32_t)(b->now_ms-cat_nonce_at)>3000u)return false;
    cat_nonce[0]=0;
    if(!confirmed||strcmp(version,r->version)||!yp001_ota_port_cat_proof_present(r)||
       yp001_ota_port_load(&current)!=1||current.phase!=OTA_INSTALL_PENDING||!same_owner(r,&current)||
       !b->transport_ready||b->network!=YP_NET_MQTT||b->alarm_active||(b->call!=YP_CALL_IDLE&&b->call!=YP_CALL_ENDED)||
       !yp_business_cat_version(measured,sizeof measured)||strcmp(version,measured)){cat_observed=false;return false;}
    if(!cat_observed||(uint32_t)(b->now_ms-cat_last_seen)>3000u)cat_first_seen=b->now_ms;
    cat_last_seen=b->now_ms;cat_observed=true;return true;
}
bool yp001_ota_port_power_safe(const yp001_ota_record *record)
{
    yp_boot boot;yp_boot_image actual;
    /* SAM | 2026-10-27 +08:00 | PREPARED/INSTALL never authorize power changes; reject their phase before performing a useless full authentication. */
    if(boot_reset_armed||!durable_owner(record,OTA_INSTALL_PENDING)||!boot_open(&boot)||
       (boot.state!=YP_BOOT_TRIAL&&boot.state!=YP_BOOT_CONFIRMED&&boot.state!=YP_BOOT_REVERTED)||
       !health_identity(record,&boot))return false;
    actual=health_check.actual;
    if((boot.state==YP_BOOT_TRIAL||boot.state==YP_BOOT_CONFIRMED)&&
       boot.new_image.version==version_number(record->version))return !memcmp(&actual,&boot.new_image,sizeof(actual));
    return boot.state==YP_BOOT_REVERTED&&boot.old_image.version==version_number(record->source_version)&&
        !memcmp(&actual,&boot.old_image,sizeof(actual));
}
void yp001_ota_port_poll(void)
{
    /* SAM | 2026-10-23 +08:00 | Foreground observes brief business losses between result frames; they cannot count toward continuous health. */
    const yp_business_status_t*b=yp_business_status();char version[64];
    if(cat_observed&&(!b->transport_ready||b->network!=YP_NET_MQTT||b->alarm_active||
       (b->call!=YP_CALL_IDLE&&b->call!=YP_CALL_ENDED)||!yp_business_cat_version(version,sizeof version)||
       strcmp(version,cat_result_owner.version)))cat_observed=false;
    if(boot_reset_armed&&(uint32_t)(yp_business_status()->now_ms-boot_reset_at)>=250u)hal_nvic_system_reset();
}
void yp001_ota_port_reply(const char *line, size_t length) { yp001_ota_uart_reply(line, length); }
/* SAM | 2026-10-23 +08:00 | Bind the actual UART path to checked dispatch. A zero-initialized receiver cannot erase/write or claim installation readiness. */
static yp_receive wire_receiver;
static yp001_ota_record receiver_owner;
static bool transfer_idle(void)
{
    yp001_ota_gates g;yp001_ota_port_gates(&g);
    return g.known&&!g.alarm&&!g.call&&!g.activity&&g.peer_stable;
}
/* SAM | 2026-10-25 +08:00 | First denial is retained in RAM for non-halting J-Link reads; no Flash logging or retry policy change.
 * mask bits: 0 unknown,1 alarm,2 call,3 activity,4 peer,5 provision,6 load,
 * 7 phase,8 epoch,9 owner,10 hash,11 progress,12 total,13 watchdog.
 * evidence: clock,battery/key/motion ages,seen/value flags. sequence is committed last. */
volatile yp001_ota_rx_denial_t yp001_ota_rx_denial;
extern void yp001_safety_observation_poll(void);
static int rx_allowed(void *ctx,uint32_t epoch,const uint8_t *hash,uint32_t total)
{
    yp001_ota_record owner;yp001_ota_gates g;uint8_t expected[32];
    uint32_t saved=0,durable=0,mask=0,wdt=0xffffffffu,evidence[5];unsigned i;(void)ctx;
    /* SAM | 2026-10-25 +08:00 | Refresh only before Flash driver entry, never inside a Flash critical section. */
    yp001_safety_observation_poll();
    yp001_ota_port_gates(&g);
    if(!g.known)mask|=1u;
    if(g.alarm)mask|=2u;
    if(g.call)mask|=4u;
    if(g.activity)mask|=8u;
    if(!g.peer_stable)mask|=16u;
    memset(&owner,0,sizeof owner);
    if(!yp001_ota_port_provisioned())mask|=32u;
    else if(yp001_ota_port_load(&owner)!=1)mask|=64u;
    else {
        if(owner.phase!=OTA_DOWNLOADING)mask|=128u;
        if(epoch!=owner.epoch)mask|=256u;
        if(!same_owner(&owner,&receiver_owner))mask|=512u;
        if(!hash||!hash_bytes(owner.hash,expected)||memcmp(expected,hash,32))mask|=1024u;
        if(!yp001_ota_port_progress_load(&owner,&saved,&durable))mask|=2048u;
        else if(saved!=total)mask|=4096u;
    }
    if(!mask){wdt=app_aon_wdt_refresh();if(wdt!=APP_DRV_SUCCESS)mask|=8192u;}
    if(mask){
        ++yp001_ota_rx_denial.count;
        if(!yp001_ota_rx_denial.sequence){
            yp_business_ota_evidence(evidence);
            yp001_ota_rx_denial.mask=mask;
            for(i=0;i<5;i++)yp001_ota_rx_denial.evidence[i]=evidence[i];
            yp001_ota_rx_denial.epoch=epoch;yp001_ota_rx_denial.total=total;
            yp001_ota_rx_denial.accepted=wire_receiver.accepted;
            yp001_ota_rx_denial.durable=durable;
            yp001_ota_rx_denial.gate_bits=(g.known?1u:0u)|(g.alarm?2u:0u)|(g.call?4u:0u)|
                (g.activity?8u:0u)|(g.peer_stable?16u:0u);
            yp001_ota_rx_denial.watchdog=wdt;yp001_ota_rx_denial.owner_epoch=owner.epoch;
            yp001_ota_rx_denial.owner_phase=owner.phase;yp001_ota_rx_denial.saved_total=saved;
            /* SAM | 2026-10-25 +08:00 | Commit the exact first-denial peer state and loss history before publishing sequence. */
            {
                uint32_t peer[12];yp_business_peer_evidence(peer);
                for(i=0;i<12;i++)yp001_ota_rx_denial.peer[i]=peer[i];
            }
            yp001_ota_rx_denial.sequence=1;
        }
        return -1;
    }
    return 0;
}
static int rx_extent(uint32_t address,uint32_t n)
{
    return n&&address>=YP_OTA_B&&address-YP_OTA_B<YP_OTA_SLOT_BYTES&&n<=YP_OTA_SLOT_BYTES-(address-YP_OTA_B);
}
static int rx_read(void *ctx,uint32_t address,void *p,uint32_t n)
{
    (void)ctx;if(!p||!rx_extent(address,n)||app_aon_wdt_refresh()!=APP_DRV_SUCCESS)return -1;
    return hal_flash_read(address,p,n)==n?0:-1;
}
static int rx_write(void *ctx,uint32_t address,const void *p,uint32_t n)
{
    if(!yp001_ota_flash_allowed()||!p||!rx_extent(address,n)||rx_allowed(ctx,wire_receiver.session,wire_receiver.hash,wire_receiver.total))return -1;
    /* SAM | 2026-10-27 +08:00 | Invalidate even an uncertain/partial B write before the HAL can mutate a signed span. */
    yp001_ota_port_install_check_reset();++b_generation;
    health_check.valid=false;
    return hal_flash_write(address,p,n)==n?0:-1;
}
static int rx_erase(void *ctx,uint32_t address)
{
    if(!yp001_ota_flash_allowed()||address%OTA_PAGE_SIZE||!rx_extent(address,OTA_PAGE_SIZE)||
       rx_allowed(ctx,wire_receiver.session,wire_receiver.hash,wire_receiver.total))return -1;
    yp001_ota_port_install_check_reset();++b_generation;
    health_check.valid=false;
    return hal_flash_erase(address,OTA_PAGE_SIZE)?0:-1;
}
static int rx_checkpoint(void *ctx,uint32_t epoch,const uint8_t *hash,uint32_t total,uint32_t at)
{
    if(rx_allowed(ctx,epoch,hash,total))return -1;
    return yp001_ota_port_progress_store(&receiver_owner,total,at)?0:-1;
}
static int rx_verify(void *ctx,const uint8_t *hash,uint32_t total)
{
    yp_boot_image image;uint32_t version=version_number(receiver_owner.version);
    if(rx_allowed(ctx,wire_receiver.session,hash,total)||!version)return -1;
    return yp001_ota_native_verify(YP_OTA_B,total,hash,version,&image);
}
bool yp001_ota_port_receive_prepare(const yp001_ota_record *owner,uint32_t total)
{
    yp001_ota_record actual;uint32_t stored,durable;uint8_t hash[32];
    yp_receive_io io={0,rx_allowed,rx_read,rx_erase,rx_write,rx_checkpoint,rx_verify};
    if(!owner||strcmp(owner->target,"GR5526")||owner->phase!=OTA_DOWNLOADING||
       total<8u+YP_OTA_SIGNATURE_BYTES||total>YP_OTA_SLOT_BYTES||!transfer_idle()||
       yp001_ota_port_load(&actual)!=1||!same_owner(owner,&actual)||actual.phase!=OTA_DOWNLOADING||
       !hash_bytes(owner->hash,hash)||!yp001_ota_port_progress_load(owner,&stored,&durable))return false;
    if(!stored){
        if(!yp001_ota_port_progress_store(owner,total,0))return false;
        stored=total;durable=0;
    }
    if(stored!=total)return false;
    receiver_owner=*owner;
    if(yp_receive_open(&wire_receiver,&io,owner->epoch,hash,total,durable))return false;
    /* SAM | 2026-11-01 +08:00 | A fresh GR transfer is staged in the fixed PSRAM OTA region (512 KB) and written to B only when complete.
     * A resume from a durable B offset, or PSRAM not ready, keeps the original direct-to-B path. */
    if(!durable){
        void *base=0;uint32_t size=0;
        if(yp_psram_mem_init()&&yp_psram_ota_region(&base,&size)&&base&&!yp_receive_stage(&wire_receiver,(uint8_t *)base,size))
            printf("[OTA] PSRAM staging total=%lu region=%lu\r\n",(unsigned long)total,(unsigned long)size);
        else printf("[OTA] PSRAM staging unavailable; direct B path\r\n");
    }
    return true;
}

void yp001_ota_port_wire(const uint8_t *frame,size_t length)
{
    uint8_t response[44];uint32_t n;
    if(length>540u)return;
    if(!wire_receiver.ready && length>=28u && frame[5]==YP_RX_HELLO && yp001_ota_wire_valid(frame,length)){
        yp001_ota_record owner;uint32_t total,durable;
        if(yp001_ota_port_load(&owner)==1 && yp001_ota_port_progress_load(&owner,&total,&durable) && total)
            (void)yp001_ota_port_receive_prepare(&owner,total);
    }
    n=yp_receive_frame(&wire_receiver,frame,(uint32_t)length,response,sizeof(response));
    if(n)yp001_ota_uart_reply((const char *)response,n);
}

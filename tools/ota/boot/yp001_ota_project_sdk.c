/* SAM | 2026-10-23 +08:00 | Reuse SDK104 SHA/PKC and check Flash read status;
 * encrypted ROM mode is deliberately rejected, never disabled or reconfigured. */
#include "yp001_ota_project_sdk.h"
#include "gr_includes.h"
#include "grx_sys.h"
#include "hal_flash.h"
#include "rsa.h"
#include "bootloader_config.h"
#include "custom_config.h"
#include <string.h>
#if !defined(SOC_GR5526) || !defined(BOOTLOADER_SIGN_ENABLE) || !BOOTLOADER_SIGN_ENABLE || BOOTLOADER_BOOT_PORT_ENABLE || SECURITY_CFG_VAL || !defined(BOOTLOADER_WDT_ENABLE) || !BOOTLOADER_WDT_ENABLE
#error YP_PROJECT_RSA_SDK104_CONFIG_REQUIRED
#endif
/* SHA ABI matches the SDK104 sign_verify.c declaration. */
typedef struct {
 uint8_t *user_hash;uint8_t hmac_key_type_sel,operation_mode;uint8_t *hmac_key;
 uint8_t dma_enable,no_padding,interrupt_enable,continue_input;
} yp_sdk_sha_config;
extern int gm_drv_sha_encrypt(const yp_sdk_sha_config*,const uint8_t*,uint32_t,uint8_t*);
extern int bootloader_wdt_service(void*);
static int ready(void){return sys_security_enable_status_check()||bootloader_wdt_service(0)?-1:0;}
static int read_flash(void*c,uint32_t a,void*p,uint32_t n){
 (void)c;
 if(ready()||hal_flash_read(a,p,n)!=n)return -1;
 return ready();
}
static int hash_ram(void*c,const void*p,uint32_t n,uint8_t*out){
 yp_sdk_sha_config config={0};(void)c;
 if(ready()||gm_drv_sha_encrypt(&config,p,n,out)!=0)return -1;
 return ready();
}
static int hash_flash(void*c,uint32_t a,uint32_t n,uint8_t*out){return hash_ram(c,(const void*)a,n,out);}
static int pss(void*c,const uint8_t*key,const uint8_t*sig,const uint8_t*hash){
 bl_rsa_context context={0};(void)c;context.len=256;context.pk=(bl_rsa_public_key_t*)key;
 if(ready()||bl_rsa_rsassa_pss_verify(&context,hash,sig)!=0)return -1;
 return ready();
}
int yp_boot_project_sdk_init(yp_project_verify*p,const uint8_t*layout,const uint8_t*data,const uint8_t*key){
 if(!p)return -1;
 memset(p,0,sizeof *p);
 if(!layout||!data||!key||ready())return -1;
 app_boot_security_clock_set();
 ll_cgc_disable_force_off_secu_hclk();ll_cgc_disable_force_off_secu_div4_pclk();
 ll_cgc_disable_force_off_rng_hclk();ll_cgc_disable_force_off_hmac_hclk();ll_cgc_disable_force_off_pkc_hclk();
 memcpy(p->layout_hash,layout,32);memcpy(p->data_hash,data,32);memcpy(p->public_hash,key,32);
 p->read=read_flash;p->hash_flash=hash_flash;p->hash_ram=hash_ram;p->pss=pss;return 0;
}

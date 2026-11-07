/* Historical functions after Boot-stage guard, before read-only health preparation. NOT firmware inputs. SAM | 2026-10-27 +08:00 */
static bool result_boot(const yp001_ota_record *record,yp_boot *boot)
{
    return durable_owner(record,OTA_INSTALL_PENDING)&&boot_open(boot)&&
        (boot->state==YP_BOOT_TRIAL||boot->state==YP_BOOT_CONFIRMED||boot->state==YP_BOOT_REVERTED)&&
        boot->new_image.version==version_number(record->version)&&
        boot->old_image.version==version_number(record->source_version);
}
}bool yp001_ota_port_result(const yp001_ota_record *record,yp001_ota_record *result)
{
    yp_boot boot;yp_boot_image actual;yp_business_ota_inputs_t inputs;uint32_t now=yp_business_status()->now_ms;
    if(result_check_started&&(uint32_t)(now-result_check_at)<1000u)return false;
    /* Long unobserved gaps cannot be counted as healthy execution. */
    if(result_check_started&&(uint32_t)(now-result_check_at)>3000u)health_started=false;
    result_check_at=now;result_check_started=true;
    if(!result||!result_boot(record,&boot)||
       yp001_ota_running_image(version_number(YP001_PRODUCT_VERSION),&actual)){health_started=false;return false;}
    if(boot.state==YP_BOOT_TRIAL){
        yp_business_ota_inputs(&inputs);
        if(memcmp(&actual,&boot.new_image,sizeof(actual))||!inputs.known||!yp_business_status()->transport_ready||
           yp_business_status()->network!=YP_NET_MQTT){health_started=false;return false;}
        if(!health_started){health_since=now;health_started=true;return false;}
        if((uint32_t)(now-health_since)<120000u||yp_boot_confirm(&boot))return false;
    }
    *result=*record;
    if(boot.state==YP_BOOT_CONFIRMED&&!memcmp(&actual,&boot.new_image,sizeof(actual)))strcpy(result->outcome,"success");
    else if(boot.state==YP_BOOT_REVERTED&&!memcmp(&actual,&boot.old_image,sizeof(actual)))strcpy(result->outcome,"fail");
    else return false;
    strcpy(result->actual_version,YP001_PRODUCT_VERSION);result->phase=OTA_COMPLETE;return true;
}

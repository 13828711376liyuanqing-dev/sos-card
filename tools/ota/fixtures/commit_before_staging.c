/* Historical production function captured before staged validation; NOT a firmware build input. SAM | 2026-10-27 +08:00 */
bool yp001_ota_port_install_commit(const yp001_ota_record *record)
{
    yp_boot boot;yp_boot_image old,next;yp001_ota_gates g;uint32_t mask;
    if(!durable_owner(record,OTA_INSTALL_PENDING))return install_fail(1,record,NULL,0);
    if(!boot_open(&boot))return install_fail(2,record,NULL,0);
    if(yp001_ota_running_image(version_number(YP001_PRODUCT_VERSION),&old))return install_fail(3,record,&boot,0);
    if(!verified_candidate(record,&next))return install_fail(4,record,&boot,0);
    if(memcmp(&boot.old_image,&old,sizeof(old))||memcmp(&boot.new_image,&next,sizeof(next)))return install_fail(5,record,&boot,0);
    yp001_ota_port_gates(&g);
    /* SAM | 2026-10-24 +08:00 | The final GR commit shares the explicit bench power policy; threshold, physical activity and peer checks are unchanged. */
    /* SAM | 2026-10-27 +08:00 | Mask mirrors the exact existing commit gates, evaluating physical USB only after known/stable as before. */
    mask=(!g.known?1u:0u)|(!g.stable?2u:0u)|(g.battery<70u||g.battery>100u?8u:0u)|
        (g.alarm?16u:0u)|(g.call?32u:0u)|(g.activity?64u:0u)|(!g.peer_stable?128u:0u);
    if(g.known&&g.stable&&!yp001_ota_commit_power(g.charging))mask|=4u;
    if(mask)return install_fail(6,record,&boot,mask);
    if(boot.state!=YP_BOOT_INSTALL&&(boot.state!=YP_BOOT_PREPARED||yp_boot_activate(&boot)))return install_fail(7,record,&boot,0);
    if(!boot_reset_armed){boot_reset_at=yp_business_status()->now_ms;boot_reset_armed=true;}
    return true;
}

/* 摘录自 ble_app_uart_c/Src/user/business/yp001_business.c（姓名下发、长期保存、清空相关部分，参考用，以项目源码为准） */

/* SAM | 2026-11-02 +08:00 | Resident name push (name_begin / glyph x g / name_end). The name text keeps the existing
 * NVDS persistence; glyphs stay RAM-only, so after reboot the UI asks CAT1 to re-fetch them (NAME_RES need). */
static void name_result(uint32_t id, unsigned err, unsigned index) {
    char line[96];
    int n = snprintf(line, sizeof(line), "NAME_RES={\"op\":\"result\",\"id\":%lu,\"ok\":%s,\"err\":%u,\"i\":%u}\r\n",
                     (unsigned long)id, err ? "false" : "true", err, index);
    if (n > 0 && (size_t)n < sizeof(line)) (void)yp_business_port_send(line, (size_t)n);
}
static bool hex_field(cJSON *j, const char *key, size_t min, size_t max, uint32_t *v) {
    const char *t = str(j,key); char *end;
    if (!t || strlen(t) < min || strlen(t) > max) return false;
    *v = (uint32_t)strtoul(t, &end, 16);
    return *end == '\0';
}
static void name_line(cJSON *j, const char *op) {
    uint32_t id, v, count;
    if (!number(j,"id",0xffffffffU,&id)) return;
    if (!strcmp(op,"name_begin")) {
        const char *name=str(j,"name"), *room=str(j,"room"), *campus=str(j,"campus");
        name_txn.open=false;
        /* SAM | 2026-11-03 +08:00 | g may be 0: an English (ASCII) name is drawn with the built-in font. */
        if (!number(j,"g",YP_NG_MAX,&count) || !number(j,"seq",0xffffffffU,&v) || !name || !room || !campus ||
            !name[0] || strlen(name)>=sizeof(name_txn.name) || strlen(room)>=sizeof(name_txn.room) ||
            strlen(campus)>=sizeof(name_txn.campus)) { name_result(id,YP_NG_BAD,0); return; }
        if (v < name_txn.last_seq) { name_result(id,YP_NG_TXN,0); return; }
        strcpy(name_txn.name,name); strcpy(name_txn.room,room); strcpy(name_txn.campus,campus);
        name_txn.id=id; name_txn.seq=v; name_txn.open=true;
        yp_ng_begin(id,count);
    } else if (!strcmp(op,"glyph")) {
        yp_ng_t g; int32_t x, y; uint32_t i, u, sz, w, h, a, c; const char *d=str(j,"d");
        if (!name_txn.open || id!=name_txn.id) { name_result(id,YP_NG_TXN,0); return; }
        if (!number(j,"i",YP_NG_MAX-1U,&i) || !number(j,"s",32U,&sz) || !number(j,"w",40U,&w) || !number(j,"h",40U,&h) ||
            !integer(j,"x",-40,40,&x) || !integer(j,"y",-40,40,&y) || !number(j,"a",640U,&a) || !d ||
            !hex_field(j,"u",2U,6U,&u) || !hex_field(j,"c",4U,4U,&c)) { name_txn.open=false; name_result(id,YP_NG_BAD,0); return; }
        g.u=u; g.size=(uint8_t)sz; g.w=(uint8_t)w; g.h=(uint8_t)h; g.x=(int8_t)x; g.y=(int8_t)y; g.adv_w=(uint16_t)a;
        yp_ng_err_t e=yp_ng_add(id,i,&g,d,(uint16_t)c);
        if (e) { name_txn.open=false; name_result(id,e,i); }
    } else {
        if (!name_txn.open || id!=name_txn.id || !number(j,"g",YP_NG_MAX,&count)) { name_result(id,YP_NG_TXN,0); return; }
        name_txn.open=false;
        yp_ng_err_t e=yp_ng_commit(id,count);
        if (!e && !yp_business_set_resident(name_txn.name,name_txn.room,name_txn.campus)) e=YP_NG_BAD;
        if (!e) { name_txn.last_seq=name_txn.seq; changed(); }
        /* SAM | 2026-11-03 +08:00 | Keep the shown set for good; a storage failure is reported (err 6) but the RAM copy stays shown. */
        if (!e && !yp_ng_save(name_txn.seq)) { name_result(id,6U,0); return; }
        name_result(id,e,0);
    }
}
/* SAM | 2026-11-03 +08:00 | The only two ways the resident name goes away: platform clear (op name_clear) and factory reset.
 * Reboot, power loss, OTA and silence keep it. */
void yp_business_clear_resident(void) {
    yp_ng_clear();
    (void)nvds_del(YP_NVDS_TAG_RESIDENT);
    s.name[0]=s.room[0]=s.campus[0]=0;
    s.resident_known=false;
    name_txn.open=false; name_txn.last_seq=0;
    changed();
}
void yp_business_factory_reset_name(void) { yp_business_clear_resident(); }
/* SAM | 2026-11-02 +08:00 | Ask CAT1 to re-fetch glyphs that neither the local fonts nor the RAM cache can draw. */
bool yp_business_request_glyphs(const uint32_t *cps, unsigned count) {
    char line[200]; int n=snprintf(line,sizeof(line),"NAME_RES={\"op\":\"need\",\"u\":\"");
    if (!s.transport_ready || !count || n<=0) return false;
    for (unsigned i=0; i<count && (size_t)n+8U<sizeof(line); ++i)
        n+=snprintf(line+n,sizeof(line)-(size_t)n,"%s%04lX",i?",":"",(unsigned long)cps[i]);
    n+=snprintf(line+n,sizeof(line)-(size_t)n,"\"}\r\n");
    return n>0 && (size_t)n<sizeof(line) && yp_business_port_send(line,(size_t)n);
}

static int cmd_busline(int argc, char *argv[]) {
    static char line[CLI_MAX_CMD_LEN + 8];
    int n;
    if (argc != 2 || (n = snprintf(line, sizeof(line), "BUS_EVT=%s", argv[1])) <= 0 || (size_t)n >= sizeof(line)) {
        cli_printf("Usage: busline <json>\r\n"); return -1;
    }
    (void)yp_business_handle_line(line, (size_t)n);
    cli_printf("[BUSLINE] %d B glyphs=%u name=%s\r\n", n, yp_ng_active_count(), s.resident_known ? "set" : "--");
    return 0;
}
CLI_CMD_REGISTER("busline", "Inject one BUS_EVT body", cmd_busline);
/* SAM | 2026-11-03 +08:00 | Bench view/clear of the stored resident name (clear = same path as platform clear / factory reset). */
static int cmd_name_store(int argc, char *argv[]) {
    if (argc==2 && !strcmp(argv[1],"clear")) {
        yp_business_clear_resident();
        cli_printf("[NAME] cleared (RAM + Flash pages + NVDS)\r\n"); return 0;
    }
    if (argc==2 && !strcmp(argv[1],"status")) {
        uint16_t len=yp_ng_stored_bytes();
        /* SAM | 2026-11-04 +08:00 | Glyph record now in Flash page A/B (page=0x000000: nothing stored, the factory state). */
        cli_printf("[NAME] resident=%s glyphs=%u seq=%lu stored_bytes=%u page=0x%06lX store_err=%u\r\n", s.resident_known ? "set":"--",
                   yp_ng_active_count(), (unsigned long)name_txn.last_seq, (unsigned)len, (unsigned long)yp_ng_stored_page(),
                   (unsigned)yp_ng_last_nvds_err());
        return 0;
    }
    cli_printf("Usage: name_store status | clear\r\n"); return -1;
}
CLI_CMD_REGISTER("name_store", "Stored resident name status/clear", cmd_name_store);

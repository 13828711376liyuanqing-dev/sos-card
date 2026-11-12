/* SAM | 2026-10-11 00:43 +08:00 | Exercise real LVGL pages on the host
 * because a successful target link cannot detect heap leaks or blank frames. */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "lvgl.h"
#include "epaper_lvgl.h"
#include "epaper_ui.h"
#include "guider/gui_guider.h"

/* SAM | 2026-10-13 09:12 +08:00 | Find the real SOS object because an alarm may arrive on an already visible call page. */
static lv_obj_t *find_image(lv_obj_t *obj, const void *source)
{
    if (lv_obj_check_type(obj, &lv_img_class) && lv_img_get_src(obj)==source) return obj;
    for (uint32_t i=0; i<lv_obj_get_child_cnt(obj); ++i) {
        lv_obj_t *found=find_image(lv_obj_get_child(obj,i),source);
        if (found) return found;
    }
    return NULL;
}

/* SAM | 2026-10-13 09:04 +08:00 | Supply controlled business snapshots because the GUI must render actual state fields. */
static yp_business_status_t business;
const yp_business_status_t *yp_business_status(void) { return &business; }
static bool event_during_flush;

static lv_obj_t *find_qr(lv_obj_t *obj)
{
    if (lv_obj_check_type(obj, &lv_qrcode_class)) return obj;
    uint32_t count = lv_obj_get_child_cnt(obj);
    for (uint32_t i = 0; i < count; ++i) {
        lv_obj_t *found = find_qr(lv_obj_get_child(obj, i));
        if (found != NULL) return found;
    }
    return NULL;
}

static uint32_t qr_hash(lv_obj_t *obj)
{
    const lv_img_dsc_t *image = lv_canvas_get_img(obj);
    uint32_t hash = 2166136261U;
    /* SAM | 2026-10-13 09:04 +08:00 | LVGL canvas leaves data_size zero; hash its fixed indexed-1bit backing buffer. */
    for (uint32_t i = 0; i < LV_CANVAS_BUF_SIZE_INDEXED_1BIT(84, 84); ++i)
        hash = (hash ^ image->data[i]) * 16777619U;
    return hash;
}

static bool has_label(lv_obj_t *obj, const char *value)
{
    if (lv_obj_check_type(obj, &lv_label_class) &&
        strcmp(lv_label_get_text(obj), value) == 0) return true;
    uint32_t count = lv_obj_get_child_cnt(obj);
    for (uint32_t i = 0; i < count; ++i)
        if (has_label(lv_obj_get_child(obj, i), value)) return true;
    return false;
}

static unsigned flush_count;
static unsigned black_pixels;
static unsigned battery_icon_pixels;
static unsigned lowbat_icon_pixels;
static bool display_ok = true;

/* SAM | 2026-10-12 13:23 +08:00 | Report failed host checks and exit normally
 * because MSVCRT assert/abort raised a recurring modal 0x40000015 dialog. */
#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "CHECK failed: %s (%s:%d)\n", #condition, __FILE__, __LINE__); \
        return 1; \
    } \
} while (0)

bool epaper_depg0150_display_frame(const uint8_t *frame)
{
    if (event_during_flush) {
        business.alarm_active = true;
        business.revision++;
        event_during_flush = false;
    }
    black_pixels = 0;
    battery_icon_pixels = 0;
    lowbat_icon_pixels = 0;
    for (unsigned i = 0; i < EPAPER_HOME_FRAME_BYTES; ++i)
        for (unsigned bit = 0; bit < 8; ++bit)
            black_pixels += !(frame[i] & (1U << bit));
    for (unsigned y = 8; y < 18; ++y)
        for (unsigned x = 170; x < 190; ++x)
            battery_icon_pixels +=
                !(frame[x * 25U + y / 8U] & (0x80U >> (y & 7U)));
    /* SAM | 2026-10-12 16:46 +08:00 | Measure the low-battery page's own
     * icon position because its fixed bitmap was omitted from SOC binding. */
    for (unsigned y = 8; y < 18; ++y)
        for (unsigned x = 90; x < 110; ++x)
            lowbat_icon_pixels +=
                !(frame[x * 25U + y / 8U] & (0x80U >> (y & 7U)));
    ++flush_count;
    if (flush_count <= EPAPER_UI_PAGE_COUNT) {
        char path[80];
        (void)snprintf(path, sizeof(path), "page_%u.pbm", flush_count - 1);
        FILE *fp = fopen(path, "wb");
        if (fp == NULL) {
            fprintf(stderr, "Cannot write %s\n", path);
            return false;
        }
        fprintf(fp, "P4\n200 200\n");
        for (unsigned y = 0; y < 200; ++y)
            for (unsigned x = 0; x < 200; x += 8) {
                unsigned char b = 0;
                for (unsigned k = 0; k < 8; ++k)
                    if (!(frame[(x + k) * 25 + y / 8] & (0x80U >> (y & 7))))
                        b |= 0x80U >> k;
                fwrite(&b, 1, 1, fp);
            }
        fclose(fp);
    }
    return display_ok;
}

int main(void)
{
    epaper_home_status_t status = {0};
    size_t baseline_blocks[EPAPER_UI_PAGE_COUNT] = {0};
    size_t minimum_free = 24U * 1024U;
    if (getenv("GUIDER_TEST_FORCE_FAIL") != NULL) CHECK(false);
    business.show_time = true;
    business.battery_known = true;
    business.battery_percent = 50;
    CHECK(!epaper_lvgl_show_home(NULL));
    CHECK(!epaper_ui_select_page(EPAPER_UI_PAGE_COUNT));
    CHECK(!epaper_ui_select_page((epaper_ui_page_t)-1));
    for (unsigned round = 0; round < 40; ++round) {
        for (unsigned page = 0; page < EPAPER_UI_PAGE_COUNT; ++page) {
            CHECK(epaper_ui_select_page((epaper_ui_page_t)page));
            unsigned previous = flush_count;
            CHECK(epaper_lvgl_show_home(&status));
            CHECK(flush_count == previous + 1);
            CHECK(black_pixels > 100 && black_pixels < 20000);
            /* SAM | 2026-10-11 01:14 +08:00 | Exclude LVGL's two
             * built-in overlay layers because they are not UI pages. */
            lv_disp_t *disp = lv_disp_get_default();
            unsigned pages = 0;
            for (unsigned i = 0; i < disp->screen_cnt; ++i)
                if (disp->screens[i] != disp->top_layer &&
                    disp->screens[i] != disp->sys_layer) ++pages;
            CHECK(pages == 1);
            CHECK(lv_mem_test() == LV_RES_OK);
            lv_mem_monitor_t monitor;
            lv_mem_monitor(&monitor);
            if (monitor.free_size < minimum_free) minimum_free = monitor.free_size;
            if (round == 2) {
                baseline_blocks[page] = monitor.used_cnt;
            }
            if (round > 2) {
                /* SAM | 2026-10-12 13:23 +08:00 | Check live-block stability
                 * and the 12KB floor without a modal assertion dialog. */
                CHECK(monitor.used_cnt == baseline_blocks[page]);
                CHECK(monitor.free_size >= 12U * 1024U);
            }
            if (round == 0)
                printf("page=%u black=%u free=%lu largest=%lu\n", page,
                       black_pixels, (unsigned long)monitor.free_size,
                       (unsigned long)monitor.free_biggest_size);
        }
    }
    /* SAM | 2026-10-13 09:04 +08:00 | Check actual SOC artwork and unknown icon visibility across four layouts. */
    for (unsigned page = EPAPER_UI_SCREEN; page <= EPAPER_UI_LOWBAT; ++page) {
        CHECK(epaper_ui_select_page((epaper_ui_page_t)page));
        business.battery_known = true;
        business.battery_percent = 25;
        CHECK(epaper_lvgl_show_home(&status));
        unsigned empty_pixels = page == EPAPER_UI_LOWBAT ?
                                lowbat_icon_pixels : battery_icon_pixels;
        business.battery_percent = 100;
        CHECK(epaper_lvgl_show_home(&status));
        unsigned full_pixels = page == EPAPER_UI_LOWBAT ?
                               lowbat_icon_pixels : battery_icon_pixels;
        if (full_pixels <= empty_pixels) {
            fprintf(stderr, "battery icon page=%u empty=%u full=%u\n",
                    page, empty_pixels, full_pixels);
            return 1;
        }
        business.battery_known = false;
        CHECK(epaper_lvgl_show_home(&status));
        CHECK((page == EPAPER_UI_LOWBAT ? lowbat_icon_pixels :
               battery_icon_pixels) == 0);
    }
    /* SAM | 2026-10-13 09:04 +08:00 | Verify private data, unknowns and priority in real LVGL objects. */
    CHECK(epaper_ui_select_page(EPAPER_UI_SCREEN));
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(!epaper_ui_needs_refresh());
    CHECK(has_label(lv_scr_act(), "--"));
    CHECK(!has_label(lv_scr_act(), "860123456789024"));
    lv_obj_t *qr = find_qr(lv_scr_act());
    CHECK(qr != NULL && lv_obj_has_flag(qr, LV_OBJ_FLAG_HIDDEN));
    business.imei_known = true;
    strcpy(business.imei, "123456789012345");
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "123456789012345"));
    qr = find_qr(lv_scr_act());
    CHECK(qr != NULL && !lv_obj_has_flag(qr, LV_OBJ_FLAG_HIDDEN));
    uint32_t first_qr = qr_hash(qr);
    strcpy(business.imei, "123456789012346");
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(qr_hash(find_qr(lv_scr_act())) != first_qr);
    strcpy(business.imei, "INVALID");
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "--"));
    CHECK(lv_obj_has_flag(find_qr(lv_scr_act()), LV_OBJ_FLAG_HIDDEN));
    business.revision++;
    CHECK(epaper_ui_needs_refresh());
    business.resident_known = true;
    strcpy(business.name, "TEST NAME");
    strcpy(business.room, "A-101");
    strcpy(business.campus, "TEST CAMPUS");
    CHECK(epaper_ui_select_page(EPAPER_UI_MAIN));
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "TEST NAME"));
    CHECK(has_label(lv_scr_act(), "A-101"));
    CHECK(!has_label(lv_scr_act(), "张秀芳"));
    CHECK(has_label(lv_scr_act(), "NET:--"));
    business.network = YP_NET_OFFLINE;
    business.arrears_known = false;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "NET:OFFLINE"));
    CHECK(has_label(lv_scr_act(), "B:-- S:--\nFEE:--"));
    strcpy(business.name, "测试");
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "--"));
    strcpy(business.name, "TEST NAME");
    business.show_time = false;
    CHECK(epaper_ui_select_page(EPAPER_UI_TIME));
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "TEST NAME"));
    business.show_time = true;
    business.time_known = true;
    strcpy(business.clock, "09:15");
    strcpy(business.date, "2026-10-13");
    strcpy(business.weekday, "MON");
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "09:15"));
    business.call = YP_CALL_DIALING;
    strcpy(business.notice, "ALARM PENDING");
    CHECK(epaper_ui_select_page(EPAPER_UI_MAIN));
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "正在呼叫..."));
    CHECK(has_label(lv_scr_act(), "ALARM PENDING"));
    lv_obj_t *sos_image=find_image(lv_scr_act(), &_icon_sos_alpha_72x72);
    CHECK(sos_image!=NULL && lv_obj_has_flag(sos_image,LV_OBJ_FLAG_HIDDEN));
    business.alarm_active=true;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(!lv_obj_has_flag(sos_image,LV_OBJ_FLAG_HIDDEN));
    business.call = YP_CALL_ENDED;
    business.alarm_active = true;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "SOS ACTIVE"));
    CHECK(business.alarm_active);
    business.call = YP_CALL_IDLE;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "SOS"));
    business.alarm_active = false;
    business.call = YP_CALL_ENDED;
    business.now_ms = 100U;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "通话结束"));
    business.now_ms = 5100U;
    CHECK(epaper_ui_needs_refresh());
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "TEST NAME"));
    business.call = YP_CALL_IDLE;
    business.battery_known = true;
    business.battery_percent = 24;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "当前电量低"));
    business.battery_percent = 50;
    CHECK(epaper_ui_select_page(EPAPER_UI_MAIN));
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(!epaper_ui_needs_refresh());
    event_during_flush = true;
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(epaper_ui_needs_refresh());
    CHECK(epaper_lvgl_show_home(&status));
    CHECK(has_label(lv_scr_act(), "SOS"));
    business.alarm_active = false;
    display_ok = false;
    CHECK(!epaper_lvgl_show_home(&status));
    CHECK(epaper_ui_needs_refresh());
    display_ok = true;
    CHECK(epaper_lvgl_show_home(&status));
    printf("minimum steady-state free=%lu of %u bytes\n", (unsigned long)minimum_free, 24U * 1024U);
    puts("PASS: six pages, 240 transitions, no heap loss, stable live allocations, flush failure/retry");
    return 0;
}

"""SAM | 2026-10-09 15:15 +08:00 | Source contracts, not device acceptance."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
TREES = [ROOT/'ble_app_uart_c', ROOT/'SVN交付_YP001_GR5526_20261001/ble_app_uart_c']
class DisplayContract(unittest.TestCase):
    # SAM | 2026-10-09 18:33 +08:00 | Include invalid first samples and
    # validity transitions because ADC RANGE was left as stale EXT IDLE.
    def test_first_sample_and_validity_change_use_full_refresh(self):
        for tree in TREES:
            bsp=(tree/'Src/platform/bsp.c').read_text(encoding='utf-8')
            epd=(tree/'Src/user/epaper_depg0150.c').read_text(encoding='utf-8')
            header=(tree/'Src/user/epaper_depg0150.h').read_text(encoding='utf-8')
            self.assertIn('if (last_text == NULL || voltage_known != last_known)',bsp)
            self.assertIn('epaper_depg0150_force_full_next();',bsp)
            self.assertIn('void epaper_depg0150_force_full_next(void);',header)
            self.assertIn('s_force_full_next',epd)
            # SAM | 2026-10-09 22:21 +08:00 | Ignore line wrapping because the
            # new partial-count guard must not weaken the forced-full condition.
            self.assertRegex(epd,r'!s_force_full_next\s*&&\s*s_refresh_mode\s*==\s*EPAPER_REFRESH_MODE_PARTIAL')
    # SAM | 2026-10-09 16:58 +08:00 | Guard the demo-to-home full baseline
    # because partial refresh left the startup TEST OK pixels on the panel.
    def test_demo_to_home_forces_one_full_refresh(self):
        for tree in TREES:
            epd=(tree/'Src/user/epaper_depg0150.c').read_text(encoding='utf-8')
            demo=epd.split('bool epaper_depg0150_display_demo_image(void)',1)[1]
            demo=demo.split('bool epaper_depg0150_display_home(',1)[0]
            self.assertIn('s_previous_frame_valid = false;',demo)
            self.assertRegex(epd,r'EPAPER_REFRESH_MODE_PARTIAL\s*&&\s*s_previous_frame_valid')
    # SAM | 2026-10-09 16:31 +08:00 | Guard the tested SysTick priority because
    # priority 0x3F let SysTick hit QP qv_port assertion 110 during EPD work.
    def test_systick_priority_below_qp_critical_threshold(self):
        for tree in TREES:
            bsp=(tree/'Src/platform/bsp.c').read_text(encoding='utf-8')
            self.assertIn('NVIC_SetPriority(SysTick_IRQn, 0x7FU);',bsp)
    def test_display(self):
        for tree in TREES:
            h=(tree/'Src/user/gui/epaper_home.h').read_text(encoding='utf-8')
            self.assertIn('voltage_known',h)
            c=(tree/'Src/user/gui/epaper_home.c').read_text(encoding='utf-8')
            self.assertIn('status->voltage_known',c)
            self.assertIn('status->power_text',c)
            self.assertIn('status->battery_known',c)
            # SAM | 2026-10-12 15:40 +08:00 | LVGL pages now receive the
            # validated battery sample through the page manager API.
            c=(tree/'Src/user/gui/epaper_lvgl.c').read_text(encoding='utf-8')
            self.assertIn('epaper_ui_set_battery(status->battery_percent', c)
            c=(tree/'Src/user/charger/yp001_charger.c').read_text(encoding='utf-8')
            self.assertIn('yp001_charger_display_status',c)
            bsp=(tree/'Src/platform/bsp.c').read_text(encoding='utf-8')
            self.assertIn('battery_display_poll()',bsp)
            self.assertIn('1000U',bsp) # 100Hz ticks / 10s display interval
            epd=(tree/'Src/user/epaper_depg0150.c').read_text(encoding='utf-8')
            self.assertIn('yp001_charger_poll()',epd)
    def test_copies(self):
        # SAM | 2026-10-09 15:45 +08:00 | Include new ADC module in delivery gate.
        # SAM | 2026-10-12 16:49 +08:00 | Guard the page battery binding in
        # both Keil trees because an unsynced copy would ship a fixed icon.
        for p in ['Src/user/yp001_battery.c','Src/user/yp001_battery.h','Src/user/gui/epaper_home.c','Src/user/gui/epaper_home.h','Src/user/gui/epaper_lvgl.c','Src/user/gui/epaper_ui.c','Src/user/charger/yp001_charger.c','Src/user/charger/yp001_charger.h','Src/user/epaper_depg0150.c']:
            self.assertEqual(*[(t/p).read_bytes() for t in TREES])

    # SAM | 2026-10-12 15:20 +08:00 | Require the LVGL battery bar binding
    # before implementation so invalid samples cannot update it as valid data.
    def test_lvgl_battery_bar_contract(self):
        for tree in TREES:
            guider = (tree/'Src/user/gui/guider/gui_guider.h').read_text(encoding='utf-8')
            ui_h = (tree/'Src/user/gui/epaper_ui.h').read_text(encoding='utf-8')
            ui_c = (tree/'Src/user/gui/epaper_ui.c').read_text(encoding='utf-8')
            bsp = (tree/'Src/platform/bsp.c').read_text(encoding='utf-8')
            self.assertIn('screen_main_img_bat', guider)
            self.assertIn('screen_time_img_bat', guider)
            self.assertIn('screen_lowbat_img_bat', guider)
            self.assertIn('epaper_ui_set_battery(uint8_t percent, bool known)', ui_h)
            self.assertIn('s_battery_maps', ui_c)
            self.assertIn('lv_img_set_src(image, &s_battery_desc[level])', ui_c)
            self.assertIn('s_ui.screen_lowbat_img_bat', ui_c)
            self.assertIn('&_battery_1_alpha_20x10', ui_c)
            lvgl = (tree/'Src/user/gui/epaper_lvgl.c').read_text(encoding='utf-8')
            self.assertIn('epaper_ui_set_battery(status->battery_percent', lvgl)
            self.assertIn('home.battery_known', bsp)
    def test_keil_inputs_exist(self):
        # SAM | 2026-10-09 15:45 +08:00 | Prevent missing-file handoff failures.
        import xml.etree.ElementTree as ET
        for tree in TREES:
            project=tree/'Keil_6/YP001_GR5526.uvprojx'
            paths=[e.text for e in ET.parse(project).findall('.//FilePath')]
            self.assertEqual(sum(p.endswith('yp001_battery.c') for p in paths),1)
            for p in paths:
                self.assertTrue((project.parent/p).is_file(),str(project.parent/p))
if __name__=='__main__': unittest.main()

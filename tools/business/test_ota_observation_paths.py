"""SAM | 2026-10-25 +08:00 | Check real alternate receive paths, not only one service."""
from pathlib import Path
r=Path(__file__).resolve().parents[2]
b=(r/'ble_app_uart_c/Src/platform/bsp.c').read_text(encoding='utf-8-sig')
u=(r/'ble_app_uart_c/Src/platform/user_periph_setup.c').read_text(encoding='utf-8-sig')
p=(r/'ble_app_uart_c/Src/user/ota/yp001_ota_port.c').read_text(encoding='utf-8-sig')
def body(s,start,end): return s[s.index(start):s.index(end,s.index(start))]
rx=body(u,'static void cat_diag_poll(void)','/* SAM | 2026-10-13 08:36 +08:00 | Expose')
assert 'yp001_safety_observation_poll();' in rx, 'CLI direct RX bypasses safety observations'
assert rx.index('yp001_safety_observation_poll();')<rx.index('yp001_ota_mux_feed(')
motion=body(b,'static void motion_observation_poll(void)','static void battery_observation_poll(void)')
assert 's_lcd_ready' not in motion, 'motion depends on screen readiness'
battery=body(b,'static void battery_observation_poll(void)','void yp001_safety_observation_poll(void)')
assert 's_lcd_ready' not in battery, 'battery depends on screen readiness'
permission=body(p,'static int rx_allowed(','static int rx_extent(')
assert permission.index('yp001_safety_observation_poll();')<permission.index('yp001_ota_port_gates(')
assert 'yp001_ota_rx_denial' in permission
print('PASS: shared RX and write permission paths refresh; display-independent sampling; denial capture')

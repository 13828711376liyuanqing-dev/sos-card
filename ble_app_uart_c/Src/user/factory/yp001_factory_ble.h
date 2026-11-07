/* SAM | 2026-10-13 15:00 +08:00 | Foreground-only BLE factory test service. */
#ifndef YP001_FACTORY_BLE_H
#define YP001_FACTORY_BLE_H
#include <stdint.h>
/* SAM | 2026-11-06 +08:00 | Copies at most 256 bytes under saved PRIMASK; no BLE/QP call or allocation. */
void yp_factory_ble_capture(const uint8_t *data, uint16_t size);
void yp_factory_ble_init(void);
void yp_factory_ble_disconnected(uint8_t conn);
void yp_factory_ble_poll(void);
void yp_factory_ble_tick(uint32_t elapsed_ms);
#endif

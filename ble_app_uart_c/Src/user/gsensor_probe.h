/* SAM | 2026-10-10 11:35 +08:00 | Share validated XYZ sampling with LCD
 * because ID-only probing cannot supply live acceleration values. */
#ifndef GSENSOR_PROBE_H
#define GSENSOR_PROBE_H

#include <stdbool.h>
#include <stdint.h>

/* Temporary configuration, one sample, restore; false clears all outputs. */
bool gsensor_read_mg(int32_t xyz[3]);
bool gsensor_read_mg_fast(int32_t xyz[3]);
/* SAM | 2026-10-16 17:30 +08:00 | Expose bounded DA215 motion setup for the serial sleep test because XYZ sampling does not assert INT1. */
/* SAM | 2026-10-18 21:40 +08:00 | Select one explicit polarity for sensor output and MCU interpretation because live voltage reports require a controlled high/low comparison. */
bool gsensor_sleep_motion_arm(bool active_high);
bool gsensor_sleep_motion_active_high(void);
bool gsensor_sleep_motion_pin_active(void);
bool gsensor_sleep_motion_restore(void);
/* SAM | 2026-10-17 17:51 +08:00 | Expose read-only INT diagnostics to identify why the pre-sleep AON7 line remains active. */
void gsensor_sleep_motion_diag(void);
/* SAM | 2026-10-18 21:52 +08:00 | Service bounded motion waiting from QV idle without blocking event dispatch. */
bool gsensor_wait_poll(uint32_t now_ms);

#endif

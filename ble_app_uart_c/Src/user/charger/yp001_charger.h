#ifndef YP001_CHARGER_H
#define YP001_CHARGER_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t id;
    uint8_t vbus_type;       /* REG08[7:5] */
    uint8_t charge_state;    /* REG08[4:3] */
    bool power_good;         /* REG08[2] */
    bool thermal_limit;      /* REG08[1] */
    bool system_minimum;     /* REG08[0] */
    bool input_present;      /* REG0A[7] */
    bool input_voltage_limit;
    bool input_current_limit;
    uint8_t fault;          /* REG09, raw fault bits */
    uint16_t input_limit_ma; /* REG00, requested limit; not measured current */
    uint16_t charge_limit_ma;/* REG02, requested limit; not measured current */
    uint16_t charge_voltage_mv; /* REG04 setpoint; not measured voltage */
    /* SAM | 2026-10-09 12:20 +08:00 | Expose safety readback because
     * current/voltage alone cannot prove charging and watchdog are off. */
    uint8_t power_raw, pre_term_raw, timer_raw, fine_raw;
    uint8_t fault_history;
    uint16_t precharge_ma, termination_ma;
    /* SAM | 2026-11-12 22:40 +08:00 | Preserve REG00 bit5 because current-limit decoding hides the FAE diagnostic bit. */
    uint8_t input_raw;
} yp001_charger_status_t;

typedef struct {
    uint16_t input_limit_ma;
    uint16_t charge_limit_ma;
    uint16_t charge_voltage_mv;
} yp001_charger_profile_t;

/* Probe only. Does not change charger registers, nCE, nQON or the BATFET. */
bool yp001_charger_probe(void);
bool yp001_charger_read_status(yp001_charger_status_t *status);
/* SAM | 2026-11-12 22:40 +08:00 | Read power bytes before boot configuration and sleep without consuming REG09. */
bool yp001_charger_power_snapshot(const char *stage);

/* SAM | 2026-10-09 21:25 +08:00 | Boot verifies disabled parameters before
 * poll auto-starts on stable input. This is not a hardware power-on inhibit. */
bool yp001_charger_prepare_disabled(void);
/* SAM | 2026-10-09 14:48 +08:00 | Generic enable stays refused because
 * guarded manual bench testing has a separate bounded entry point. */
bool yp001_charger_apply_profile(const yp001_charger_profile_t *profile);
bool yp001_charger_set_enabled(bool enabled);
bool yp001_charger_test_start(void);
bool yp001_charger_test_stop(void);
void yp001_charger_tick_ms(uint32_t elapsed_ms);
void yp001_charger_poll(void);
/* SAM | 2026-10-09 21:25 +08:00 | Expose latched IC termination to UI. */
bool yp001_charger_is_complete(void);
/* SAM | 2026-10-10 09:04 +08:00 | Print retained stop evidence without
 * reading hardware; current status can be normal after a transient stop. */
void yp001_charger_print_diagnostic(void);
/* SAM | 2026-10-09 15:15 +08:00 | UI uses the safety sampler during tests
 * because extra REG09 reads could consume latched fault evidence. */
bool yp001_charger_display_status(yp001_charger_status_t *status);
/* SAM | 2026-11-07 07:14 +08:00 | Refresh only live supply fields without consuming the fault latch owned by charger poll. */
bool yp001_charger_live_input(yp001_charger_status_t *status);

/* SAM | 2026-10-13 14:03 +08:00 | Factory adapter-wake ship control;
 * lock is visible to CLI/business/display so no task restarts during cutoff. */
bool yp001_charger_ship_locked(void);
void yp001_charger_ship_key_sample(bool pressed);
/* SAM | 2026-11-08 20:30 +08:00 | One request owns the asynchronous job, including internal prepare and confirm. */
bool yp001_charger_ship_start(void);
void yp001_charger_ship_auto_snapshot(uint8_t *phase,const char **reason);
bool yp001_charger_ship_prepare(void);
bool yp001_charger_ship_confirm(uint32_t token);
bool yp001_charger_ship_cancel(void);
void yp001_charger_ship_status(void);
/* SAM | 2026-10-13 15:00 +08:00 | Structured RAM ship evidence for sealed
 * BLE testing; phase SENT is acceptance, never a measured zero-current claim. */
void yp001_charger_ship_snapshot(uint8_t *phase, uint32_t *token, bool *attempted);
/* SAM | 2026-10-13 15:28 +08:00 | BLE reads charger-owned evidence so it
 * cannot consume fault latches ahead of the safety poll. */
bool yp001_charger_cached_status(yp001_charger_status_t *status);

#endif

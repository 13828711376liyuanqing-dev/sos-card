#include "yp001_charger.h"

#include "app_i2c.h"
#include "app_io.h"
#include "gr_includes.h"
#include "yp001_board_config.h"
#include "cli.h"
#include "user_periph_setup.h"

#include <stddef.h>

/* SAM | 2026-10-13 14:03 +08:00 | Use tested ship controller and existing
 * business/OTA gates because factory cutoff must not interrupt live work. */
#include "yp001_shipping.h"
#include "../yp001_battery.h"
#include "../business/yp001_business.h"
#include "../ota/yp001_ota_port.h"
static yp_ship_t s_ship;
/* SAM | 2026-11-08 20:30 +08:00 | The automatic job is RAM-only and never resumes after reboot. */
static yp_ship_auto_t s_ship_auto;
static uint32_t s_ship_auto_poll_ms;
static bool s_ship_auto_internal;
static uint32_t s_ship_poll_ms;
static bool ship_business_guard(void);
static volatile bool s_ship_key_seen;


/* SAM | 2026-11-12 22:40 +08:00 | Match the measured board's 100mA profile because the sleep comparison must keep charging load consistent. */
#define FAST_CHARGE_CURRENT_VALUE 100U

/* ETA69631 Rev 1.9, pp. 23-30. These addresses differ from the older
 * eta69631.c register definitions in this repository. */
#define REG_INPUT       0x00U
#define REG_POWER       0x01U
#define REG_CURRENT     0x02U
#define REG_VOLTAGE     0x04U
#define REG_TIMER       0x05U
#define REG_STATUS      0x08U
#define REG_FAULT       0x09U
#define REG_DPM_STATUS  0x0AU
#define REG_PART_ID     0x0BU
#define PART_ID_MASK    0x7FU
#define PART_ID_VALUE   0x3FU
#define CHARGE_ENABLE   0x10U
/* SAM | 2026-10-09 12:20 +08:00 | Include pre/term and fine adjustment
 * because conservative setpoints require these fields to be verified. */
#define REG_PRE_TERM    0x03U
#define REG_FINE        0x0DU

static bool s_ready;
/* SAM | 2026-10-09 14:48 +08:00 | Bound an explicitly requested bench test
 * because boot must stay disabled and fault recovery must not restart it.
 * Only tick counter is ISR-owned; all I2C/state transitions are foreground. */
static volatile uint32_t s_test_clock_ms;
static bool s_test_active;
static bool s_stop_pending;
static uint32_t s_test_start_ms, s_test_poll_ms, s_test_log_ms;
/* SAM | 2026-10-09 21:25 +08:00 | Arm automatic charging only after boot
 * verification; latch stops until a confirmed unplug or explicit start.
 * Keep existing test_* API names for CLI compatibility. */
static bool s_auto_ready, s_auto_blocked, s_input_stable, s_input_absent;
static bool s_charge_complete;
static uint32_t s_input_since, s_absent_since;
/* SAM | 2026-10-09 15:15 +08:00 | Cache successful samples because UI
 * must not independently consume fault latches during a charging test. */
static yp001_charger_status_t s_display_status;
static uint32_t s_display_ms;
static bool s_display_valid;

/* SAM | 2026-10-10 09:04 +08:00 | Preserve the first stop evidence because
 * later REG09 reads and UI samples can hide the transient that caused it.
 * Foreground-only RAM record; successful start or MCU reset begins a new record. */
static const char *s_last_stop;
static yp001_charger_status_t s_stop_status;
static uint32_t s_stop_ms;
static bool s_stop_status_valid, s_stop_reported;

static void remember_stop(const char *reason, const yp001_charger_status_t *status)
{
    if (s_last_stop != NULL) return;
    s_last_stop = reason;
    s_stop_ms = s_test_clock_ms;
    s_stop_status_valid = status != NULL;
    if (status != NULL) s_stop_status = *status;
    s_stop_reported = false;
}

void yp001_charger_print_diagnostic(void)
{
    const yp001_charger_status_t *s = &s_stop_status;
    cli_printf("[CHG DIAG] ready=%u active=%u hold=%u stop_pending=%u last=%s at_ms=%lu snapshot=%u\r\n",
               (unsigned)s_auto_ready, (unsigned)s_test_active,
               (unsigned)s_auto_blocked, (unsigned)s_stop_pending,
               s_last_stop != NULL ? s_last_stop : "NONE",
               (unsigned long)s_stop_ms, (unsigned)s_stop_status_valid);
    if (!s_stop_status_valid) return;
    cli_printf("[CHG SNAP] ID=%02X VIN=%u PG=%u CHG=%u THERM=%u HIST=%02X NOW=%02X\r\n",
               s->id, s->input_present, s->power_good, s->charge_state,
               s->thermal_limit, s->fault_history, s->fault);
    cli_printf("[CHG SNAP] POWER=%02X TIMER=%02X PRETERM=%02X FINE=%02X IIN=%u ICHG=%u VREG=%u\r\n",
               s->power_raw, s->timer_raw, s->pre_term_raw, s->fine_raw,
               s->input_limit_ma, s->charge_limit_ma, s->charge_voltage_mv);
}

static app_i2c_params_t s_i2c = {
    .id = APP_I2C_ID_4,
    .role = APP_I2C_ROLE_MASTER,
    .pin_cfg = {
        .scl = { .type = YP001_CHARGER_I2C_TYPE,
                 .mux = YP001_CHARGER_SCL_MUX,
                 .pin = YP001_CHARGER_SCL_PIN, .pull = APP_IO_PULLUP },
        .sda = { .type = YP001_CHARGER_I2C_TYPE,
                 .mux = YP001_CHARGER_SDA_MUX,
                 .pin = YP001_CHARGER_SDA_PIN, .pull = APP_IO_PULLUP },
    },
    .dma_cfg = {
#if (APP_DRIVER_CHIP_TYPE == APP_DRIVER_GR5332X) || (APP_DRIVER_CHIP_TYPE == APP_DRIVER_GR551X)
        .tx_dma_instance = DMA0, .rx_dma_instance = DMA0,
#else
        .tx_dma_instance = DMA1, .rx_dma_instance = DMA1,
#endif
        .tx_dma_channel = DMA_Channel0,
        .rx_dma_channel = DMA_Channel1,
    },
    .init = {
        .speed = I2C_SPEED_100K,
        .own_address = 0,
        .addressing_mode = I2C_ADDRESSINGMODE_7BIT,
        .general_call_mode = I2C_GENERALCALL_DISABLE,
    },
};

static bool read_reg(uint8_t address, uint8_t *value)
{
    /* SAM | 2026-10-04 | Report transport errors separately from chip ID. */
    if (!s_ready || value == NULL) return false;
    uint16_t ret = app_i2c_mem_read_sync(APP_I2C_ID_4, YP001_CHARGER_ADDRESS,
                         address, I2C_MEMADD_SIZE_8BIT, value, 1U, 100U);
    if (ret != SDK_SUCCESS) {
        i2c_handle_t *h = app_i2c_get_handle(APP_I2C_ID_4);
        cli_printf("[CHG] reg=%02X ret=%04X hal=%08lX abort=%08lX SCL=%u SDA=%u\r\n",
                   address, ret, (unsigned long)h->error_code,
                   (unsigned long)h->p_instance->TX_ABORT_SRC,
                   app_io_read_pin(YP001_CHARGER_I2C_TYPE, YP001_CHARGER_SCL_PIN),
                   app_io_read_pin(YP001_CHARGER_I2C_TYPE, YP001_CHARGER_SDA_PIN));
    }
    return ret == SDK_SUCCESS;
}

static bool write_field(uint8_t address, uint8_t mask, uint8_t bits)
{
    uint8_t old_value;
    uint8_t new_value;
    uint8_t check;
    if (!read_reg(address, &old_value)) return false;
    new_value = (uint8_t)((old_value & (uint8_t)~mask) | (bits & mask));
    if (new_value == old_value) return true;
    if (app_i2c_mem_write_sync(APP_I2C_ID_4, YP001_CHARGER_ADDRESS,
                               address, I2C_MEMADD_SIZE_8BIT,
                               &new_value, 1U, 100U) != SDK_SUCCESS) {
        /* SAM | 2026-10-09 12:20 +08:00 | Identify failed writes because
         * partial configuration must not be reported as verified. */
        cli_printf("[CHG] WRITE FAILED reg=%02X\r\n", address);
        return false;
    }
    if (!read_reg(address, &check)) return false;
    if ((check & mask) != (new_value & mask)) {
        cli_printf("[CHG] VERIFY FAILED reg=%02X mask=%02X want=%02X got=%02X\r\n",
                   address, mask, new_value, check);
        return false;
    }
    return true;
}

bool yp001_charger_probe(void)
{
    uint8_t id;
    if (s_ready) return read_reg(REG_PART_ID, &id) &&
                        (id & PART_ID_MASK) == PART_ID_VALUE;
    /* SAM | 2026-10-04 | Identify init failures before blaming hardware. */
    uint16_t ret = app_i2c_init(&s_i2c, NULL);
    cli_printf("[CHG] I2C4 init=%04X\r\n", ret);
    if (ret != SDK_SUCCESS) return false;
    s_ready = true;
    bool id_read = read_reg(REG_PART_ID, &id);
    if (id_read) cli_printf("[CHG] REG0B=%02X expected masked ID=%02X\r\n", id, PART_ID_VALUE);
    if (!id_read || (id & PART_ID_MASK) != PART_ID_VALUE) {
        s_ready = false;
        app_i2c_deinit(APP_I2C_ID_4);
        return false;
    }
    return true;
}

bool yp001_charger_read_status(yp001_charger_status_t *status)
{
    uint8_t id, input, current, voltage, state, fault, dpm;
    /* SAM | 2026-10-09 12:20 +08:00 | Read actual safety fields and both
     * REG09 samples because its first read can contain historical faults. */
    uint8_t power, pre_term, timer, fine, history;
    /* SAM | 2026-10-09 15:15 +08:00 | Invalidate before I2C because
     * failed reads must not leave an apparently current screen status. */
    s_display_valid = false;
    if (status == NULL || !s_ready) return false;
    if (!read_reg(REG_PART_ID, &id) || (id & PART_ID_MASK) != PART_ID_VALUE ||
        !read_reg(REG_INPUT, &input) || !read_reg(REG_CURRENT, &current) ||
        !read_reg(REG_VOLTAGE, &voltage) || !read_reg(REG_STATUS, &state) ||
        !read_reg(REG_FAULT, &history) || !read_reg(REG_FAULT, &fault) ||
        !read_reg(REG_DPM_STATUS, &dpm) || !read_reg(REG_POWER, &power) ||
        !read_reg(REG_PRE_TERM, &pre_term) || !read_reg(REG_TIMER, &timer) ||
        !read_reg(REG_FINE, &fine)) return false;
    status->id = id;
    /* SAM | 2026-11-12 22:40 +08:00 | Keep the full input byte because 0x04 and 0x24 both decode to 500mA. */
    status->input_raw = input;
    status->vbus_type = (state >> 5U) & 0x07U;
    status->charge_state = (state >> 3U) & 0x03U;
    status->power_good = (state & 0x04U) != 0U;
    status->thermal_limit = (state & 0x02U) != 0U;
    status->system_minimum = (state & 0x01U) != 0U;
    status->input_present = (dpm & 0x80U) != 0U;
    status->input_voltage_limit = (dpm & 0x40U) != 0U;
    status->input_current_limit = (dpm & 0x20U) != 0U;
    status->fault = fault;
    status->input_limit_ma = (uint16_t)(100U + (input & 0x1FU) * 100U);
    status->charge_limit_ma = (uint16_t)(current * 20U);
    /* SAM | 2026-10-09 12:20 +08:00 | Include REG0D fine offset because
     * omitting it can hide an extra 5 mV in the programmed voltage. */
    status->charge_voltage_mv = (uint16_t)(4070U + ((voltage >> 2U) & 0x3FU) * 10U +
                                          ((fine & 0x80U) ? 5U : 0U));
    status->power_raw = power;
    status->pre_term_raw = pre_term;
    status->timer_raw = timer;
    status->fine_raw = fine;
    status->fault_history = history;
    status->precharge_ma = (uint16_t)(20U + (pre_term >> 4U) * 20U);
    status->termination_ma = (uint16_t)(20U + (pre_term & 0x0FU) * 20U);
    /* SAM | 2026-10-09 15:15 +08:00 | Publish only a complete sample. */
    s_display_status = *status;
    s_display_ms = s_test_clock_ms;
    s_display_valid = true;
    return true;
}

/* SAM | 2026-11-12 22:40 +08:00 | Capture pre-configuration power state because a reset can hide charging re-enable during sleep. */
bool yp001_charger_power_snapshot(const char *stage)
{
    uint8_t input, power, timer;
    if (!yp001_charger_probe() || !read_reg(REG_INPUT, &input) ||
        !read_reg(REG_POWER, &power) || !read_reg(REG_TIMER, &timer)) {
        cli_printf("[CHG RAW] stage=%s read_failed\r\n", stage);
        return false;
    }
    cli_printf("[CHG RAW] stage=%s REG00=%02X REG01=%02X REG05=%02X\r\n",
               stage, input, power, timer);
    return true;
}

/* SAM | 2026-10-09 15:15 +08:00 | Read-only display source; active test
 * ownership stays with poll(). Never configure or enable from the UI. */
/* SAM | 2026-11-07 07:14 +08:00 | Check current USB input/PG/thermal/OTG before OTA commit; never read REG_FAULT or change power settings. */
bool yp001_charger_live_input(yp001_charger_status_t *status)
{
    uint8_t state,dpm,power;
    if(!status||!s_ready||yp001_charger_ship_locked()||s_stop_pending)return false;
    if(!read_reg(REG_STATUS,&state)||!read_reg(REG_DPM_STATUS,&dpm)||!read_reg(REG_POWER,&power))return false;
    status->input_present=(dpm&0x80U)!=0U;
    status->power_good=(state&0x04U)!=0U;
    status->thermal_limit=(state&0x02U)!=0U;
    status->power_raw=power;
    return true;
}
bool yp001_charger_display_status(yp001_charger_status_t *status)
{
    /* SAM | 2026-10-13 14:03 +08:00 | Do not consume I2C during cutoff. */
    if (yp001_charger_ship_locked()) return false;
    if (status == NULL || s_stop_pending) return false;
    if (!s_test_active) return yp001_charger_read_status(status);
    if (!s_display_valid || (uint32_t)(s_test_clock_ms - s_display_ms) > 1000U)
        return false;
    *status = s_display_status;
    return true;
}

/* SAM | 2026-10-13 15:28 +08:00 | No bus access in factory telemetry;
 * fault history belongs to charger poll, and stale samples stay unknown. */
bool yp001_charger_cached_status(yp001_charger_status_t *status)
{
    if (!status || s_stop_pending || yp001_charger_ship_locked() || !s_display_valid ||
        (uint32_t)(s_test_clock_ms-s_display_ms)>1000U) return false;
    *status=s_display_status;
    return true;
}

bool yp001_charger_apply_profile(const yp001_charger_profile_t *profile)
{
    uint8_t input_bits, current_bits, voltage_bits;
    uint8_t power;
    /* SAM | 2026-10-13 14:03 +08:00 | Ship owns charger writes until recovery. */
    if (yp001_charger_ship_locked()) return false;
    if (!s_ready || profile == NULL) return false;
    /* Refuse unsupported or unreviewed settings. The cell and USB source
     * ratings must be checked before the caller uses this API on hardware. */
    if (profile->input_limit_ma < 100U || profile->input_limit_ma > 500U ||
        (profile->input_limit_ma % 100U) != 0U ||
        profile->charge_limit_ma < 20U || profile->charge_limit_ma > 500U ||
        (profile->charge_limit_ma % 20U) != 0U ||
        profile->charge_voltage_mv < 4070U || profile->charge_voltage_mv > 4200U ||
        (profile->charge_voltage_mv % 10U) != 0U) return false;
    /* Do not change voltage/current while autonomous charging or OTG is on. */
    if (!read_reg(REG_POWER, &power) || (power & 0x30U) != 0U) return false;
    input_bits = (uint8_t)((profile->input_limit_ma - 100U) / 100U);
    current_bits = (uint8_t)(profile->charge_limit_ma / 20U);
    voltage_bits = (uint8_t)(((profile->charge_voltage_mv - 4070U) / 10U) << 2U);
    /* SAM | 2026-10-09 14:48 +08:00 | Do not cache enable permission
     * because manual start must recheck the current hardware profile. */
    /* REG05[5:4] controls only the I2C watchdog. Keep REG05[3]
     * (the independent charge safety timer) unchanged. */
    if (!write_field(REG_TIMER, 0x30U, 0U) ||
        !write_field(REG_INPUT, 0x1FU, input_bits) ||
        !write_field(REG_CURRENT, 0xFFU, current_bits) ||
        !write_field(REG_VOLTAGE, 0xFCU, voltage_bits)) return false;
    return true;
}

/* SAM | 2026-10-09 12:20 +08:00 | Prepare a disabled 100mA/4.20V profile
 * because YQ452435 is 530mAh and NTC protection is not yet validated.
 * A successful return proves register readback only, not battery safety. */
bool yp001_charger_prepare_disabled(void)
{
    const yp001_charger_profile_t profile = { 500U, FAST_CHARGE_CURRENT_VALUE, 4200U };
    yp001_charger_status_t status;
    /* SAM | 2026-10-13 14:03 +08:00 | Preserve armed BATFET and timing. */
    if (yp001_charger_ship_locked()) return false;
    /* SAM | 2026-10-09 21:25 +08:00 | A later prepare is a stop request;
     * only the first successful boot prepare arms automatic operation. */
    if (s_auto_ready) s_auto_blocked = true;
    /* SAM | 2026-10-09 14:48 +08:00 | Stop a running test before preparing
     * because configuration commands must never prolong an active test. */
    if ((s_test_active || s_stop_pending) && !yp001_charger_test_stop()) return false;
    if (!yp001_charger_probe()) goto failed;
    if (!yp001_charger_set_enabled(false)) goto failed;
    /* Disable watchdog; enable termination and safety timer; keep other bits.
     * First inhibit charge so later configuration failures cannot enable it. */
    if (!write_field(REG_TIMER, 0xB8U, 0x88U) ||
        !write_field(REG_PRE_TERM, 0xFFU, 0U) ||
        !write_field(REG_FINE, 0x80U, 0U) ||
        !yp001_charger_apply_profile(&profile) ||
        !yp001_charger_read_status(&status)) goto failed;
    if ((status.power_raw & 0x30U) != 0U ||
        (status.timer_raw & 0xB8U) != 0x88U ||
        status.pre_term_raw != 0U || (status.fine_raw & 0x80U) != 0U ||
        status.input_limit_ma != 500U || status.charge_limit_ma != FAST_CHARGE_CURRENT_VALUE ||
        status.charge_voltage_mv != 4200U) {
        /* SAM | 2026-10-10 09:04 +08:00 | Capture mismatch before disabling. */
        remember_stop("PREPARE_PROFILE", &status);
        cli_printf("[CHG] FINAL PROFILE MISMATCH\r\n");
        goto failed;
    }
    /* SAM | 2026-10-09 21:25 +08:00 | Poll may start after stable input
     * because the user authorized automatic 100mA/4.20V charging. */
    s_auto_ready = true;
    cli_printf("[CHG] DISABLED PROFILE VERIFIED; auto %d mA/4200mV, hold=%u\r\n",
               FAST_CHARGE_CURRENT_VALUE,(unsigned)s_auto_blocked);
    return true;
failed:
    /* SAM | 2026-10-10 09:04 +08:00 | Invalid reads must not become snapshots. */
    remember_stop("PREPARE_IO_OR_PROFILE", NULL);
    /* SAM | 2026-10-09 21:25 +08:00 | Never auto-retry a failed profile. */
    s_auto_blocked = true;
    /* Best effort only: lost I2C cannot guarantee physical charge inhibition. */
    /* SAM | 2026-10-09 14:48 +08:00 | Latch an unconfirmed stop because
     * a lost I2C write must be retried and must block subsequent starts. */
    s_stop_pending = !yp001_charger_set_enabled(false);
    if (!s_stop_pending)
        cli_printf("[CHG] PREPARE FAILED; CHG_CONFIG=0 read back; keep battery disconnected\r\n");
    else
        cli_printf("[CHG] PREPARE FAILED; DISABLE NOT CONFIRMED; DISCONNECT BATTERY\r\n");
    return false;
}

bool yp001_charger_set_enabled(bool enabled)
{
    /* SAM | 2026-10-13 14:03 +08:00 | No generic writes while ship locked. */
    if (yp001_charger_ship_locked()) return false;
    /* SAM | 2026-10-09 21:25 +08:00 | Generic enable remains forbidden
     * because both automatic and CLI starts must use the checked entry. */
    if (enabled) return false;
    if (!s_ready) return false;
    /* nCE is tied low on YP001 A1 through R57. Do not drive nQON: R11 is NC. */
    return write_field(REG_POWER, CHARGE_ENABLE, 0U);
}

/* SAM | 2026-10-09 14:48 +08:00 | Room-temperature-only guard because
 * the user approved 100mA/4.20V attended tests, not production charging.
 * Reject ALL NTC states other than normal, including cool and warm.
 * Nominal normal window with R61=10k, R62 absent, B3435 is ~6..30C,
 * not a calibrated thermometer or proof of physical battery presence. */
static bool test_status_ok(const yp001_charger_status_t *status, bool enabled)
{
    return status->id == PART_ID_VALUE &&
           status->input_present && status->power_good &&
           status->fault == 0U && status->fault_history == 0U &&
           !status->thermal_limit &&
           (status->power_raw & 0x30U) == (enabled ? CHARGE_ENABLE : 0U) &&
           (status->timer_raw & 0xB8U) == 0x88U &&
           status->pre_term_raw == 0U && (status->fine_raw & 0x80U) == 0U &&
           status->input_limit_ma == 500U && status->charge_limit_ma == FAST_CHARGE_CURRENT_VALUE &&
           status->charge_voltage_mv == 4200U;
}

/* SAM | 2026-10-09 14:48 +08:00 | ISR does no I2C because blocking bus
 * operations must stay outside SysTick and QP interrupt locks. */
void yp001_charger_tick_ms(uint32_t elapsed_ms)
{
    s_test_clock_ms += elapsed_ms;
}

/* SAM | 2026-10-13 14:03 +08:00 | Restrict first ship test to offline,
 * unprovisioned factory bench because online flush/persistence is unvalidated.
 * GPIO readback is a request-state check, not measured CAT1 supply voltage. */
static bool ship_business_guard(void)
{
    const yp_business_status_t *b = yp_business_status();
    /* SAM | 2026-11-08 +08:00 | Factory pre-shipment configuration is forced: the single start owns the sequence, so business, key, link and
     * OTA-layout conditions do not apply. Only a live OTA transaction (never present before shipment) and the CAT1 rail the job itself forced off remain. */
    if (s_ship_auto.phase != YP_SHIP_AUTO_IDLE)
        return yp001_ota_power_change_allowed() && (GPIO0->DATAOUT & YP001_CAT1_POWER_PIN) == 0U;
    /* SAM | 2026-11-06 +08:00 | Ship cutoff cannot override the independent factory power hold. */
    return !yp001_cat1_factory_hold_active() && !s_ship_key_seen && !yp001_ota_port_provisioned() && yp001_ota_power_change_allowed() &&
        !b->alarm_active && !b->searching && !b->transport_ready &&
        b->call != YP_CALL_DIALING && b->call != YP_CALL_INCOMING &&
        b->call != YP_CALL_CONNECTED &&
        /* SAM | 2026-10-13 14:26 +08:00 | Check DATAOUT for output-owned
         * GPIO6 because input readback may be low while rail request is high. */
        (GPIO0->DATAOUT & YP001_CAT1_POWER_PIN) == 0U &&
        app_io_read_pin(YP001_KEY1_TYPE, YP001_KEY1_PIN) != APP_IO_PIN_RESET &&
        app_io_read_pin(YP001_KEY2_TYPE, YP001_KEY2_PIN) != APP_IO_PIN_RESET;
}

/* SAM | 2026-11-08 20:30 +08:00 | Preserve the existing offline/unprovisioned safety boundary until F-010 shutdown is implemented. */
static const char *ship_auto_guard(void)
{
    /* SAM | 2026-11-08 +08:00 | Forced factory shipment: the only refusal is a live OTA transaction (power would corrupt the install). */
    if (!yp001_ota_power_change_allowed()) return "OTA_guard";
    /* A running job has already forced CAT1 off; if the rail is still requested the force failed and nothing may be cut. */
    if (s_ship_auto.phase != YP_SHIP_AUTO_IDLE && (GPIO0->DATAOUT & YP001_CAT1_POWER_PIN) != 0U) return "CAT1_power_off_failed";
    return NULL;
}
/* SAM | 2026-11-08 +08:00 | Force the preconditions instead of refusing: release the factory power hold, drop the CAT1 rail request, clear the key latch.
 * Idempotent; called at job start and every poll tick so a later rail request (scan scheduler, other code) cannot defeat it. */
static void ship_force_cat1_off(void)
{
    if (!yp001_ota_power_change_allowed()) return;
    if (yp001_cat1_factory_hold_active()) {
        char command[]="cat1_power",release[]="hold_off";char *args[]={command,release};
        (void)cat1_debug_power(2,args);
    }
    if ((GPIO0->DATAOUT & YP001_CAT1_POWER_PIN)!=0U) {
        char command[]="cat1_power",off[]="off";char *args[]={command,off};
        (void)cat1_debug_power(2,args);
    }
    s_ship_key_seen=false;
}
static int ship_auto_usb(void)
{
    uint8_t status,dpm;
    if (!yp001_charger_probe() || !read_reg(REG_STATUS,&status) || !read_reg(REG_DPM_STATUS,&dpm)) return -1;
    return (status & 0xFCU) || (dpm & 0x80U) ? 1 : 0;
}
static bool ship_auto_prepare(void)
{
    uint16_t mv;
    /* A live reading after USB removal is required; a USB-powered sample cannot qualify this path. */
    ship_force_cat1_off();
    if (ship_auto_guard() || ship_auto_usb()!=0 || yp001_battery_read(&mv)!=YP001_BATTERY_OK) return false;
    s_ship_auto_internal=true;
    bool ok=yp001_charger_ship_prepare();
    s_ship_auto_internal=false;
    return ok;
}
static bool ship_auto_confirm(uint32_t token)
{
    s_ship_auto_internal=true;
    bool ok=yp001_charger_ship_confirm(token);
    s_ship_auto_internal=false;
    return ok;
}
static void ship_auto_cancel(void) { (void)yp001_charger_ship_cancel(); }
static const yp_ship_auto_port_t ship_auto_port={
    ship_auto_guard,ship_auto_usb,ship_auto_prepare,ship_auto_confirm,ship_auto_cancel
};
bool yp001_charger_ship_start(void)
{
    if (s_ship_auto.phase==YP_SHIP_AUTO_IDLE && yp_ship_locked(&s_ship)) return false;
    bool ok=yp_ship_auto_start(&s_ship_auto,s_test_clock_ms,&ship_auto_port);
    if (ok && yp_ship_auto_active(&s_ship_auto)) ship_force_cat1_off();   /* SAM | 2026-11-08 +08:00 | forced, not refused */
    yp001_charger_ship_status();
    return ok;
}
void yp001_charger_ship_auto_snapshot(uint8_t *phase,const char **reason)
{
    *phase=(uint8_t)s_ship_auto.phase;
    *reason=s_ship_auto.reason?s_ship_auto.reason:"idle";
}

bool yp001_charger_ship_locked(void) { return yp_ship_locked(&s_ship); }
/* SAM | 2026-10-13 15:00 +08:00 | Read-only state access without parsing UART logs. */
void yp001_charger_ship_snapshot(uint8_t *phase, uint32_t *token, bool *attempted)
{
    if (phase) *phase=(uint8_t)s_ship.phase;
    if (token) *token=s_ship.token;
    if (attempted) *attempted=s_ship.disconnect_attempted;
}

/* SAM | 2026-10-13 14:15 +08:00 | Latch presses at 10ms even when normal
 * business is suspended because a short press can fall between bus polls. */
void yp001_charger_ship_key_sample(bool pressed)
{
    if (yp001_charger_ship_locked() && pressed) s_ship_key_seen = true;
}

/* SAM | 2026-10-13 14:15 +08:00 | Recheck key/input immediately before
 * final bus write because generic read-modify-write can block after guard. */
static bool ship_write_field(uint8_t reg, uint8_t mask, uint8_t bits)
{
    uint8_t old, state, dpm, check;
    if (!read_reg(reg, &old) || !read_reg(REG_STATUS, &state) ||
        !read_reg(REG_DPM_STATUS, &dpm) || (state & 0xFCU) || (dpm & 0x80U) ||
        !ship_business_guard()) return false;
    uint8_t value = (uint8_t)((old & (uint8_t)~mask) | (bits & mask));
    if (value == old) return true;
    if (app_i2c_mem_write_sync(APP_I2C_ID_4, YP001_CHARGER_ADDRESS,
        reg, I2C_MEMADD_SIZE_8BIT, &value, 1U, 100U) != SDK_SUCCESS) return false;
    return read_reg(reg, &check) && (check & mask) == (value & mask);
}

void yp001_charger_ship_status(void)
{
    if (s_ship_auto.phase!=YP_SHIP_AUTO_IDLE) {
        static const char *const jobs[]={"IDLE","CHECKING","SENT","FAILED","UNKNOWN","WAIT_USB_REMOVED"};
        cli_printf("[SHIP] auto=%s reason=%s attempted=%u\r\n",jobs[s_ship_auto.phase],
            s_ship_auto.reason?s_ship_auto.reason:"idle",(unsigned)s_ship.disconnect_attempted);
    }
    static const char *const names[] = { "IDLE", "CHECKING", "READY", "SENT", "FAILED" };
    cli_printf("[SHIP] state=%s token=%lu attempted=%u reason=%s\r\n",
        names[s_ship.phase], (unsigned long)s_ship.token,
        (unsigned)s_ship.disconnect_attempted, s_ship.reason ? s_ship.reason : "not requested");
    /* SAM | 2026-10-13 14:03 +08:00 | Raw pre-write evidence without
     * consuming REG09 fault history; never poll an already-cut supply. */
    if (!s_ship.disconnect_attempted && yp001_charger_probe()) {
        uint8_t ship, fine, state, dpm;
        if (read_reg(7U, &ship) && read_reg(REG_FINE, &fine) &&
            read_reg(REG_STATUS, &state) && read_reg(REG_DPM_STATUS, &dpm))
            cli_printf("[SHIP] REG07=%02X REG0D=%02X REG08=%02X REG0A=%02X\r\n", ship, fine, state, dpm);
    }
    if (s_ship.phase == YP_SHIP_READY && s_ship_auto.phase==YP_SHIP_AUTO_IDLE)
        cli_printf("[SHIP] confirm within 30s: charger ship confirm %lu\r\n", (unsigned long)s_ship.token);
    if (s_ship.disconnect_attempted)
        cli_printf("[SHIP] no cancel/retry; measure SYS and battery current; insert 5V to restore\r\n");
}

bool yp001_charger_ship_prepare(void)
{
    /* SAM | 2026-11-08 20:30 +08:00 | A running automatic job owns its internal token. */
    if (s_ship_auto.phase!=YP_SHIP_AUTO_IDLE && !s_ship_auto_internal) return false;
    /* SAM | 2026-10-13 14:15 +08:00 | Reject qualification read-only before
     * stopping charge; a refused ship command must not change charge hold. */
    if (!yp001_charger_ship_locked()) s_ship_key_seen = false;
    if (yp001_charger_ship_locked() || !s_test_clock_ms || !ship_business_guard() ||
        !yp001_charger_probe()) {
        cli_printf("[SHIP] prepare refused: lock/tick/offline/key/OTA/ID guard\r\n");
        return false;
    }
    if (!yp_ship_check(&s_ship, read_reg, ship_business_guard)) {
        if (s_ship.disconnect_attempted) s_ship.phase = YP_SHIP_FAILED;
        yp001_charger_ship_status();
        return false;
    }
    /* Stop charging before acquiring the ship lock; do not reconfigure profile. */
    if (!yp001_charger_test_stop()) return false;
    bool ok = yp_ship_prepare(&s_ship, s_test_clock_ms, read_reg, ship_business_guard);
    s_ship_poll_ms = s_test_clock_ms;
    yp001_charger_ship_status();
    return ok;
}

bool yp001_charger_ship_confirm(uint32_t token)
{
    /* SAM | 2026-11-08 20:30 +08:00 | Legacy confirmation cannot race the automatic coordinator. */
    if (s_ship_auto.phase!=YP_SHIP_AUTO_IDLE && !s_ship_auto_internal) return false;
    bool ok = yp_ship_confirm(&s_ship, token, s_test_clock_ms,
                             read_reg, ship_write_field, ship_business_guard);
    if (ok) cli_printf("[SHIP] BATFET_DIS readback=1; delay ~12s; accepted, physical cutoff UNVERIFIED\r\n");
    else cli_printf("[SHIP] confirm refused or write unconfirmed\r\n");
    yp001_charger_ship_status();
    return ok;
}

bool yp001_charger_ship_cancel(void)
{
    bool ok = yp_ship_cancel(&s_ship);
    if (ok) {
        if (yp_ship_auto_active(&s_ship_auto)) {
            s_ship_auto.phase=YP_SHIP_AUTO_FAILED;
            s_ship_auto.reason="cancelled";
        }
        /* Retain a charge hold and restart ordinary input qualification. */
        s_auto_blocked = true;
        s_input_absent = s_input_stable = false;
        s_ship_key_seen = false;
    }
    yp001_charger_ship_status();
    return ok;
}

/* SAM | 2026-10-09 14:48 +08:00 | Invalidate the run before bus access
 * because a failed stop must never leave software authorized to restart. */
bool yp001_charger_test_stop(void)
{
    /* SAM | 2026-10-13 14:03 +08:00 | Cutoff lock supersedes normal stop retries. */
    if (yp001_charger_ship_locked()) return false;
    /* SAM | 2026-10-10 09:04 +08:00 | Keep a prior fault reason on retries;
     * calls without a captured fault are explicit/requested stops. */
    remember_stop("REQUESTED_STOP", NULL);
    /* SAM | 2026-10-09 21:25 +08:00 | Manual/fault/completion stops hold
     * charging off while the same input remains connected. */
    s_auto_blocked = true;
    s_input_stable = false;
    s_test_active = false;
    s_stop_pending = true;
    if (!s_ready && !yp001_charger_probe()) {
        cli_printf("[CHG] STOP NOT CONFIRMED: probe failed; DISCONNECT BATTERY\r\n");
        return false;
    }
    if (!yp001_charger_set_enabled(false)) {
        cli_printf("[CHG] STOP NOT CONFIRMED; DISCONNECT BATTERY; no automatic restart\r\n");
        return false;
    }
    s_stop_pending = false;
    cli_printf("[CHG] STOP VERIFIED CHG_EN=0 (register readback, not current measurement)\r\n");
    /* SAM | 2026-10-10 09:04 +08:00 | Print only after the disable write so
     * detailed diagnostics do not delay the charge-stop operation. */
    if (!s_stop_reported) {
        yp001_charger_print_diagnostic();
        s_stop_reported = true;
    }
    return true;
}

/* SAM | 2026-10-09 14:48 +08:00 | Each manual request revalidates all
 * limits because cached setpoints cannot detect charger reset or drift. */
bool yp001_charger_test_start(void)
{
    yp001_charger_status_t status;
    /* SAM | 2026-10-13 14:03 +08:00 | Both manual and auto starts respect ship. */
    if (yp001_charger_ship_locked()) return false;
    if (s_test_active) {
        /* SAM | 2026-10-09 21:25 +08:00 | Do not disturb active charging. */
        cli_printf("[CHG] CHARGE already active\r\n");
        return false;
    }
    if (s_stop_pending || s_test_clock_ms == 0U) {
        cli_printf("[CHG] START BLOCKED: unresolved stop or tick not running\r\n");
        return false;
    }
    /* SAM | 2026-10-10 09:04 +08:00 | A failed read leaves id zero; this
     * prevents an incomplete status from being saved as valid evidence. */
    status.id = 0U;
    if (!yp001_charger_prepare_disabled() ||
        !yp001_charger_read_status(&status) || !test_status_ok(&status, false)) {
        remember_stop("START_GUARD", status.id == PART_ID_VALUE ? &status : NULL);
        cli_printf("[CHG] START BLOCKED: supply/NTC/fault/profile check failed\r\n");
        (void)yp001_charger_test_stop();
        return false;
    }
    s_test_start_ms = s_test_clock_ms;
    /* SAM | 2026-10-10 09:04 +08:00 | Do not retain the pre-enable sample
     * when the enable write or subsequent read fails. */
    status.id = 0U;
    if (!write_field(REG_POWER, CHARGE_ENABLE, CHARGE_ENABLE) ||
        !yp001_charger_read_status(&status) || !test_status_ok(&status, true)) {
        remember_stop("ENABLE_OR_GUARD", status.id == PART_ID_VALUE ? &status : NULL);
        cli_printf("[CHG] START FAILED; stopping\r\n");
        (void)yp001_charger_test_stop();
        return false;
    }
    /* SAM | 2026-10-10 09:04 +08:00 | Clear old evidence only after a
     * verified new charge start; status reads/unplug keep the old record. */
    s_last_stop = NULL;
    s_stop_status_valid = false;
    s_stop_reported = false;
    s_stop_ms = 0U;
    s_test_active = true;
    /* SAM | 2026-10-09 21:25 +08:00 | Clear holds only after checked start. */
    s_auto_blocked = false;
    s_charge_complete = false;
    s_test_poll_ms = s_test_clock_ms;
    s_test_log_ms = s_test_clock_ms;
    /* SAM | 2026-10-09 21:25 +08:00 | Remove bench deadline because IC
     * termination and safety timer now bound the requested charge cycle. */
    cli_printf("[CHG] CHARGE STARTED: %d mA/4200mV; IC termination/safety timer; keep attended\r\n",FAST_CHARGE_CURRENT_VALUE);
    return true;
}

/* SAM | 2026-10-09 14:48 +08:00 | Poll from unlocked foreground because
 * NTC faults, input loss, I2C failure or register drift must stop the test.
 * This is best-effort software, not independent hardware protection. */
void yp001_charger_poll(void)
{
    uint32_t now = s_test_clock_ms;
    yp001_charger_status_t status;
    /* SAM | 2026-11-08 20:30 +08:00 | Waiting does not acquire the ship lock or suspend OTA/business dispatch. */
    if (yp_ship_auto_active(&s_ship_auto) && (uint32_t)(now-s_ship_auto_poll_ms)>=250U) {
        s_ship_auto_poll_ms=now;
        if (!s_ship.disconnect_attempted) ship_force_cat1_off();
        yp_ship_auto_phase_t before=s_ship_auto.phase;
        yp_ship_auto_poll(&s_ship_auto,&s_ship,now,&ship_auto_port);
        if (before!=s_ship_auto.phase) yp001_charger_ship_status();
    }
    /* SAM | 2026-10-13 14:03 +08:00 | Sample only qualification; after an
     * attempted cutoff never retry charger writes or infer SYS from I2C. */
    if (yp001_charger_ship_locked()) {
        if ((uint32_t)(now - s_ship_poll_ms) >= 250U) {
            yp_ship_phase_t before = s_ship.phase;
            s_ship_poll_ms = now;
            yp_ship_poll(&s_ship, now, read_reg, ship_business_guard);
            if (before != s_ship.phase) yp001_charger_ship_status();
        }
        return;
    }
    /* SAM | 2026-10-09 21:25 +08:00 | Poll idle input as well as charging
     * because a stable 5V insertion must start a new verified cycle. */
    if (!s_auto_ready && !s_stop_pending) return;
    if ((uint32_t)(now - s_test_poll_ms) < 250U) return;
    s_test_poll_ms = now;
    if (s_stop_pending) {
        (void)yp001_charger_test_stop();
        return;
    }
    if (!yp001_charger_read_status(&status)) {
        /* SAM | 2026-10-10 09:04 +08:00 | I2C failure has no valid snapshot. */
        remember_stop("I2C_READ", NULL);
        cli_printf("[CHG] I2C FAULT; stopping and holding\r\n");
        (void)yp001_charger_test_stop();
        return;
    }
    /* A confirmed 2s absence rearms insertion; a PG glitch alone does not. */
    if (!status.input_present && !status.power_good) {
        s_input_stable = false;
        if (s_test_active || (status.power_raw & CHARGE_ENABLE) != 0U) {
            /* SAM | 2026-10-10 09:04 +08:00 | Save both input flags at loss. */
            remember_stop("INPUT_REMOVED", &status);
            cli_printf("[CHG] INPUT REMOVED; stopping\r\n");
            (void)yp001_charger_test_stop();
            s_input_absent = false;
            return;
        }
        if (!s_input_absent) {
            s_input_absent = true;
            s_absent_since = now;
        }
        if ((uint32_t)(now - s_absent_since) >= 2000U) {
            if (s_auto_blocked) cli_printf("[CHG] INPUT ABSENT; auto rearmed\r\n");
            s_auto_blocked = false;
            s_charge_complete = false;
        }
        return;
    }
    s_input_absent = false;
    if (!s_test_active) {
        /* SAM | 2026-10-09 21:25 +08:00 | A held cycle must also detect
         * an unexpected IC reset that re-enables charging. */
        if (s_auto_blocked) {
            if ((status.power_raw & CHARGE_ENABLE) != 0U)
                (void)yp001_charger_test_stop();
            return;
        }
        if (!status.input_present || !status.power_good) {
            s_input_stable = false;
            return;
        }
        if (status.fault != 0U || status.fault_history != 0U || status.thermal_limit) {
            /* SAM | 2026-10-10 09:04 +08:00 | Preserve history before UI reads. */
            remember_stop("AUTO_FAULT", &status);
            cli_printf("[CHG] AUTO BLOCKED: NTC/fault; unplug or explicit start after repair\r\n");
            (void)yp001_charger_test_stop();
            return;
        }
        if (!s_input_stable) {
            s_input_stable = true;
            s_input_since = now;
        }
        if ((uint32_t)(now - s_input_since) >= 2000U) {
            s_input_stable = false;
            cli_printf("[CHG] INPUT STABLE; auto start\r\n");
            (void)yp001_charger_test_start();
        }
        return;
    }
    if (!test_status_ok(&status, true)) {
        /* SAM | 2026-10-10 09:04 +08:00 | Save all guard inputs for diagnosis. */
        remember_stop("RUN_GUARD", &status);
        cli_printf("[CHG] CHARGE FAULT: supply/NTC/profile; stopping, no restart\r\n");
        (void)yp001_charger_test_stop();
        return;
    }
    if (status.charge_state == 3U) {
        /* SAM | 2026-10-10 09:04 +08:00 | Distinguish termination from faults. */
        remember_stop("IC_TERMINATION", &status);
        cli_printf("[CHG] IC reports termination; stopping (not capacity acceptance)\r\n");
        (void)yp001_charger_test_stop();
        s_charge_complete = true;
        return;
    }
    if ((uint32_t)(now - s_test_log_ms) >= 5000U) {
        s_test_log_ms = now;
        /* SAM | 2026-11-12 22:40 +08:00 | Print register readback because the prior fixed 100mA text could conceal a changed profile. */
        cli_printf("[CHG] CHARGE elapsed=%lus CHG=%u FAULT=%02X (setpoints %umA/%umV)\r\n",
                   (unsigned long)((now - s_test_start_ms) / 1000U),
                   status.charge_state, status.fault,
                   status.charge_limit_ma, status.charge_voltage_mv);
    }
}

/* SAM | 2026-10-09 21:25 +08:00 | Retain completion after CHG_EN clears
 * because the IC state may then return to idle before the screen updates. */
bool yp001_charger_is_complete(void)
{
    return s_charge_complete && !s_stop_pending;
}

/* SAM | 2026-10-04 | Board bring-up: distinguish motor rail/reset/I2C
 * reachability from waveform playback. Guide V1.0 p7: address 0x5A,
 * RSTN low shuts down. No waveform or drive registers are written. */
static int cmd_motor_probe(int argc, char *argv[])
{
    (void)argv;
    if (argc != 1) return -1;
    app_io_init_t io = APP_IO_DEFAULT_CONFIG;
    io.mode = APP_IO_MODE_OUTPUT;
    io.pull = APP_IO_NOPULL;
    io.mux = YP001_GPIO_GPIO_MUX;
    io.pin = YP001_MOTOR_RESET_PIN;
    if (app_io_init(YP001_MOTOR_RESET_TYPE, &io) != APP_DRV_SUCCESS) return -1;
    app_io_write_pin(YP001_MOTOR_RESET_TYPE, YP001_MOTOR_RESET_PIN, APP_IO_PIN_RESET);
    io.pin = YP001_MOTOR_POWER_PIN;
    if (app_io_init(YP001_MOTOR_POWER_TYPE, &io) != APP_DRV_SUCCESS) return -1;
    app_io_write_pin(YP001_MOTOR_POWER_TYPE, YP001_MOTOR_POWER_PIN, APP_IO_PIN_SET);
    delay_ms(10);
    app_io_write_pin(YP001_MOTOR_RESET_TYPE, YP001_MOTOR_RESET_PIN, APP_IO_PIN_SET);
    delay_ms(10);
    app_i2c_params_t motor = s_i2c;
    motor.id = APP_I2C_ID_3;
    motor.pin_cfg.scl.type = YP001_MOTOR_I2C_TYPE;
    motor.pin_cfg.sda.type = YP001_MOTOR_I2C_TYPE;
    motor.pin_cfg.scl.pin = YP001_MOTOR_SCL_PIN;
    motor.pin_cfg.sda.pin = YP001_MOTOR_SDA_PIN;
    motor.pin_cfg.scl.mux = YP001_MOTOR_I2C_MUX;
    motor.pin_cfg.sda.mux = YP001_MOTOR_I2C_MUX;
    uint16_t ret = app_i2c_init(&motor, NULL);
    cli_printf("[MOTOR] I2C3 init=%04X, GPIO26/27 requested HIGH\r\n", ret);
    if (ret == APP_DRV_SUCCESS) {
        uint8_t raw = 0;
        ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, 0U,
                                  I2C_MEMADD_SIZE_8BIT, &raw, 1U, 100U);
        cli_printf("[MOTOR] addr=5A reg00 raw=%02X ret=%04X (not an ID verdict)\r\n", raw, ret);
        /* SAM | 2026-10-04 | Capture timeout cause before driver deinit. */
        i2c_handle_t *h = app_i2c_get_handle(APP_I2C_ID_3);
        cli_printf("[MOTOR] hal=%08lX abort=%08lX SCL=%u SDA=%u\r\n",
                   (unsigned long)h->error_code, (unsigned long)h->p_instance->TX_ABORT_SRC,
                   app_io_read_pin(YP001_MOTOR_I2C_TYPE, YP001_MOTOR_SCL_PIN),
                   app_io_read_pin(YP001_MOTOR_I2C_TYPE, YP001_MOTOR_SDA_PIN));
        app_i2c_deinit(APP_I2C_ID_3);
    }
    app_io_write_pin(YP001_MOTOR_RESET_TYPE, YP001_MOTOR_RESET_PIN, APP_IO_PIN_RESET);
    app_io_write_pin(YP001_MOTOR_POWER_TYPE, YP001_MOTOR_POWER_PIN, APP_IO_PIN_RESET);
    cli_printf("[MOTOR] probe ended; reset asserted, rail requested OFF\r\n");
    return ret == APP_DRV_SUCCESS ? 0 : -1;
}
CLI_CMD_REGISTER("motor_probe", "Probe AW86233 I2C; no vibration", cmd_motor_probe);

/* SAM | 2026-10-12 11:48 +08:00 | Add one bounded low-level CONT pulse
 * because the fitted motor needs a physical function check at I2C3 100kHz.
 * AW8623X DS V1.4: 0x2330=AW86233, CONT avoids RTP's >=250kHz limit. */
static bool motor_test_write(uint8_t reg, uint8_t value)
{
    uint16_t ret = app_i2c_mem_write_sync(APP_I2C_ID_3, 0x5AU, reg,
                                          I2C_MEMADD_SIZE_8BIT, &value, 1U, 100U);
    cli_printf("[MOTOR TEST] W %02X=%02X ret=%04X\r\n", reg, value, ret);
    if (ret != APP_DRV_SUCCESS) return false;
    if (reg == 0x09U) return true; /* GO/STOP are write-command bits. */
    uint8_t readback = 0;
    ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, reg,
                                I2C_MEMADD_SIZE_8BIT, &readback, 1U, 100U);
    cli_printf("[MOTOR TEST] R %02X=%02X ret=%04X\r\n", reg, readback, ret);
    return ret == APP_DRV_SUCCESS && readback == value;
}

static int cmd_motor_test(int argc, char *argv[])
{
    (void)argv;
    if (argc != 1) {
        cli_printf("Usage: motor_test\r\n");
        return -1;
    }
    app_io_init_t io = APP_IO_DEFAULT_CONFIG;
    io.mode = APP_IO_MODE_OUTPUT;
    io.pull = APP_IO_NOPULL;
    io.mux = YP001_GPIO_GPIO_MUX;
    io.pin = YP001_MOTOR_RESET_PIN;
    if (app_io_init(YP001_MOTOR_RESET_TYPE, &io) != APP_DRV_SUCCESS) return -1;
    app_io_write_pin(YP001_MOTOR_RESET_TYPE, YP001_MOTOR_RESET_PIN, APP_IO_PIN_RESET);
    io.pin = YP001_MOTOR_POWER_PIN;
    if (app_io_init(YP001_MOTOR_POWER_TYPE, &io) != APP_DRV_SUCCESS) return -1;
    app_io_write_pin(YP001_MOTOR_POWER_TYPE, YP001_MOTOR_POWER_PIN, APP_IO_PIN_SET);
    delay_ms(10);
    app_io_write_pin(YP001_MOTOR_RESET_TYPE, YP001_MOTOR_RESET_PIN, APP_IO_PIN_SET);
    delay_ms(10);

    app_i2c_params_t motor = s_i2c;
    motor.id = APP_I2C_ID_3;
    motor.pin_cfg.scl.type = YP001_MOTOR_I2C_TYPE;
    motor.pin_cfg.sda.type = YP001_MOTOR_I2C_TYPE;
    motor.pin_cfg.scl.pin = YP001_MOTOR_SCL_PIN;
    motor.pin_cfg.sda.pin = YP001_MOTOR_SDA_PIN;
    motor.pin_cfg.scl.mux = YP001_MOTOR_I2C_MUX;
    motor.pin_cfg.sda.mux = YP001_MOTOR_I2C_MUX;
    uint16_t ret = app_i2c_init(&motor, NULL);
    bool i2c_ready = ret == APP_DRV_SUCCESS;
    bool go_issued = false;
    bool ok = false;
    cli_printf("[MOTOR TEST] I2C3 init=%04X\r\n", ret);
    if (i2c_ready) {
        uint8_t idh = 0, idl = 0, status = 0, state = 0;
        ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, 0x57U,
                                    I2C_MEMADD_SIZE_8BIT, &idh, 1U, 100U);
        if (ret == APP_DRV_SUCCESS)
            ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, 0x69U,
                                        I2C_MEMADD_SIZE_8BIT, &idl, 1U, 100U);
        cli_printf("[MOTOR TEST] CHIPID=%02X%02X ret=%04X expect=2330\r\n", idh, idl, ret);
        if (ret == APP_DRV_SUCCESS && idh == 0x23U && idl == 0x30U) {
            ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, 0x01U,
                                        I2C_MEMADD_SIZE_8BIT, &status, 1U, 100U);
            cli_printf("[MOTOR TEST] SYSST=%02X ret=%04X\r\n", status, ret);
            if (ret == APP_DRV_SUCCESS && (status & 0x26U) == 0U &&
                motor_test_write(0x18U, 0x8DU) && /* F_PRE ~170Hz */
                motor_test_write(0x1CU, 0x20U) && /* no tracking, ~25% VDD */
                motor_test_write(0x1DU, 0x90U) && /* reserved bit + 12.5% VDD */
                motor_test_write(0x1EU, 0x10U) && /* 16 half cycles */
                motor_test_write(0x1FU, 0x18U) && /* 24 half cycles */
                motor_test_write(0x08U, 0x0AU) && /* immediate stop, CONT */
                motor_test_write(0x09U, 0x01U)) {
                go_issued = true;
                delay_ms(10);
                ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, 0x3FU,
                                            I2C_MEMADD_SIZE_8BIT, &state, 1U, 100U);
                cli_printf("[MOTOR TEST] GLB_STATE@10ms=%02X ret=%04X\r\n", state, ret);
                delay_ms(110);
                /* SAM | 2026-10-12 11:48 +08:00 | Require the chip's
                 * CONT state so an ACK alone cannot be called playback. */
                ok = ret == APP_DRV_SUCCESS && (state & 0x0FU) == 0x06U;
            }
        }
        /* SAM | 2026-10-12 11:48 +08:00 | Always request STOP before
         * rail-off, including an I2C error after GO. */
        if (go_issued && !motor_test_write(0x09U, 0x02U)) ok = false;
        ret = app_i2c_mem_read_sync(APP_I2C_ID_3, 0x5AU, 0x01U,
                                    I2C_MEMADD_SIZE_8BIT, &status, 1U, 100U);
        cli_printf("[MOTOR TEST] SYSST after=%02X ret=%04X\r\n", status, ret);
        if (ret != APP_DRV_SUCCESS || (status & 0x26U) != 0U) ok = false;
        app_i2c_deinit(APP_I2C_ID_3);
    }
    app_io_write_pin(YP001_MOTOR_RESET_TYPE, YP001_MOTOR_RESET_PIN, APP_IO_PIN_RESET);
    app_io_write_pin(YP001_MOTOR_POWER_TYPE, YP001_MOTOR_POWER_PIN, APP_IO_PIN_RESET);
    cli_printf("[MOTOR TEST] %s; reset asserted, rail requested OFF; feel/observe motor\r\n",
               ok ? "COMMAND OK" : "FAILED");
    return ok ? 0 : -1;
}
CLI_CMD_REGISTER("motor_test", "One low-level 120ms AW86233 CONT pulse", cmd_motor_test);

/* SAM | 2026-10-10 10:28 +08:00 | Add a manual read-only I2C probe
 * because DA215 communication must be verified before configuring motion.
 * Address source: FAE clarification 2026-10-10; CHIPID register is 0x01.
 * This command reuses I2C0; it does not change rails or sensor registers.
 */
#include "cli.h"
#include "app_i2c.h"
#include "app_io.h"
#include "app_gpiote.h"
#include "qpc.h"
#include "sensor.h"
#include "gr55xx_ll_aon_gpio.h"
#include "yp001_board_config.h"
/* SAM | 2026-10-10 11:35 +08:00 | Export the LCD sampling contract. */
#include "gsensor_probe.h"

/* SAM | 2026-10-18 18:57 +08:00 | Keep the probe at the board-verified 0x26 address, now shared with production config because SA0 is pulled low on YP001. */
#define GSENSOR_PROBE_ADDR 0x26U
extern void DA221_gpio_int_callback(app_io_evt_t *p_evt);

static int cmd_gsensor_probe(int argc, char *argv[])
{
    (void)argv;
    if (argc != 1) {
        cli_printf("Usage: gsensor_probe\r\n");
        return -1;
    }

    i2c_handle_t *h = app_i2c_get_handle(APP_I2C_ID_0);
    cli_printf("[GS] GPIO7=%u SCL2=%u SDA3=%u INT=%u (logic, not voltage)\r\n",
               app_io_read_pin(YP001_SENSOR_POWER_TYPE, YP001_SENSOR_POWER_PIN),
               app_io_read_pin(YP001_SENSOR_I2C_TYPE, YP001_SENSOR_SCL_PIN),
               app_io_read_pin(YP001_SENSOR_I2C_TYPE, YP001_SENSOR_SDA_PIN),
               app_io_read_pin(YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN));
    if (h == NULL) {
        cli_printf("[GS] I2C0 not initialized; no probe performed\r\n");
        return -1;
    }

    unsigned int ok = 0;
    for (unsigned int n = 0; n < 5U; ++n) {
        if (hal_i2c_get_state(h) != HAL_I2C_STATE_READY) {
            cli_printf("[GS] I2C0 not ready, state=%02X; probe stopped\r\n",
                       (unsigned int)hal_i2c_get_state(h));
            return -1;
        }
        uint8_t id = 0xFFU;
        uint16_t ret = app_i2c_mem_read_sync(APP_I2C_ID_0, GSENSOR_PROBE_ADDR, 0x01U,
                                           I2C_MEMADD_SIZE_8BIT, &id, 1U, 100U);
        /* Capture diagnostics before logging or starting another transfer. */
        uint32_t error = h->error_code;
        uint32_t abort_src = h->p_instance->TX_ABORT_SRC;
        bool valid = ret == APP_DRV_SUCCESS;
        if (valid && id == 0x13U) ++ok;
        cli_printf("[GS] n=%u addr7=%02X reg=01 ret=%04X valid=%u raw=%02X hal=%08lX abort=%08lX SCL=%u SDA=%u\r\n",
                   n + 1U, GSENSOR_PROBE_ADDR, ret, valid, id, (unsigned long)error,
                   (unsigned long)abort_src,
                   app_io_read_pin(YP001_SENSOR_I2C_TYPE, YP001_SENSOR_SCL_PIN),
                   app_io_read_pin(YP001_SENSOR_I2C_TYPE, YP001_SENSOR_SDA_PIN));
    }
    cli_printf("[GS] ID13=%u/5 %s (I2C/ID only; no motion acceptance)\r\n",
               ok, ok == 5U ? "PASS" : "FAIL");
    return ok == 5U ? 0 : -1;
}

/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_probe", "Read DA215 ID x5", cmd_gsensor_probe);

/* SAM | 2026-10-10 11:12 +08:00 | Add bounded XYZ measurements because
 * CHIPID alone cannot verify acceleration. DS_da215 Rev0.3 pp20-23:
 * left-justified signed 14-bit, +/-2g=4096 LSB/g, ODR code 5=31.25Hz.
 * Save/restore configuration and preserve reserved bits and axis polarity. */
#include "gr55xx_delay.h"

static int16_t gsensor_decode14(uint8_t low, uint8_t high)
{
    int32_t value = (((uint32_t)high << 8) | low) >> 2;
    if (value >= 8192) value -= 16384;
    return (int16_t)value;
}

static bool gsensor_xyz_read(uint8_t reg, uint8_t *data, uint16_t size)
{
    uint16_t ret = app_i2c_mem_read_sync(APP_I2C_ID_0, GSENSOR_PROBE_ADDR,
                                        reg, I2C_MEMADD_SIZE_8BIT, data, size, 100U);
    if (ret != APP_DRV_SUCCESS)
        cli_printf("[XYZ] read reg=%02X failed ret=%04X; data invalid\r\n", reg, ret);
    return ret == APP_DRV_SUCCESS;
}

static bool gsensor_xyz_write_check(uint8_t reg, uint8_t value)
{
    uint8_t check = 0;
    uint16_t ret = app_i2c_mem_write_sync(APP_I2C_ID_0, GSENSOR_PROBE_ADDR,
                                         reg, I2C_MEMADD_SIZE_8BIT, &value, 1U, 100U);
    if (ret != APP_DRV_SUCCESS) {
        cli_printf("[XYZ] write reg=%02X failed ret=%04X\r\n", reg, ret);
        return false;
    }
    if (!gsensor_xyz_read(reg, &check, 1U)) return false;
    if (check != value) {
        cli_printf("[XYZ] reg=%02X expected=%02X actual=%02X\r\n", reg, value, check);
        return false;
    }
    return true;
}

/* SAM | 2026-10-16 17:30 +08:00 | Save and read back DA215 registers before enabling vendor active interrupt because the existing DA221 0x27 path is unverified on this board. */
/* SAM | 2026-10-17 23:17 +08:00 | Save INT_LATCH for the temporary 2s diagnostic capture and restore it so sleep behavior is unchanged. */
/* SAM | 2026-10-18 22:03 +08:00 | Also save new-data enable/map for a deterministic INT test that must restore the prior sensor state. */
static const uint8_t s_motion_regs[] = {0x0FU, 0x10U, 0x11U, 0x16U, 0x19U, 0x20U, 0x21U, 0x27U, 0x28U, 0x17U, 0x1AU};
static uint8_t s_motion_saved[sizeof(s_motion_regs)];
static bool s_motion_armed;
/* SAM | 2026-10-18 21:40 +08:00 | Keep output polarity and pin interpretation together for the reversible serial diagnostic. */
static bool s_motion_active_high = true;
bool gsensor_sleep_motion_restore(void);

bool gsensor_sleep_motion_active_high(void) { return s_motion_active_high; }

bool gsensor_sleep_motion_pin_active(void)
{
    return (app_io_read_pin(YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN) == APP_IO_PIN_SET)
           == s_motion_active_high;
}

bool gsensor_sleep_motion_arm(bool active_high)
{
    i2c_handle_t *h = app_i2c_get_handle(APP_I2C_ID_0);
    uint8_t id = 0U;
    if (s_motion_armed || h == NULL || hal_i2c_get_state(h) != HAL_I2C_STATE_READY ||
        !gsensor_xyz_read(0x01U, &id, 1U) || id != 0x13U) return false;
    for (unsigned int i = 0; i < sizeof(s_motion_regs); ++i)
        if (!gsensor_xyz_read(s_motion_regs[i], &s_motion_saved[i], 1U)) return false;
    s_motion_armed = true; /* Restore even after a partial configuration write. */
    s_motion_active_high = active_high;
    /* SAM | 2026-10-19 10:35 +08:00 | Use board-tested push-pull: 01 asserts low and 00 asserts high; OD stayed high during confirmed motion. */
    /* SAM | 2026-10-18 20:16 +08:00 | Use the previously motion-tested 0x08 (~31mg) sleep threshold because 0x33 (~199mg) did not wake the board during the confirmed movement test. */
    /* SAM | 2026-10-20 +08:00 | Qualify active motion for four ODR periods because pre-reset captures proved unsolicited AON7 wake with both polarities and the old duration 00 admitted a single-period transient. Keep threshold 08 unchanged; this filter candidate still needs static and real-motion acceptance. */
    static const uint8_t target[] = {0x00U, 0x07U, 0x34U, 0x87U, 0x04U, 0x01U, 0x00U, 0x03U, 0x08U};
    for (unsigned int i = 0; i < sizeof(s_motion_regs); ++i) {
        /* SAM | 2026-10-18 22:03 +08:00 | Ordinary motion arming preserves the extra new-data registers; only gsensor_drdy changes them. */
        if (i >= sizeof(target)) continue;
        if (s_motion_regs[i] == 0x16U || s_motion_regs[i] == 0x21U) continue;
        /* SAM | 2026-10-19 10:35 +08:00 | Match physical polarity to AON edge/idle checks because paired 60s captures proved the old interpretation inverted. */
        uint8_t value = s_motion_regs[i] == 0x20U ? (active_high ? 0x00U : 0x01U) : target[i];
        if (!gsensor_xyz_write_check(s_motion_regs[i], value)) {
            (void)gsensor_sleep_motion_restore();
            return false;
        }
    }
    if (!gsensor_xyz_write_check(0x16U, 0x87U)) {
        (void)gsensor_sleep_motion_restore();
        return false;
    }
    cli_printf("[GS] DA215 active INT1 armed addr=26 threshold=08 duration=03 (4 ODR periods) %s-active PP config=%02X\r\n",
               active_high ? "high" : "low", active_high ? 0x00U : 0x01U);
    return true;
}

bool gsensor_sleep_motion_restore(void)
{
    if (!s_motion_armed) return true;
    bool ok = true;
    /* Disable interrupt first, then restore every saved register. */
    if (!gsensor_xyz_write_check(0x16U, 0x00U)) ok = false;
    /* SAM | 2026-10-18 22:03 +08:00 | Disable both interrupt engines during restore, then restore their enables after routing and electrical configuration. */
    if (!gsensor_xyz_write_check(0x17U, 0x00U)) ok = false;
    for (unsigned int i = 0; i < sizeof(s_motion_regs); ++i) {
        if (s_motion_regs[i] == 0x16U || s_motion_regs[i] == 0x17U) continue;
        if (!gsensor_xyz_write_check(s_motion_regs[i], s_motion_saved[i])) ok = false;
    }
    if (!gsensor_xyz_write_check(0x16U, s_motion_saved[3])) ok = false;
    if (!gsensor_xyz_write_check(0x17U, s_motion_saved[9])) ok = false;
    if (ok) s_motion_armed = false;
    return ok;
}

/* SAM | 2026-10-17 17:51 +08:00 | Read DA215 status before restoring its registers so pin-high can be attributed to sensor motion or board wiring. */
/* SAM | 2026-10-17 23:05 +08:00 | Include the active-enable, map, latch and timing registers so a pin-level failure can be separated from sensor configuration. */
void gsensor_sleep_motion_diag(void)
{
    uint8_t id = 0U, motion = 0U, axis = 0U, int_set1 = 0U, map1 = 0U;
    uint8_t config = 0U, latch = 0U, duration = 0U, threshold = 0U;
    bool ok = gsensor_xyz_read(0x01U, &id, 1U) &&
              gsensor_xyz_read(0x09U, &motion, 1U) &&
              gsensor_xyz_read(0x0BU, &axis, 1U) &&
              gsensor_xyz_read(0x16U, &int_set1, 1U) &&
              gsensor_xyz_read(0x19U, &map1, 1U) &&
              gsensor_xyz_read(0x20U, &config, 1U) &&
              gsensor_xyz_read(0x21U, &latch, 1U) &&
              gsensor_xyz_read(0x27U, &duration, 1U) &&
              gsensor_xyz_read(0x28U, &threshold, 1U);
    cli_printf("[GS] INT diag read=%u id=%02X pin=%u motion=%02X axis=%02X en=%02X map=%02X config=%02X latch=%02X dur=%02X ths=%02X\r\n",
               (unsigned int)ok, (unsigned int)id,
               (unsigned int)app_io_read_pin(YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN),
               (unsigned int)motion, (unsigned int)axis, (unsigned int)int_set1,
               (unsigned int)map1, (unsigned int)config, (unsigned int)latch,
               (unsigned int)duration, (unsigned int)threshold);
}

/* SAM | 2026-10-17 23:05 +08:00 | Add a bounded live motion/INT1 check because ATK-Logic is unavailable and a 60s sleep timeout cannot identify which wake-chain layer failed. */
/* SAM | 2026-10-18 18:57 +08:00 | Configure AON_GPIO7 as an input during the awake diagnostic because pad reads before GPIOTE setup are not valid evidence of the wired INT1 level. */
static volatile unsigned int s_gsensor_diag_irq_count;
/* SAM | 2026-10-18 21:04 +08:00 | Count only prompted-window IRQs and sample the AON pad directly because one IRQ with no polled low level can originate during setup/settling or differ from the HAL read. */
static volatile bool s_gsensor_diag_monitoring;
static volatile unsigned int s_gsensor_diag_irq_low_count;
static volatile unsigned int s_gsensor_diag_irq_raw_low_count;
/* SAM | 2026-10-18 20:58 +08:00 | Pause the sensor sample timer while this blocking CLI owns INT1 because its 5Hz events overflow the QV sensor queue during the 10s capture. */
static QTimeEvtCtr s_gsensor_diag_sample_ticks;

/* SAM | 2026-10-18 21:58 +08:00 | Read live pad ownership/direction and IRQ setup because motion flags without pad transitions cannot distinguish sensor output from MCU pin misconfiguration. */
static bool gsensor_pad_diag(const char *stage)
{
    bool input = ll_aon_gpio_get_pin_mode(YP001_SENSOR_INT_PIN) == LL_AON_GPIO_MODE_INPUT;
    uint32_t mux = ll_aon_gpio_get_pin_mux(YP001_SENSOR_INT_PIN);
    uint32_t enabled = ll_aon_gpio_is_enabled_it(YP001_SENSOR_INT_PIN);
    uint32_t edge = s_motion_active_high ? ll_aon_gpio_is_enabled_rising_trigger(YP001_SENSOR_INT_PIN)
                                        : ll_aon_gpio_is_enabled_falling_trigger(YP001_SENSOR_INT_PIN);
    cli_printf("[GS PAD] stage=%s input=%u mux=%lu pull=%lu irq_en=%lu edge_ok=%lu pad=%08lX ctrl=%08lX ovr=%08lX\r\n",
               stage, (unsigned int)input, (unsigned long)mux,
               (unsigned long)ll_aon_gpio_get_pin_pull(YP001_SENSOR_INT_PIN),
               (unsigned long)enabled, (unsigned long)edge,
               (unsigned long)AON_IO->AON_PAD_CTRL1,
               (unsigned long)AON_IO->EXT_WAKEUP_CTRL0, (unsigned long)AON_IO->AON_MCU_OVR);
    return input && mux == LL_AON_GPIO_MUX_7 && enabled && edge;
}

static void gsensor_int_diag_callback(app_io_evt_t *evt)
{
    if (evt != NULL && evt->type == YP001_SENSOR_INT_TYPE &&
        evt->pin == YP001_SENSOR_INT_PIN && s_gsensor_diag_monitoring) {
        ++s_gsensor_diag_irq_count;
        if (app_io_read_pin(YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN) == APP_IO_PIN_RESET)
            ++s_gsensor_diag_irq_low_count;
        if (ll_aon_gpio_read_input_pin(YP001_SENSOR_INT_PIN) == 0U)
            ++s_gsensor_diag_irq_raw_low_count;
    }
}

static bool gsensor_int_diag_gpio_setup(void)
{
    app_gpiote_param_t param = {YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN,
                                s_motion_active_high ? APP_IO_MODE_IT_RISING : APP_IO_MODE_IT_FALLING, APP_IO_NOPULL,
                                gsensor_int_diag_callback};
    s_gsensor_diag_irq_count = 0U;
    s_gsensor_diag_monitoring = false;
    if (app_gpiote_config(&param) != APP_DRV_SUCCESS) return false;
    /* The diagnostic callback now owns INT1, so it cannot rearm sample_clk. */
    s_gsensor_diag_sample_ticks = QTimeEvt_currCtr(&DA221_inst.sample_clk);
    (void)QTimeEvt_disarm(&DA221_inst.sample_clk);
    cli_printf("[GS TEST] periodic sampling paused; saved_ticks=%lu\r\n",
               (unsigned long)s_gsensor_diag_sample_ticks);
    return true;
}

static bool gsensor_int_diag_gpio_restore(void)
{
    s_gsensor_diag_monitoring = false;
    app_gpiote_param_t param = {YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN,
                                APP_IO_MODE_IT_BOTH_EDGE, APP_IO_NOPULL,
                                DA221_gpio_int_callback};
    bool ok = app_gpiote_config(&param) == APP_DRV_SUCCESS;
    /* SAM | 2026-10-18 20:58 +08:00 | Restore the previous countdown and existing periodic interval on all diagnostic exits; rearm also tolerates an INT edge that already restarted sampling. */
    if (s_gsensor_diag_sample_ticks != 0U) {
        (void)QTimeEvt_rearm(&DA221_inst.sample_clk, s_gsensor_diag_sample_ticks);
        s_gsensor_diag_sample_ticks = 0U;
    }
    return ok;
}

static int cmd_gsensor_int_test(int argc, char *argv[])
{
    /* SAM | 2026-10-18 21:40 +08:00 | Allow high/low comparison without rebuilding; reject unknown polarity before touching sensor registers. */
    if (argc < 1 || argc > 2 || (argc == 2 && strcmp(argv[1], "high") && strcmp(argv[1], "low"))) {
        cli_printf("Usage: gsensor_int_test [low|high] (10s; default low)\r\n");
        return -1;
    }
    if (!gsensor_sleep_motion_arm(argc == 2 && !strcmp(argv[1], "high"))) {
        cli_printf("[GS TEST] arm failed; test not started\r\n");
        return -1;
    }
    if (!gsensor_int_diag_gpio_setup()) {
        bool sensor_restored = gsensor_sleep_motion_restore();
        (void)gsensor_int_diag_gpio_restore();
        cli_printf("[GS TEST] AON_GPIO7 input setup failed sensor_restore=%u\r\n",
                   (unsigned int)sensor_restored);
        return -1;
    }

    /* SAM | 2026-10-17 23:17 +08:00 | Temporarily latch INT1 for 2s and discard configuration-time status before the prompted tap; the normal sleep arm keeps the saved latch setting. */
    if (!gsensor_xyz_write_check(0x21U, 0x04U)) {
        cli_printf("[GS TEST] INT_LATCH=04 setup failed; restoring sensor registers\r\n");
        (void)gsensor_int_diag_gpio_restore();
        (void)gsensor_sleep_motion_restore();
        return -1;
    }
    /* SAM | 2026-10-17 23:34 +08:00 | Lower ACTIVE_THS only for this diagnostic to test whether the confirmed light tap reaches DA215; restore the saved product threshold on every exit. */
    if (!gsensor_xyz_write_check(0x28U, 0x08U)) {
        cli_printf("[GS TEST] ACTIVE_THS=08 setup failed; restoring sensor registers\r\n");
        (void)gsensor_int_diag_gpio_restore();
        (void)gsensor_sleep_motion_restore();
        return -1;
    }
    cli_printf("[GS TEST] temporary ACTIVE_THS=08 (~31mg); sleep threshold unchanged\r\n");
    gsensor_sleep_motion_diag();
    cli_printf("[GS TEST] settling 2200ms; do not tap yet\r\n");
    delay_ms(2200U);
    uint8_t baseline_motion = 0U;
    if (!gsensor_xyz_read(0x09U, &baseline_motion, 1U)) {
        (void)gsensor_int_diag_gpio_restore();
        (void)gsensor_sleep_motion_restore();
        cli_printf("[GS TEST] baseline read failed; sensor registers restored\r\n");
        return -1;
    }
    uint8_t baseline_axis = 0U;
    if ((baseline_motion & 0x04U) != 0U && !gsensor_xyz_read(0x0BU, &baseline_axis, 1U)) {
        (void)gsensor_int_diag_gpio_restore();
        (void)gsensor_sleep_motion_restore();
        cli_printf("[GS TEST] baseline axis read failed; sensor registers restored\r\n");
        return -1;
    }
    unsigned int baseline_pin = (unsigned int)app_io_read_pin(YP001_SENSOR_INT_TYPE,
                                                              YP001_SENSOR_INT_PIN);
    cli_printf("[GS TEST] baseline motion=%02X axis=%02X pin=%u\r\n",
               (unsigned int)baseline_motion, (unsigned int)baseline_axis, baseline_pin);
    if ((baseline_motion & 0x04U) != 0U || gsensor_sleep_motion_pin_active()) {
        bool restored = gsensor_sleep_motion_restore();
        bool gpio_restored = gsensor_int_diag_gpio_restore();
        cli_printf("[GS TEST] baseline still active; test aborted restore=%u\r\n",
                   (unsigned int)(restored && gpio_restored));
        return -1;
    }
    /* SAM | 2026-10-18 21:04 +08:00 | Discard configuration/settling IRQs before opening the measurement window; no UART output runs in the ISR. */
    s_gsensor_diag_irq_count = 0U;
    s_gsensor_diag_irq_low_count = 0U;
    s_gsensor_diag_irq_raw_low_count = 0U;
    s_gsensor_diag_monitoring = true;
    cli_printf("[GS TEST] monitoring for 10s; window-only IRQ + raw AON pad; tap/move now\r\n");
    unsigned int motion_samples = 0U, pin_low_samples = 0U;
    unsigned int raw_pin_low_samples = 0U;
    unsigned int pin_active_samples = 0U, raw_pin_active_samples = 0U;
    unsigned int first_event_ms = 0xFFFFFFFFU;
    unsigned int xyz_samples = 0U;
    int16_t xyz_min[3] = {0, 0, 0}, xyz_max[3] = {0, 0, 0};
    bool read_ok = true;
    /* SAM | 2026-10-17 23:27 +08:00 | Sample raw XYZ during the same prompted window because a tap with no active flag must be separated from no sensor acceleration response. */
    /* Poll flags every 5ms and XYZ every 10ms; raw ranges show motion even if ACTIVE_THS is not crossed. */
    for (unsigned int i = 0U; i < 2000U; ++i) {
        uint8_t motion = 0U;
        if (!gsensor_xyz_read(0x09U, &motion, 1U)) {
            read_ok = false;
            break;
        }
        bool motion_active = (motion & 0x04U) != 0U;
        bool pin_high = app_io_read_pin(YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN) == APP_IO_PIN_SET;
        bool pin_active = pin_high == s_motion_active_high;
        bool raw_pin_high = ll_aon_gpio_read_input_pin(YP001_SENSOR_INT_PIN) != 0U;
        if (motion_active) ++motion_samples;
        if (!pin_high) ++pin_low_samples;
        if (!raw_pin_high) ++raw_pin_low_samples;
        if (pin_active) ++pin_active_samples;
        if (raw_pin_high == s_motion_active_high) ++raw_pin_active_samples;
        if ((i & 1U) == 0U) {
            uint8_t raw[6];
            if (!gsensor_xyz_read(0x02U, raw, sizeof(raw))) {
                read_ok = false;
                break;
            }
            int16_t sample[3] = {
                gsensor_decode14(raw[0], raw[1]),
                gsensor_decode14(raw[2], raw[3]),
                gsensor_decode14(raw[4], raw[5])
            };
            if (xyz_samples == 0U) {
                for (unsigned int axis = 0U; axis < 3U; ++axis)
                    xyz_min[axis] = xyz_max[axis] = sample[axis];
            } else {
                for (unsigned int axis = 0U; axis < 3U; ++axis) {
                    if (sample[axis] < xyz_min[axis]) xyz_min[axis] = sample[axis];
                    if (sample[axis] > xyz_max[axis]) xyz_max[axis] = sample[axis];
                }
            }
            ++xyz_samples;
        }
        if ((motion_active || pin_active) && first_event_ms == 0xFFFFFFFFU) {
            first_event_ms = i * 5U;
            uint8_t axis = 0U;
            if (motion_active && !gsensor_xyz_read(0x0BU, &axis, 1U)) {
                read_ok = false;
                break;
            }
            cli_printf("[GS TEST] first event t=%ums motion=%02X axis=%02X pin=%u\r\n",
                       first_event_ms, (unsigned int)motion, (unsigned int)axis,
                       (unsigned int)app_io_read_pin(YP001_SENSOR_INT_TYPE,
                                                     YP001_SENSOR_INT_PIN));
        }
        /* SAM | 2026-10-17 23:08 +08:00 | Use the SDK-declared delay_ms API; gr55xx_delay_ms has no linked definition and fails Keil link. */
        delay_ms(5U);
    }

    s_gsensor_diag_monitoring = false;
    bool sensor_restored = gsensor_sleep_motion_restore();
    bool gpio_restored = gsensor_int_diag_gpio_restore();
    bool restored = sensor_restored && gpio_restored;
    if (xyz_samples != 0U) {
        unsigned int range_x = (unsigned int)((int32_t)xyz_max[0] - xyz_min[0]);
        unsigned int range_y = (unsigned int)((int32_t)xyz_max[1] - xyz_min[1]);
        unsigned int range_z = (unsigned int)((int32_t)xyz_max[2] - xyz_min[2]);
        cli_printf("[GS TEST] xyz_samples=%u range_raw=(%u,%u,%u) range_mg=(%u,%u,%u)\r\n",
                   xyz_samples, range_x, range_y, range_z,
                   range_x * 1000U / 4096U, range_y * 1000U / 4096U,
                   range_z * 1000U / 4096U);
    } else {
        cli_printf("[GS TEST] xyz_samples=0\r\n");
    }
    cli_printf("[GS TEST] raw_pin_low_samples=%u irq_low_samples=%u irq_raw_low_samples=%u\r\n",
               raw_pin_low_samples, s_gsensor_diag_irq_low_count,
               s_gsensor_diag_irq_raw_low_count);
    cli_printf("[GS TEST] polarity=%s pin_active_samples=%u raw_pin_active_samples=%u\r\n",
               s_motion_active_high ? "high" : "low", pin_active_samples, raw_pin_active_samples);
    if (first_event_ms == 0xFFFFFFFFU)
        cli_printf("[GS TEST] read_ok=%u motion_samples=%u pin_low_samples=%u irq_edges=%u first_ms=none restore=%u\r\n",
                   (unsigned int)read_ok, motion_samples, pin_low_samples,
                   s_gsensor_diag_irq_count,
                   (unsigned int)restored);
    else
        cli_printf("[GS TEST] read_ok=%u motion_samples=%u pin_low_samples=%u irq_edges=%u first_ms=%u restore=%u\r\n",
                   (unsigned int)read_ok, motion_samples, pin_low_samples,
                   s_gsensor_diag_irq_count,
                   first_event_ms, (unsigned int)restored);
    return read_ok && restored ? 0 : -1;
}

/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_int_test", "DA215 motion/AON7 test 10s", cmd_gsensor_int_test);

/* SAM | 2026-10-18 21:52 +08:00 | Wait up to 120s for actual motion, then capture 3s of pad evidence because fixed 10s human-action windows repeatedly missed the action and blocking QV overflows timer queues. */
static struct {
    /* SAM | 2026-10-18 22:20 +08:00 | Hold one configuration for a full minute so manual voltmeter readings cannot cross an automatic motion-triggered restore. */
    bool active, started, monitoring, triggered, data_ready, hold;
    /* SAM | 2026-10-18 22:28 +08:00 | Verify the exact selected output stage during the minute-long OD/push-pull comparison. */
    uint8_t hold_config;
    uint32_t start_ms, last_ms, trigger_ms, samples, motion, pin, raw, report_ms;
} s_wait;

static void gsensor_wait_finish(const char *reason)
{
    s_gsensor_diag_monitoring = false;
    bool sensor_ok = gsensor_sleep_motion_restore();
    bool gpio_ok = gsensor_int_diag_gpio_restore();
    s_wait.active = false;
    cli_printf("[GS WAIT] source=%s\r\n", s_wait.data_ready ? "new_data" : "motion");
    cli_printf("[GS WAIT] end=%s samples=%lu motion=%lu pin_active=%lu raw_active=%lu irq=%u irq_raw_low=%u restore=%u\r\n",
               reason, (unsigned long)s_wait.samples, (unsigned long)s_wait.motion,
               (unsigned long)s_wait.pin, (unsigned long)s_wait.raw,
               s_gsensor_diag_irq_count, s_gsensor_diag_irq_raw_low_count,
               (unsigned int)(sensor_ok && gpio_ok));
}

static int cmd_gsensor_wait(int argc, char *argv[])
{
    if (argc == 2 && !strcmp(argv[1], "stop")) {
        if (s_wait.active) gsensor_wait_finish("cancel");
        return 0;
    }
    if (argc > 2 || (argc == 2 && strcmp(argv[1], "low") && strcmp(argv[1], "high"))) {
        cli_printf("Usage: gsensor_wait [low|high|stop]\r\n");
        return -1;
    }
    if (s_wait.active || !gsensor_sleep_motion_arm(argc == 2 && !strcmp(argv[1], "high"))) {
        cli_printf("[GS WAIT] busy/arm failed\r\n");
        return -1;
    }
    if (!gsensor_int_diag_gpio_setup() || !gsensor_xyz_write_check(0x21U, 0x04U)) {
        gsensor_wait_finish("setup_failed");
        return -1;
    }
    /* SAM | 2026-10-18 21:58 +08:00 | Reject a bad live MCU configuration instead of collecting misleading zero-IRQ evidence. */
    if (!gsensor_pad_diag("configured")) {
        gsensor_wait_finish("pad_config_failed");
        return -1;
    }
    memset(&s_wait, 0, sizeof(s_wait));
    s_wait.active = true;
    cli_printf("[GS WAIT] starting; keep still until READY; foreground capture, 120s limit\r\n");
    return 0;
}

/* SAM | 2026-10-18 22:20 +08:00 | Provide a fixed 60s measurement window with no clean-baseline gate or motion-triggered completion; retain the existing manual stop and failure restoration. */
static int cmd_gsensor_hold(int argc, char *argv[])
{
    /* SAM | 2026-10-18 22:28 +08:00 | Add an optional push-pull comparison, changing only INT_od; default remains OD and all original registers are restored. */
    if ((argc != 2 && argc != 3) || (strcmp(argv[1], "low") && strcmp(argv[1], "high")) ||
        (argc == 3 && strcmp(argv[2], "pp") && strcmp(argv[2], "od"))) {
        cli_printf("Usage: gsensor_hold low|high [od|pp] (fixed 60s; gsensor_wait stop cancels)\r\n");
        return -1;
    }
    if (s_wait.active || !gsensor_sleep_motion_arm(!strcmp(argv[1], "high"))) {
        cli_printf("[GS HOLD] busy/arm failed\r\n");
        return -1;
    }
    /* SAM | 2026-10-19 10:35 +08:00 | Make PP low/high match measured physical polarity; OD remains an explicit comparison only. */
    uint8_t config = (s_motion_active_high ? 0x00U : 0x01U) |
                     ((argc == 3 && !strcmp(argv[2], "pp")) ? 0x00U : 0x02U);
    if (!gsensor_int_diag_gpio_setup() || !gsensor_xyz_write_check(0x21U, 0x04U) ||
        !gsensor_xyz_write_check(0x20U, config) ||
        !gsensor_pad_diag("hold")) {
        gsensor_wait_finish("hold_setup_failed");
        return -1;
    }
    memset(&s_wait, 0, sizeof(s_wait));
    s_wait.hold_config = config;
    s_wait.active = s_wait.hold = s_wait.monitoring = true;
    s_gsensor_diag_irq_count = s_gsensor_diag_irq_low_count = s_gsensor_diag_irq_raw_low_count = 0U;
    s_gsensor_diag_monitoring = true;
    cli_printf("[GS HOLD] START polarity=%s drive=%s config=%02X; FIXED 60s; movement will NOT end the test\r\n",
               s_motion_active_high ? "high" : "low", (config & 0x02U) ? "OD" : "PP", config);
    return 0;
}

/* SAM | 2026-10-18 22:03 +08:00 | Generate new-data IRQs at the existing 125Hz ODR without any human movement, isolating INT output/routing from the motion detector. DS_da215 Rev0.3 pp17,22,25: SET2 bit4, MAP2 bit0, status 0A bit0. */
static int cmd_gsensor_drdy(int argc, char *argv[])
{
    (void)argv;
    if (argc != 1 || s_wait.active || !gsensor_sleep_motion_arm(false)) {
        cli_printf("[GS DRDY] usage: gsensor_drdy; busy/arm failed\r\n");
        return -1;
    }
    if (!gsensor_int_diag_gpio_setup() ||
        !gsensor_xyz_write_check(0x16U, 0x00U) ||
        !gsensor_xyz_write_check(0x17U, 0x00U) ||
        !gsensor_xyz_write_check(0x19U, 0x00U) ||
        !gsensor_xyz_write_check(0x1AU, 0x01U) ||
        !gsensor_xyz_write_check(0x21U, 0x00U) ||
        !gsensor_pad_diag("new_data")) {
        gsensor_wait_finish("new_data_setup_failed");
        return -1;
    }
    memset(&s_wait, 0, sizeof(s_wait));
    s_wait.active = s_wait.data_ready = s_wait.monitoring = true;
    s_gsensor_diag_irq_count = s_gsensor_diag_irq_low_count = s_gsensor_diag_irq_raw_low_count = 0U;
    s_gsensor_diag_monitoring = true;
    if (!gsensor_xyz_write_check(0x17U, 0x10U)) {
        gsensor_wait_finish("new_data_enable_failed");
        return -1;
    }
    cli_printf("[GS DRDY] enabled SET2=10 MAP2=01 latch=00; capture 3s; no movement needed\r\n");
    return 0;
}

bool gsensor_wait_poll(uint32_t now_ms)
{
    if (!s_wait.active) return false;
    if (!s_wait.started) {
        s_wait.started = true;
        s_wait.start_ms = now_ms;
        s_wait.last_ms = now_ms;
    }
    /* SAM | 2026-10-18 22:20 +08:00 | End the meter window only at 60s, explicit stop or a reported I2C/configuration failure, never on motion. */
    if (s_wait.hold && (uint32_t)(now_ms - s_wait.start_ms) >= 60000U) {
        cli_printf("[GS HOLD] END 60s reached; restoring now\r\n");
        gsensor_wait_finish("hold_60s_complete");
        return true;
    }
    if ((uint32_t)(now_ms - s_wait.start_ms) >= 120000U) {
        gsensor_wait_finish("timeout");
        return true;
    }
    if ((uint32_t)(now_ms - s_wait.last_ms) < 10U) return true;
    s_wait.last_ms = now_ms;
    if (!s_wait.hold && !s_wait.data_ready && (uint32_t)(now_ms - s_wait.start_ms) < 2200U) return true;
    uint8_t motion = 0U;
    if (!gsensor_xyz_read(s_wait.data_ready ? 0x0AU : 0x09U, &motion, 1U)) {
        gsensor_wait_finish("read_failed");
        return true;
    }
    if (!s_wait.monitoring) {
        /* Wait for a clean baseline instead of aborting while the user is still settling. */
        if ((motion & 0x04U) || gsensor_sleep_motion_pin_active()) return true;
        s_gsensor_diag_irq_count = 0U;
        s_gsensor_diag_irq_low_count = 0U;
        s_gsensor_diag_irq_raw_low_count = 0U;
        s_gsensor_diag_monitoring = true;
        s_wait.monitoring = true;
        cli_printf("[GS WAIT] READY; move whenever convenient; waiting for actual motion\r\n");
    }
    ++s_wait.samples;
    if (motion & (s_wait.data_ready ? 0x01U : 0x04U)) ++s_wait.motion;
    if (gsensor_sleep_motion_pin_active()) ++s_wait.pin;
    if ((ll_aon_gpio_read_input_pin(YP001_SENSOR_INT_PIN) != 0U) == s_motion_active_high) ++s_wait.raw;
    if (s_wait.hold) {
        if ((uint32_t)(now_ms - s_wait.report_ms) >= 1000U) {
            s_wait.report_ms = now_ms;
            uint8_t config = 0U;
            if (!gsensor_xyz_read(0x20U, &config, 1U) ||
                config != s_wait.hold_config) {
                gsensor_wait_finish("hold_config_failed");
                return true;
            }
            cli_printf("[GS HOLD] elapsed_ms=%lu config=%02X motion=%02X pin=%u raw=%lu irq=%u\r\n",
                       (unsigned long)(now_ms - s_wait.start_ms), config, motion,
                       (unsigned int)app_io_read_pin(YP001_SENSOR_INT_TYPE, YP001_SENSOR_INT_PIN),
                       (unsigned long)ll_aon_gpio_read_input_pin(YP001_SENSOR_INT_PIN),
                       s_gsensor_diag_irq_count);
        }
        return true;
    }
    if (!s_wait.data_ready && !s_wait.triggered && (motion & 0x04U)) {
        s_wait.triggered = true;
        s_wait.trigger_ms = now_ms;
        /* SAM | 2026-10-18 21:58 +08:00 | Read both sensor routing and pad state at the actual event to detect configuration drift after READY. */
        gsensor_sleep_motion_diag();
        if (!gsensor_pad_diag("motion")) {
            gsensor_wait_finish("pad_changed");
            return true;
        }
        cli_printf("[GS WAIT] MOTION detected; capturing 3s of INT evidence\r\n");
    }
    if (s_wait.data_ready && (uint32_t)(now_ms - s_wait.start_ms) >= 3000U)
        gsensor_wait_finish("new_data_captured");
    else if (s_wait.triggered && (uint32_t)(now_ms - s_wait.trigger_ms) >= 3000U)
        gsensor_wait_finish("motion_captured");
    return true;
}

/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_wait", "Motion low|high|stop, max120s", cmd_gsensor_wait);
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_drdy", "Data-ready capture 3s", cmd_gsensor_drdy);
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_hold", "Meter 60s: low|high [od|pp]", cmd_gsensor_hold);

/* SAM | 2026-10-10 11:35 +08:00 | Reuse the same decoding and restore
 * path for one LCD sample and the existing ten-sample serial test. */
static int gsensor_capture(unsigned int count, int32_t xyz[3])
{
    i2c_handle_t *h = app_i2c_get_handle(APP_I2C_ID_0);
    if (h == NULL || hal_i2c_get_state(h) != HAL_I2C_STATE_READY) {
        cli_printf("[XYZ] I2C0 unavailable/busy\r\n");
        return -1;
    }
    uint8_t id = 0, saved[3], target[3];
    /* SAM | 2026-10-10 14:24 +08:00 | Retry CHIPID up to three times
     * because the MiraMEMS mir3da_init reference allows transient I2C failures. */
    bool id_ok = false;
    for (unsigned int attempt = 0; attempt < 3U; ++attempt) {
        if (gsensor_xyz_read(0x01U, &id, 1U) && id == 0x13U) {
            id_ok = true;
            break;
        }
    }
    if (!id_ok) {
        cli_printf("[XYZ] ID check failed; no config writes\r\n");
        return -1;
    }
    if (!gsensor_xyz_read(0x0FU, saved, 3U)) return -1;
    target[0] = saved[0] & 0xFCU;              /* +/-2g */
    /* SAM | 2026-10-10 14:24 +08:00 | Follow MiraMEMS mir3da_init's
     * 125Hz and normal-mode settings while preserving saved register state. */
    target[1] = (saved[1] & 0xF0U) | 0x07U;   /* 125Hz */
    target[2] = 0x34U;                        /* vendor normal mode */
    bool success = true;
    for (unsigned int i = 0; i < 3U; ++i) {
        if (!gsensor_xyz_write_check((uint8_t)(0x0FU + i), target[i])) {
            success = false;
            break;
        }
    }
    if (success) {
        cli_printf("[XYZ] addr=26 +/-2g ODR=125Hz; mg=1000ths of g; polarity preserved\r\n");
        for (unsigned int n = 0; n < count; ++n) {
            uint8_t raw[6];
            delay_ms(100U); /* Allow a fresh conversion before each display. */
            if (!gsensor_xyz_read(0x02U, raw, 6U)) {
                success = false;
                break;
            }
            int16_t x = gsensor_decode14(raw[0], raw[1]);
            int16_t y = gsensor_decode14(raw[2], raw[3]);
            int16_t z = gsensor_decode14(raw[4], raw[5]);
            xyz[0] = (int32_t)x * 1000 / 4096;
            xyz[1] = (int32_t)y * 1000 / 4096;
            xyz[2] = (int32_t)z * 1000 / 4096;
            cli_printf("[XYZ] n=%u raw X=%d Y=%d Z=%d | mg X=%ld Y=%ld Z=%ld\r\n",
                       n + 1U, x, y, z, (long)((int32_t)x * 1000 / 4096),
                       (long)((int32_t)y * 1000 / 4096),
                       (long)((int32_t)z * 1000 / 4096));
        }
    }
    bool restored = true;
    for (unsigned int i = 0; i < 3U; ++i) {
        /* Attempt every restore even if a previous write/readback failed. */
        if (!gsensor_xyz_write_check((uint8_t)(0x0FU + i), saved[i])) restored = false;
    }
    cli_printf("[XYZ] capture=%s restore=%s; %s\r\n", success ? "OK" : "FAIL",
               restored ? "OK" : "FAIL", restored ? "original config restored" :
               "sensor config uncertain; check I2C before further testing");
    return success && restored ? 0 : -1;
}

/* SAM | 2026-10-10 11:35 +08:00 | Never return stale LCD values after
 * failed capture or failed restoration of the original configuration. */
bool gsensor_read_mg(int32_t xyz[3])
{
    if (xyz == NULL) return false;
    xyz[0] = xyz[1] = xyz[2] = 0;
    if (gsensor_capture(1U, xyz) == 0) return true;
    xyz[0] = xyz[1] = xyz[2] = 0;
    return false;
}

bool gsensor_read_mg_fast(int32_t xyz[3])
{
    uint8_t raw[6];
    uint8_t range = 0U;
    if (xyz == NULL) return false;
    xyz[0] = xyz[1] = xyz[2] = 0;
    if (!gsensor_xyz_read(0x0FU, &range, 1U)) return false;
    if (!gsensor_xyz_read(0x02U, raw, 6U)) return false;
    int16_t x = gsensor_decode14(raw[0], raw[1]);
    int16_t y = gsensor_decode14(raw[2], raw[3]);
    int16_t z = gsensor_decode14(raw[4], raw[5]);
    int32_t lsb_per_g = (int32_t)(4096U >> (range & 0x03U));
    xyz[0] = (int32_t)x * 1000 / lsb_per_g;
    xyz[1] = (int32_t)y * 1000 / lsb_per_g;
    xyz[2] = (int32_t)z * 1000 / lsb_per_g;
    return true;
}

static int cmd_gsensor_xyz(int argc, char *argv[])
{
    (void)argv;
    int32_t xyz[3];
    if (argc != 1) {
        cli_printf("Usage: gsensor_xyz (10 samples; temporary config writes)\r\n");
        return -1;
    }
    return gsensor_capture(10U, xyz);
}

/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_xyz", "XYZ x10; restore DA215 config", cmd_gsensor_xyz);

/* SAM | 2026-10-10 14:37 +08:00 | Run the factory init sequence once and
 * read 0xC0 because the requested value must be measured after mir3da_init.
 * This diagnostic does not run during boot or periodic LCD sampling. */
static int cmd_gsensor_init_c0(int argc, char *argv[])
{
    (void)argv;
    if (argc != 1) {
        cli_printf("Usage: gsensor_init_c0\r\n");
        return -1;
    }
    i2c_handle_t *h = app_i2c_get_handle(APP_I2C_ID_0);
    if (h == NULL || hal_i2c_get_state(h) != HAL_I2C_STATE_READY) {
        cli_printf("[C0] I2C0 unavailable/busy; init not started\r\n");
        return -1;
    }
    uint8_t id = 0;
    bool id_ok = false;
    for (unsigned int attempt = 0; attempt < 3U; ++attempt) {
        uint16_t ret = app_i2c_mem_read_sync(APP_I2C_ID_0, GSENSOR_PROBE_ADDR,
                                             0x01U, I2C_MEMADD_SIZE_8BIT,
                                             &id, 1U, 100U);
        cli_printf("[C0] ID try=%u ret=%04X value=%02X\r\n", attempt + 1U, ret, id);
        if (ret == APP_DRV_SUCCESS && id == 0x13U) {
            id_ok = true;
            break;
        }
    }
    if (!id_ok) {
        cli_printf("[C0] INIT FAIL: CHIPID; no register writes\r\n");
        return -1;
    }
    /* SAM | 2026-10-10 14:37 +08:00 | Keep the vendor mir3da_init write
     * order, including the undocumented engineering and low-power writes,
     * so the subsequent 0xC0 read has the requested initialization state. */
    static const struct { uint8_t reg, value; } init_seq[] = {
        {0x0FU, 0x00U}, {0x11U, 0x34U}, {0x10U, 0x07U},
        {0x7FU, 0x83U}, {0x7FU, 0x69U}, {0x7FU, 0xBDU},
        {0x8CU, 0x00U} /* SA0 low: vendor 0x26 branch */
    };
    for (unsigned int i = 0; i < sizeof(init_seq) / sizeof(init_seq[0]); ++i) {
        uint8_t value = init_seq[i].value;
        uint16_t ret = app_i2c_mem_write_sync(APP_I2C_ID_0, GSENSOR_PROBE_ADDR,
                                              init_seq[i].reg, I2C_MEMADD_SIZE_8BIT,
                                              &value, 1U, 100U);
        cli_printf("[C0] init step=%u reg=%02X value=%02X ret=%04X\r\n",
                   i + 1U, init_seq[i].reg, value, ret);
        if (ret != APP_DRV_SUCCESS) {
            cli_printf("[C0] INIT FAIL: partial configuration; 0xC0 not read\r\n");
            return -1;
        }
    }
    cli_printf("[C0] INIT OK: vendor writes completed; register readback not implied\r\n");
    for (unsigned int i = 0; i < 3U; ++i) {
        uint8_t value = 0;
        uint16_t ret = app_i2c_mem_read_sync(APP_I2C_ID_0, GSENSOR_PROBE_ADDR,
                                             0xC0U, I2C_MEMADD_SIZE_8BIT,
                                             &value, 1U, 100U);
        cli_printf("[C0] read=%u reg=C0 ret=%04X value=%02X valid=%u\r\n",
                   i + 1U, ret, value, ret == APP_DRV_SUCCESS);
        if (ret != APP_DRV_SUCCESS) return -1;
    }
    return 0;
}

/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("gsensor_init_c0", "DA215 init; read C0 x3", cmd_gsensor_init_c0);

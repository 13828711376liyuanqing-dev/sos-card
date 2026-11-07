/* SAM | 2026-10-09 20:52 +08:00 | Match the user-installed R13=100k
 * with R42=100k because the previous divider reached the ADC rail.
 * GPIO23 enables Q8/Q9.
 * GR5526 datasheet rev1.3 pp590-592: single-ended CH_N, 13-bit,
 * full scale 2*Vref; discard initial samples and use eFuse calibration.
 * 1.6V reference requires chip supply >=3.2V. At 4.35V battery this
 * divider produces 2.175V; retain rail checks rather than clamp into SOC.
 * Only this module owns ADC in the current Keil source list. */
#include "yp001_battery.h"
#include "yp001_board_config.h"
#include "app_adc.h"
#include "gr55xx_delay.h"
#include "system_gr55xx.h"
#include "cli.h"

static app_adc_params_t s_adc = {
    .pin_cfg = {
        .channel_n = { .type = YP001_BATTERY_ADC_TYPE,
                       .mux = APP_IO_MUX_7, .pin = YP001_BATTERY_ADC_PIN },
        .channel_p = { .type = YP001_BATTERY_ADC_TYPE,
                       .mux = APP_IO_MUX_7, .pin = YP001_BATTERY_ADC_PIN },
    },
    /* SAM | 2026-10-26 +08:00 | Use the slowest fast ADC clock because the ROM clock callback waits for four conversions under PRIMASK: 16k needs about 3.75ms, exceeding UART4's FIFO budget; 1M needs about 60us. Preserve 50ms divider settling, sample counts and eFuse calibration. */
    .init = { .channel_n = ADC_INPUT_SRC_IO1, .channel_p = ADC_INPUT_SRC_IO1,
              .input_mode = ADC_INPUT_SINGLE, .ref_source = ADC_REF_SRC_BUF_INT,
              .ref_value = ADC_REF_VALUE_1P6, .clock = ADC_CLK_1M },
};

/* SAM | 2026-10-26 +08:00 | Keep actual conversion duration in RAM so the same build can validate the ADC fix without another diagnostic firmware. This is total call duration, not a direct PRIMASK measurement. */
typedef struct {
    uint32_t sequence, count, status, clock_hz, cycles, last_us, max_us, valid;
} yp001_adc_timing_t;
volatile yp001_adc_timing_t g_yp001_adc_timing;
static uint16_t battery_conversion_sync(uint16_t *raw)
{
    uint32_t demcr=CoreDebug->DEMCR,ctrl=DWT->CTRL,clock=SystemCoreClock;
    CoreDebug->DEMCR=demcr|CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL=ctrl|DWT_CTRL_CYCCNTENA_Msk;
    /* Never reset CYCCNT: an outer OTA measurement may already own it. */
    uint32_t start=DWT->CYCCNT;
    uint16_t status=app_adc_conversion_sync(raw,36U,100U);
    uint32_t cycles=DWT->CYCCNT-start;
    DWT->CTRL=ctrl;CoreDebug->DEMCR=demcr;
    uint32_t valid=clock&&clock==SystemCoreClock&&cycles!=0;
    uint32_t us=valid?(uint32_t)(((uint64_t)cycles*1000000u)/clock):0;
    ++g_yp001_adc_timing.sequence;
    if(g_yp001_adc_timing.count!=UINT32_MAX)++g_yp001_adc_timing.count;
    g_yp001_adc_timing.status=status;g_yp001_adc_timing.clock_hz=clock;
    g_yp001_adc_timing.cycles=cycles;g_yp001_adc_timing.last_us=us;
    if(valid&&us>g_yp001_adc_timing.max_us)g_yp001_adc_timing.max_us=us;
    g_yp001_adc_timing.valid=valid;
    ++g_yp001_adc_timing.sequence;
    return status;
}

yp001_battery_result_t yp001_battery_read(uint16_t *millivolts)
{
    /* SAM | 2026-10-09 18:26 +08:00 | Initialize raw storage because a
     * missing sample must fail the rail check instead of using stack data. */
    uint16_t raw[36] = {0};
    double volts[32];
    double sum = 0.0, low = 4.0, high = 0.0;
    uint32_t raw_sum = 0U;
    bool initialized = false;
    yp001_battery_result_t result = YP001_BATTERY_ADC_ERROR;
    app_io_init_t gate = APP_IO_DEFAULT_CONFIG;
    if (millivolts == NULL) return result;
    *millivolts = 0U;
    gate.pin = YP001_BATTERY_SWITCH_PIN;
    gate.mode = APP_IO_MODE_OUTPUT;
    gate.pull = APP_IO_NOPULL;
    gate.mux = YP001_GPIO_GPIO_MUX;
    if (app_io_init(YP001_BATTERY_SWITCH_TYPE, &gate) != APP_DRV_SUCCESS)
        return result;
    app_io_write_pin(YP001_BATTERY_SWITCH_TYPE, gate.pin, APP_IO_PIN_SET);
    /* SAM | 2026-10-09 20:52 +08:00 | R42/R13 are now both 100k:
     * Thevenin R=50k with C8=0.1uF; retain 50ms (10 RC constants). */
    delay_ms(50U);
    if (app_adc_init(&s_adc, NULL) != APP_DRV_SUCCESS) goto done;
    initialized = true;
    /* SDK validates timeout but delegates actual wait to HAL. Do not
     * describe this parameter as an independent safety deadline. */
    if (battery_conversion_sync(raw) != APP_DRV_SUCCESS) goto done;
    /* SAM | 2026-10-09 18:26 +08:00 | Check BOTH rails before conversion
     * because GR5526 single-ended codes decrease with input voltage
     * (datasheet rev1.3 p590). raw=2 was incorrectly accepted as 3.873V.
     * Keep the previous high-code guard and add an 8-code low guard. */
    uint16_t raw_min = 8191U, raw_max = 0U;
    for (unsigned i = 0U; i < 32U; ++i) {
        uint16_t sample = raw[i + 4U];
        raw_sum += sample;
        if (sample < raw_min) raw_min = sample;
        if (sample > raw_max) raw_max = sample;
        /* HAL voltage conversion has no error return; sentinel detects a
         * calibration failure that leaves the output buffer untouched. */
        volts[i] = -1.0;
    }
    if (raw_min <= 8U || raw_max >= 8180U) {
        //cli_printf("[BAT] ADC RANGE raw_avg=%lu min=%u max=%u ref=1600mV; low raw=high input\r\n",
        //           (unsigned long)(raw_sum / 32U), (unsigned)raw_min, (unsigned)raw_max);
        result = YP001_BATTERY_ADC_RANGE;
        goto done;
    }
    if (app_adc_voltage_intern(&raw[4], volts, 32U) != APP_DRV_SUCCESS) goto done;
    for (unsigned i = 0U; i < 32U; ++i) {
        /* SAM | 2026-10-09 18:26 +08:00 | Raw rails were checked above;
         * retain the converted-voltage ceiling and invalid-value guard. */
        if (volts[i] > 3.2) {
            result = YP001_BATTERY_ADC_RANGE;
            goto done;
        }
        if (!(volts[i] >= 0.0)) goto done;
        sum += volts[i];
        /* SAM | 2026-10-09 18:26 +08:00 | raw_sum is captured before
         * conversion so the diagnostic always describes sampled codes. */
        if (volts[i] < low) low = volts[i];
        if (volts[i] > high) high = volts[i];
    }
    /* Remove one min/max; samples are volts from calibrated SDK API. */
    double pin_v = (sum - low - high) / 30.0;
    /* SAM | 2026-10-09 20:52 +08:00 | Restore battery voltage by x2
     * because the user replaced the lower R13 with 100k. */
    double battery_mv = pin_v * 1000.0 * (100.0 + 100.0) / 100.0;
    if (!(battery_mv >= 2500.0 && battery_mv <= 4350.0)) {
        result = YP001_BATTERY_LOW;
        goto done;
    }
    *millivolts = (uint16_t)(battery_mv + 0.5);
    result = YP001_BATTERY_OK;
    /* SAM | 2026-10-09 20:52 +08:00 | Identify the installed divider
     * in live logs because old firmware would use the wrong ratio. */
    cli_printf("[BAT] raw=%lu ADC=%umV BAT=%umV EST=%u%% R42=100k R13=100k\r\n",
               (unsigned long)(raw_sum / 32U), (unsigned)(pin_v * 1000.0 + 0.5),
               (unsigned)*millivolts, (unsigned)yp001_battery_estimate(*millivolts));
done:
    if (initialized && app_adc_deinit() != APP_DRV_SUCCESS)
        result = YP001_BATTERY_ADC_ERROR;
    app_io_write_pin(YP001_BATTERY_SWITCH_TYPE, gate.pin, APP_IO_PIN_RESET);
    if (result != YP001_BATTERY_OK) {
        *millivolts = 0U;
        /*cli_printf("[BAT] sample invalid=%u (1=ADC error,2=range,3=low)\r\n",
                   (unsigned)result);*/
    }
    return result;
}

/* SAM | 2026-10-09 15:45 +08:00 | Explicit voltage-based estimate because
 * no measured SOC/OCV curve is available for the temporary 530mAh cell.
 * Endpoints from its spec: discharge 3.0V, charge 4.35V. This is not
 * remaining capacity and must not control charging or shutdown. */
uint8_t yp001_battery_estimate(uint16_t millivolts)
{
    if (millivolts <= 3000U) return 0U;
    if (millivolts >= 4350U) return 100U;
    return (uint8_t)(((uint32_t)millivolts - 3000U) * 100U / 1350U);
}


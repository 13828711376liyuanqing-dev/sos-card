#include "yp001_charger.h"
#include "cli.h"
/* SAM | 2026-10-09 12:02 +08:00 | Share board address with diagnostics
 * because a hard-coded address can disagree with the driver. */
#include "yp001_board_config.h"

#include <string.h>
#include <stdlib.h>
#include <errno.h>

/* SAM | 2026-10-13 14:03 +08:00 | Require an expiring prepare token because
 * ship cuts MCU supply and only adapter insertion is supported for wake. */
static int cmd_ship(int argc, char *argv[])
{
    /* SAM | 2026-11-08 20:30 +08:00 | Factory operators start one GR-owned asynchronous transaction. */
    if (argc == 3 && !strcmp(argv[2], "start"))
        return yp001_charger_ship_start() ? 0 : -1;
    if (argc == 3 && !strcmp(argv[2], "status")) {
        yp001_charger_ship_status(); return 0;
    }
    if (argc == 3 && !strcmp(argv[2], "prepare"))
        return yp001_charger_ship_prepare() ? 0 : -1;
    if (argc == 3 && !strcmp(argv[2], "cancel"))
        return yp001_charger_ship_cancel() ? 0 : -1;
    if (argc == 4 && !strcmp(argv[2], "confirm")) {
        char *end;
        if (!argv[3][0]) return -1;
        for (const char *p = argv[3]; *p; ++p)
            if (*p < '0' || *p > '9') return -1;
        errno = 0;
        unsigned long token = strtoul(argv[3], &end, 10);
        if (errno || *end || !token || strlen(argv[3]) > 10U) return -1;
        return yp001_charger_ship_confirm((uint32_t)token) ? 0 : -1;
    }
    cli_printf("Usage: charger ship start|prepare|status|cancel|confirm <token>\r\n");
    return -1;
}

static int cmd_charger(int argc, char *argv[])
{
    yp001_charger_status_t status;
    /* SAM | 2026-10-13 14:03 +08:00 | Route ship before ordinary argument validation. */
    if (argc >= 2 && !strcmp(argv[1], "ship")) return cmd_ship(argc, argv);
    if (yp001_charger_ship_locked()) return -1;
    /* SAM | 2026-10-09 21:25 +08:00 | Retain manual overrides alongside
     * automatic insertion handling; stop holds until unplug or start. */
    if (argc != 2 ||
        (strcmp(argv[1], "probe") != 0 && strcmp(argv[1], "status") != 0 &&
         strcmp(argv[1], "prepare") != 0 && strcmp(argv[1], "start") != 0 &&
         strcmp(argv[1], "stop") != 0)) {
        cli_printf("Usage: charger <probe|status|prepare|start|stop> (prepare/start/stop WRITE)\r\n");
        return -1;
    }
    /* SAM | 2026-10-10 09:04 +08:00 | Print saved evidence before any probe
     * because even a failed status read must expose the original stop. */
    if (strcmp(argv[1], "status") == 0)
        yp001_charger_print_diagnostic();
    /* SAM | 2026-10-09 14:48 +08:00 | Stop before probing because a bus
     * failure must still invalidate the active software test state. */
    if (strcmp(argv[1], "stop") == 0) {
        return yp001_charger_test_stop() ? 0 : -4;
    }
    if (strcmp(argv[1], "start") == 0) {
        return yp001_charger_test_start() ? 0 : -4;
    }
    if (strcmp(argv[1], "prepare") == 0) {
        if (!yp001_charger_prepare_disabled()) return -4;
    } else if (!yp001_charger_probe()) {
        /* SAM | 2026-10-09 12:02 +08:00 | Report the configured address
         * because ETA69631 uses 7-bit 0x6B, not the previous 0x6A. */
        cli_printf("ETA69631 probe failed (I2C4 GPIO4/5, address 0x%02X, REG0B ID)\r\n",
                   (unsigned int)YP001_CHARGER_ADDRESS);
        return -2;
    }
    if (strcmp(argv[1], "probe") == 0) {
        cli_printf("ETA69631 detected; charger registers unchanged\r\n");
        return 0;
    }
    if (!yp001_charger_read_status(&status)) {
        cli_printf("ETA69631 status read failed\r\n");
        return -3;
    }
    cli_printf("ID=%02X VBUS=%u CHG=%u PG=%u VIN=%u FAULT=%02X\r\n",
               status.id, status.vbus_type, status.charge_state,
               status.power_good, status.input_present, status.fault);
    cli_printf("IIN_LIMIT=%umA ICHG_LIMIT=%umA VREG=%umV (setpoints, not measurements)\r\n",
               status.input_limit_ma, status.charge_limit_ma,
               status.charge_voltage_mv);
    cli_printf("VINDPM=%u IINDPM=%u THERM=%u VSYS_MIN=%u\r\n",
               status.input_voltage_limit, status.input_current_limit,
               status.thermal_limit, status.system_minimum);
    /* SAM | 2026-10-09 12:20 +08:00 | Print safety fields and raw bytes
     * because an ID or charge-state code alone does not verify inhibition. */
    cli_printf("CHG_EN=%u OTG=%u WD=%u EN_TIMER=%u EN_TERM=%u IPRE=%umA ITERM=%umA\r\n",
               (status.power_raw >> 4U) & 1U, (status.power_raw >> 5U) & 1U,
               (status.timer_raw >> 4U) & 3U, (status.timer_raw >> 3U) & 1U,
               (status.timer_raw >> 7U) & 1U, status.precharge_ma, status.termination_ma);
    /* SAM | 2026-11-12 22:40 +08:00 | Expose REG00 bit5 because the FAE mask change cannot be assessed from IIN_LIMIT alone. */
    cli_printf("REG00=%02X REG01=%02X REG03=%02X REG05=%02X REG0D=%02X FAULT_HISTORY=%02X FAULT_NOW=%02X\r\n",
               status.input_raw, status.power_raw, status.pre_term_raw, status.timer_raw, status.fine_raw,
               status.fault_history, status.fault);
    return 0;
}

/* SAM | 2026-10-09 21:25 +08:00 | Describe auto mode and the held stop
 * because a user stop must not be undone by the next idle poll. */
/* SAM | 2026-11-08 20:30 +08:00 | Expose the single factory entry alongside the legacy engineering commands. */
CLI_CMD_REGISTER("charger", "probe/status; prepare/start/stop; ship start/status; legacy prepare/confirm <token>/cancel", cmd_charger);

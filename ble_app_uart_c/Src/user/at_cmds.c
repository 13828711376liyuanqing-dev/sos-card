#include "cli.h"
#include "app_log.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

extern void uart4_send_data(uint8_t *p_data, uint16_t length);

#include "AOs.h"
#include "yp001_board_config.h"

/* Parse a byte with an out-of-band error value; FF is valid data. */
static int hex_to_byte(const char *s)
{
    if (strlen(s) != 2U) return -1;
    int value = 0;
    for (unsigned i = 0; i < 2U; ++i) {
        unsigned char c = (unsigned char)s[i];
        if (!isxdigit(c)) return -1;
        value = value * 16 + (isdigit(c) ? c - '0' : toupper(c) - 'A' + 10);
    }
    return value;
}

static int cmd_at1(int argc, char *argv[])
{
    uint8_t data[CLI_MAX_CMD_LEN];
    size_t used = 0;
    if (argc < 2) { cli_printf("Usage: at <command> | at hex XX ...\r\n"); return -1; }
    if (!strcmp(argv[1], "hex") || !strcmp(argv[1], "raw")) {
        if (argc < 3) return -1;
        for (int i = 2; i < argc; ++i) {
            int value = hex_to_byte(argv[i]);
            if (value < 0 || used >= sizeof(data)) {
                cli_printf("Error: invalid hex input\r\n"); return -1;
            }
            data[used++] = (uint8_t)value;
        }
    } else {
        for (int i = 1; i < argc; ++i) {
            size_t n = strlen(argv[i]);
            if (n + used + (i > 1 ? 1U : 0U) + 2U > sizeof(data)) {
                cli_printf("Error: command too long\r\n"); return -1;
            }
            if (i > 1) data[used++] = ' ';
            memcpy(data + used, argv[i], n); used += n;
        }
        data[used++] = '\r'; data[used++] = '\n';
    }
    uint16_t ret = Cat1Svr_send_async(&AO_Cat1Svr, data, (uint16_t)used);
    if (ret != APP_DRV_SUCCESS) {
        cli_printf("AT not sent: service/driver unavailable or busy (0x%04X)\r\n", ret);
        return -1;
    }
    cli_printf("Queued %u bytes\r\n", (unsigned)used);
    return 0;
}
CLI_CMD_REGISTER("at", "Send AT text or hex bytes", cmd_at1);

#include "cli.h"
#include <string.h>

extern bool g_log_output_enabled;   /* 定义在 user_periph_setup.c */

static int cmd_log(int argc, char *argv[])
{
    if (argc < 2) {
        cli_printf("Usage: log <on|off|status>\r\n");
        return -1;
    }
    if (strcmp(argv[1], "on") == 0) {
        g_log_output_enabled = true;
        cli_printf("Log output enabled\r\n");
    } else if (strcmp(argv[1], "off") == 0) {
        g_log_output_enabled = false;
        cli_printf("Log output disabled\r\n");
    } else if (strcmp(argv[1], "status") == 0) {
        cli_printf("Log output is %s\r\n", g_log_output_enabled ? "on" : "off");
    } else {
        cli_printf("Invalid argument. Use: on, off, status\r\n");
        return -2;
    }
    return 0;
}

CLI_CMD_REGISTER("log", "Control log output (on|off|status)", cmd_log);

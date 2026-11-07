#ifndef _CLI_H_
#define _CLI_H_

#include <stdint.h>
#include <stdbool.h>

#define CLI_MAX_CMD_LEN     1024
#define CLI_MAX_ARGS        8
#define CLI_PROMPT          "\n> "

typedef int (*cli_cmd_handler_t)(int argc, char *argv[]);

typedef struct {
    const char *name;
    const char *help;
    cli_cmd_handler_t handler;
} cli_cmd_t;


#define CLI_CMD_REGISTER(_name, _help, _func) \
    static const cli_cmd_t __cli_cmd_##_func \
        __attribute__((used, section(".cli_cmds"))) = { \
        .name = _name, \
        .help = _help, \
        .handler = _func \
    }

void cli_init(void);
void cli_discard_input(void);
void cli_process_char(uint8_t ch);
void cli_printf(const char *fmt, ...);
/* SAM | 2026-11-06 +08:00 | Structured maintenance callers need handler status, not just UART text. */
int cli_execute_string_result(const char *cmd);
void cli_execute_string(const char *cmd);

#endif /* _CLI_H_ */
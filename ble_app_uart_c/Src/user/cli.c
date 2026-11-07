#include "cli.h"
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
/* SAM | 2026-10-13 14:03 +08:00 | Gate every command owner during cutoff,
 * including queued AO power commands, rather than only charger start. */
#include "charger/yp001_charger.h"

/* 底层强制发送函数 */
extern void uart_tx_data_send_force(uint8_t *p_data, uint16_t length);


/* CLI 上下文 */
static struct {
    char line[CLI_MAX_CMD_LEN];
    uint16_t pos;
    bool discard;
    const cli_cmd_t *cmds;         /* 指向命令数组（实际存储在段中，无需复制） */
    uint32_t cmd_cnt;              /* 命令数量（运行时计算） */
} cli_ctx;

static int cli_execute(char *cmd_line);
static int cmd_help(int argc, char *argv[]);

/* Command section boundaries are supplied by the active toolchain linker. */
#if defined(__CC_ARM) || (defined(__ARMCC_VERSION) && (__ARMCC_VERSION >= 6000000))
extern const cli_cmd_t Image$$ER_CLI_CMDS$$Base[];
extern const cli_cmd_t Image$$ER_CLI_CMDS$$Limit[];
#define CLI_CMDS_START Image$$ER_CLI_CMDS$$Base
#define CLI_CMDS_END   Image$$ER_CLI_CMDS$$Limit
#else
extern const cli_cmd_t __cli_cmds_start[];
extern const cli_cmd_t __cli_cmds_end[];
#define CLI_CMDS_START __cli_cmds_start
#define CLI_CMDS_END   __cli_cmds_end
#endif

void cli_init(void)
{
    memset(&cli_ctx, 0, sizeof(cli_ctx));

    const cli_cmd_t *start = CLI_CMDS_START;
    const cli_cmd_t *end   = CLI_CMDS_END;
    
    if (end > start) {
        cli_ctx.cmds = start;
        cli_ctx.cmd_cnt = (end - start);
    } else {
        cli_ctx.cmds = NULL;
        cli_ctx.cmd_cnt = 0;
    }

    cli_printf("\r\n========================================\r\n");
    cli_printf("    GR5526 CLI Framework v1.0\r\n");
    cli_printf("    Type 'help' for commands\r\n");
    cli_printf("========================================\r\n");
    cli_printf(CLI_PROMPT);
}


/**
 * 处理单个输入字符
 */
void cli_discard_input(void)
{
    cli_ctx.pos = 0;
    cli_ctx.discard = true;
}

void cli_process_char(uint8_t ch)
{
    if (cli_ctx.discard) {
        if (ch == '\r' || ch == '\n') {
            cli_ctx.discard = false;
            cli_printf("\r\nInput discarded: line too long or RX overflow.\r\n" CLI_PROMPT);
        }
        return;
    }
    if (ch == '\r' || ch == '\n') {
        if (cli_ctx.pos > 0) {
            cli_ctx.line[cli_ctx.pos] = '\0';
            cli_printf("\r\n");
            cli_execute(cli_ctx.line);
            cli_ctx.pos = 0;
        }
        cli_printf(CLI_PROMPT);
        return;
    }

    if (ch == '\b' || ch == 0x7F) {
        if (cli_ctx.pos > 0) {
            cli_ctx.pos--;
            cli_printf("\b \b");
        }
        return;
    }

    if (cli_ctx.pos < CLI_MAX_CMD_LEN - 1) {
        cli_ctx.line[cli_ctx.pos++] = ch;
        uart_tx_data_send_force(&ch, 1);
    } else {
        cli_discard_input();
    }
}

/**
 * CLI 格式化输出
 */
void cli_printf(const char *fmt, ...)
{
    static char buf[256];
    va_list args;
    int len;

    va_start(args, fmt);
    len = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    if (len > 0) {
        uart_tx_data_send_force((uint8_t *)buf, (uint16_t)((len < (int)sizeof(buf)) ? len : sizeof(buf) - 1U));
    }
}

/* SAM | 2026-11-06 +08:00 | Return real handler status to BLE while retaining the existing void UART/API entry. */
int cli_execute_string_result(const char *cmd)
{
    char line[CLI_MAX_CMD_LEN];
    if (!cmd) return -1;
    if (strlen(cmd)>=sizeof(line)) { cli_printf("Error: command too long\r\n");return -1; }
    strcpy(line,cmd);
    return cli_execute(line);
}
void cli_execute_string(const char *cmd) { (void)cli_execute_string_result(cmd); }

/**
 * 解析并执行命令行
 */
static int cli_execute(char *cmd_line)
{
    char *argv[CLI_MAX_ARGS];
    int argc = 0;
    char *token;

    // 去除行首空格
    while (*cmd_line == ' ') cmd_line++;
    if (*cmd_line == '\0') return -1;

    // 分割参数
    token = strtok(cmd_line, " ");
    while (token != NULL && argc < CLI_MAX_ARGS) {
        argv[argc++] = token;
        token = strtok(NULL, " ");
    }

    if (token != NULL) {
        cli_printf("Error: too many arguments\r\n");
        return -1;
    }
    if (argc == 0) return -1;

    /* SAM | 2026-10-13 14:03 +08:00 | Only ship control remains available
     * while prepared/failed/sent; motor, UART, reset and UI writes are denied. */
    if (yp001_charger_ship_locked() &&
        !(argc >= 3 && !strcmp(argv[0], "charger") && !strcmp(argv[1], "ship"))) {
        cli_printf("[SHIP] command blocked; use charger ship status/cancel\r\n");
        return -1;
    }

    // 安全查找命令（若命令数为0则直接报未知命令）
    if (cli_ctx.cmd_cnt > 0 && cli_ctx.cmds != NULL) {
        for (uint32_t i = 0; i < cli_ctx.cmd_cnt; i++) {
            if (strcmp(cli_ctx.cmds[i].name, argv[0]) == 0) {
                return cli_ctx.cmds[i].handler(argc, argv);
            }
        }
    }

    cli_printf("Unknown command: '%s'. Type 'help' for list.\r\n", argv[0]);
    return -1;
}


/**
 * help 命令实现（也通过宏注册）
 */
static int cmd_help(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    cli_printf("\r\nAvailable commands:\r\n");
    cli_printf("--------------------------------------------------\r\n");
    for (uint32_t i = 0; i < cli_ctx.cmd_cnt; i++) {
        cli_printf("  %-12s - %s\r\n", cli_ctx.cmds[i].name, cli_ctx.cmds[i].help);
    }
    cli_printf("--------------------------------------------------\r\n");
    return 0;
}

/* 使用宏注册 help 命令 */
CLI_CMD_REGISTER("help", "Show available commands", cmd_help);

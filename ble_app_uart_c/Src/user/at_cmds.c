#include "cli.h"
#include "app_log.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

extern void uart4_send_data(uint8_t *p_data, uint16_t length);

#include "AOs.h" 

/* 普通 AT 命令发送宏（字符串 + \r\n） */
#define AT_SEND(fmt, ...) \
    do { \
        char _buf[CLI_MAX_CMD_LEN]; \
        int _len = snprintf(_buf, sizeof(_buf), fmt "\r\n", ##__VA_ARGS__); \
        if (_len > 0 && _len < (int)sizeof(_buf)) { \
            uint16_t _ret = Cat1Svr_send_async(&AO_Cat1Svr, (uint8_t *)_buf, (uint16_t)_len); \
            if (_ret == APP_DRV_BUSY) { \
                cli_printf("Error: UART busy, send failed\r\n"); \
            } else if (_ret == APP_DRV_SUCCESS) { \
                cli_printf("Sent: ...", _buf); \
            } else { \
                cli_printf("Error: Send data failed, ret:%u\r\n", _ret); \
            } \
        } else { \
            cli_printf("Error: Command too long\r\n"); \
        } \
    } while(0)

/* 辅助函数：两个十六进制字符转字节，非法返回 0xFF */
static uint8_t hex_to_byte(const char *s) {
    if (strlen(s) != 2) return 0xFF;
    int val = 0;
    for (int i = 0; i < 2; i++) {
        char c = s[i];
        if (c >= '0' && c <= '9')      val = val * 16 + (c - '0');
        else if (c >= 'A' && c <= 'F') val = val * 16 + (c - 'A' + 10);
        else if (c >= 'a' && c <= 'f') val = val * 16 + (c - 'a' + 10);
        else return 0xFF;
    }
    return (uint8_t)val;
}

static int cmd_at(int argc, char *argv[])
{
    /* --- 二进制发送子命令：at hex 55 AA 01 --- */
    if (argc >= 3 && (strcmp(argv[1], "hex") == 0 || strcmp(argv[1], "raw") == 0)) {
        uint8_t data[CLI_MAX_CMD_LEN];
        int data_len = 0;

        for (int i = 2; i < argc; i++) {
            uint8_t byte = hex_to_byte(argv[i]);
            if (byte == 0xFF) {
                cli_printf("Error: invalid hex byte '%s' (must be two hex digits)\r\n", argv[i]);
                return -1;
            }
            if (data_len >= (int)sizeof(data)) {
                cli_printf("Error: too many bytes, max %d\r\n", (int)sizeof(data));
                return -1;
            }
            data[data_len++] = byte;
        }

        /* 直接调用异步发送接口（不加 \r\n） */
        uint16_t ret = Cat1Svr_send_async(&AO_Cat1Svr, data, (uint16_t)data_len);
        if (ret == APP_DRV_BUSY) {
            cli_printf("Error: UART busy, send failed\r\n");
        } else if (ret == APP_DRV_SUCCESS) {
            cli_printf("Sent %d bytes (hex): ", data_len);
            for (int i = 0; i < data_len; i++) {
                cli_printf("%02X ", data[i]);
            }
            cli_printf("\r\n");
        } else {
            cli_printf("Error: Send data failed, ret:%u\r\n", ret);
        }
        return 0;
    }

    /* --- 原有透传 AT 命令（字符串 + \r\n） --- */
    char cmd_buf[CLI_MAX_CMD_LEN] = {0};
    int offset = 0;
    for (int i = 1; i < argc; i++) {
        offset += snprintf(cmd_buf + offset, sizeof(cmd_buf) - offset, "%s", argv[i]);
        if (i < argc - 1) {
            offset += snprintf(cmd_buf + offset, sizeof(cmd_buf) - offset, " ");
        }
    }
    AT_SEND("%s", cmd_buf);
    return 0;
}

static int cmd_at1(int argc, char *argv[])
{
    uint8_t send_buf[CLI_MAX_CMD_LEN] = {0};
    uint16_t send_len = 0;
    char log_buf[128] = {0}; // 最终日志缓存，仅最后打印一次
    bool is_hex_raw = false;

    // 分支1：十六进制/RAW二进制发送（at hex/raw xx xx xx）
    if (argc >= 3 && (!strcmp(argv[1], "hex") || !strcmp(argv[1], "raw")))
    {
        is_hex_raw = true;
        for (int i = 2; i < argc; i++)
        {
            uint8_t byte = hex_to_byte(argv[i]);
            if (byte == 0xFF)
            {
                snprintf(log_buf, sizeof(log_buf), "Error: invalid hex byte '%s' (must be two hex digits)", argv[i]);
                cli_printf("%s\r\n", log_buf);
                return -1;
            }
            if (send_len >= sizeof(send_buf))
            {
                snprintf(log_buf, sizeof(log_buf), "Error: too many bytes, max %d", (int)sizeof(send_buf));
                cli_printf("%s\r\n", log_buf);
                return -1;
            }
            send_buf[send_len++] = byte;
        }
    }
    // 分支2：普通文本AT指令，拼接空格+结尾\r\n
    else
    {
        for (int i = 1; i < argc; i++)
        {
            send_len += snprintf((char *)send_buf + send_len, sizeof(send_buf) - send_len, "%s", argv[i]);
            if (i < argc - 1)
                send_len += snprintf((char *)send_buf + send_len, sizeof(send_buf) - send_len, " ");
        }
        // 追加AT标准结尾 \r\n
        send_len += snprintf((char *)send_buf + send_len, sizeof(send_buf) - send_len, "\r\n");
        // 超长二次兜底校验
        if (send_len >= sizeof(send_buf))
        {
            snprintf(log_buf, sizeof(log_buf), "Error: Command too long");
            cli_printf("%s\r\n", log_buf);
            return -1;
        }
    }

    // 统一异步发送调用
    uint16_t ret = Cat1Svr_send_async(&AO_Cat1Svr, send_buf, send_len);
#if 0
    switch (ret)
    {
        case APP_DRV_BUSY:
            snprintf(log_buf, sizeof(log_buf), "Error: UART busy, send failed");
            break;
        case APP_DRV_SUCCESS:
            if (is_hex_raw)
            {
                int off = snprintf(log_buf, sizeof(log_buf), "Sent %d bytes (hex): ", send_len);
                for (uint16_t i = 0; i < send_len && off < (int)sizeof(log_buf)-4; i++)
                    off += snprintf(log_buf + off, sizeof(log_buf) - off, "%02X ", send_buf[i]);
            }
            else
            {
                snprintf(log_buf, sizeof(log_buf), "Sent: %.*s", send_len, send_buf);
            }
            break;
        default:
            snprintf(log_buf, sizeof(log_buf), "Error: Send data failed, ret:%u", ret);
            break;
    }

    // 全程仅此处最终打印一次日志，符合你要求
    cli_printf("%s\r\n", log_buf);
#endif
    return 0;
}

CLI_CMD_REGISTER("at", "Send raw AT command (with \\r\\n) or binary (at hex 55 AA 01)", cmd_at1);
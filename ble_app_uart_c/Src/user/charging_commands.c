/**
 *****************************************************************************************
 *
 * @file charging_commands.c
 *
 * @brief Charging IC Commands Implementation.
 *
 *****************************************************************************************
 * @attention
 *  #####Copyright (c) 2024
 *  All rights reserved.
 *
 *****************************************************************************************
 */

#include "eta69631.h"
#include "app_log.h"
#include <string.h>
#include <stdlib.h>

/*
 * DEFINES
 *****************************************************************************************
 */

#define CHARGING_CMD_MAX_LEN  64
#define MAX_ARGS              5

/*
 * LOCAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */

/**
 *****************************************************************************************
 * @brief Parse command line arguments.
 * @param[in] cmd: Command string.
 * @param[out] argc: Pointer to store argument count.
 * @param[out] argv: Array to store argument pointers.
 * @return true if successful, false otherwise.
 *****************************************************************************************
 */
static bool parse_command(const char *cmd, int *argc, char *argv[])
{
    char buffer[CHARGING_CMD_MAX_LEN];
    char *token;
    int count = 0;
    
    if (!cmd || !argc || !argv)
    {
        return false;
    }
    
    /* Copy command to buffer for tokenization */
    strncpy(buffer, cmd, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';
    
    /* Tokenize the command */
    token = strtok(buffer, " ");
    while (token != NULL && count < MAX_ARGS)
    {
        argv[count++] = token;
        token = strtok(NULL, " ");
    }
    
    *argc = count;
    return true;
}

/**
 *****************************************************************************************
 * @brief Handle 'status' command.
 * @param[in] argc: Argument count.
 * @param[in] argv: Argument array.
 *****************************************************************************************
 */
static void handle_status_cmd(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    
    eta69631_print_status();
}

/**
 *****************************************************************************************
 * @brief Handle 'enable' command.
 * @param[in] argc: Argument count.
 * @param[in] argv: Argument array.
 *****************************************************************************************
 */
static void handle_enable_cmd(int argc, char *argv[])
{
    if (argc < 2)
    {
        APP_LOG_ERROR("Usage: enable <on|off>");
        return;
    }
    
    if (strcmp(argv[1], "on") == 0)
    {
        if (eta69631_enable_charging(true))
        {
            APP_LOG_INFO("Charging enabled");
        }
        else
        {
            APP_LOG_ERROR("Failed to enable charging");
        }
    }
    else if (strcmp(argv[1], "off") == 0)
    {
        if (eta69631_enable_charging(false))
        {
            APP_LOG_INFO("Charging disabled");
        }
        else
        {
            APP_LOG_ERROR("Failed to disable charging");
        }
    }
    else
    {
        APP_LOG_ERROR("Invalid argument. Use 'on' or 'off'");
    }
}

/**
 *****************************************************************************************
 * @brief Handle 'current' command.
 * @param[in] argc: Argument count.
 * @param[in] argv: Argument array.
 *****************************************************************************************
 */
static void handle_current_cmd(int argc, char *argv[])
{
    if (argc < 2)
    {
        APP_LOG_ERROR("Usage: current <value in mA>");
        return;
    }
    
    int current = atoi(argv[1]);
    if (current < 64 || current > 5056)
    {
        APP_LOG_ERROR("Current must be between 64-5056 mA");
        return;
    }
    
    if (eta69631_set_charge_current((uint16_t)current))
    {
        APP_LOG_INFO("Charge current set to %d mA", current);
    }
    else
    {
        APP_LOG_ERROR("Failed to set charge current");
    }
}

/**
 *****************************************************************************************
 * @brief Handle 'voltage' command.
 * @param[in] argc: Argument count.
 * @param[in] argv: Argument array.
 *****************************************************************************************
 */
static void handle_voltage_cmd(int argc, char *argv[])
{
    if (argc < 2)
    {
        APP_LOG_ERROR("Usage: voltage <value in mV>");
        return;
    }
    
    int voltage = atoi(argv[1]);
    if (voltage < 3504 || voltage > 4624)
    {
        APP_LOG_ERROR("Voltage must be between 3504-4624 mV");
        return;
    }
    
    if (eta69631_set_charge_voltage((uint16_t)voltage))
    {
        APP_LOG_INFO("Charge voltage set to %d mV", voltage);
    }
    else
    {
        APP_LOG_ERROR("Failed to set charge voltage");
    }
}

/**
 *****************************************************************************************
 * @brief Handle 'input_limit' command.
 * @param[in] argc: Argument count.
 * @param[in] argv: Argument array.
 *****************************************************************************************
 */
static void handle_input_limit_cmd(int argc, char *argv[])
{
    if (argc < 2)
    {
        APP_LOG_ERROR("Usage: input_limit <value in mA>");
        return;
    }
    
    int limit = atoi(argv[1]);
    if (limit < 100 || limit > 3250)
    {
        APP_LOG_ERROR("Input limit must be between 100-3250 mA");
        return;
    }
    
    if (eta69631_set_input_current_limit((uint16_t)limit))
    {
        APP_LOG_INFO("Input current limit set to %d mA", limit);
    }
    else
    {
        APP_LOG_ERROR("Failed to set input current limit");
    }
}

/**
 *****************************************************************************************
 * @brief Handle 'info' command.
 * @param[in] argc: Argument count.
 * @param[in] argv: Argument array.
 *****************************************************************************************
 */
static void handle_info_cmd(int argc, char *argv[])
{
    (void)argc;
    (void)argv;
    
    eta69631_battery_info_t battery_info;
    if (eta69631_get_battery_info(&battery_info))
    {
        APP_LOG_INFO("=== Battery Information ===");
        APP_LOG_INFO("Battery Voltage: %d mV", battery_info.bat_voltage);
        APP_LOG_INFO("System Voltage: %d mV", battery_info.sys_voltage);
        APP_LOG_INFO("Charge Current: %d mA", battery_info.charge_current);
        APP_LOG_INFO("==========================");
    }
    else
    {
        APP_LOG_ERROR("Failed to get battery information");
    }
}

/**
 *****************************************************************************************
 * @brief Handle 'help' command.
 *****************************************************************************************
 */
static void handle_help_cmd(void)
{
    APP_LOG_INFO("=== Charging Commands ===");
    APP_LOG_INFO("status                  - Show charging status");
    APP_LOG_INFO("enable <on|off>         - Enable/disable charging");
    APP_LOG_INFO("current <mA>            - Set charge current (64-5056 mA)");
    APP_LOG_INFO("voltage <mV>            - Set charge voltage (3504-4624 mV)");
    APP_LOG_INFO("input_limit <mA>        - Set input current limit (100-3250 mA)");
    APP_LOG_INFO("info                    - Show battery information");
    APP_LOG_INFO("help                    - Show this help message");
    APP_LOG_INFO("=========================");
}

/*
 * GLOBAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */

/**
 *****************************************************************************************
 * @brief Process charging command.
 * @param[in] cmd: Command string.
 *****************************************************************************************
 */
void process_charging_command(const char *cmd)
{
    int argc = 0;
    char *argv[MAX_ARGS];
    
    if (!cmd || strlen(cmd) == 0)
    {
        return;
    }
    
    /* Parse command */
    if (!parse_command(cmd, &argc, argv))
    {
        APP_LOG_ERROR("Failed to parse command");
        return;
    }
    
    if (argc == 0)
    {
        return;
    }
    
    /* Process command */
    if (strcmp(argv[0], "status") == 0)
    {
        handle_status_cmd(argc, argv);
    }
    else if (strcmp(argv[0], "enable") == 0)
    {
        handle_enable_cmd(argc, argv);
    }
    else if (strcmp(argv[0], "current") == 0)
    {
        handle_current_cmd(argc, argv);
    }
    else if (strcmp(argv[0], "voltage") == 0)
    {
        handle_voltage_cmd(argc, argv);
    }
    else if (strcmp(argv[0], "input_limit") == 0)
    {
        handle_input_limit_cmd(argc, argv);
    }
    else if (strcmp(argv[0], "info") == 0)
    {
        handle_info_cmd(argc, argv);
    }
    else if (strcmp(argv[0], "help") == 0)
    {
        handle_help_cmd();
    }
    else
    {
        APP_LOG_ERROR("Unknown command: %s. Type 'help' for available commands.", argv[0]);
    }
}

/**
 *****************************************************************************************
 * @brief Handle UART data as command.
 * @param[in] data: Pointer to UART data.
 * @param[in] length: Data length.
 *****************************************************************************************
 */
void handle_uart_command(uint8_t *data, uint16_t length)
{
    char cmd[CHARGING_CMD_MAX_LEN + 1];
    
    if (!data || length == 0 || length > CHARGING_CMD_MAX_LEN)
    {
        return;
    }
    
    /* Copy data to command buffer */
    memcpy(cmd, data, length);
    cmd[length] = '\0';
    
    /* Remove newline/carriage return if present */
    if (cmd[length - 1] == '\n' || cmd[length - 1] == '\r')
    {
        cmd[length - 1] = '\0';
    }
    
    /* Process command */
    process_charging_command(cmd);
}

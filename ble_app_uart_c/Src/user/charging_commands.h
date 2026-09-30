/**
 *****************************************************************************************
 *
 * @file charging_commands.h
 *
 * @brief Charging IC Commands Header File.
 *
 *****************************************************************************************
 * @attention
 *  #####Copyright (c) 2024
 *  All rights reserved.
 *
 *****************************************************************************************
 */

#ifndef _CHARGING_COMMANDS_H_
#define _CHARGING_COMMANDS_H_

#include <stdint.h>

/*
 * GLOBAL FUNCTION DECLARATION
 *****************************************************************************************
 */

/**
 *****************************************************************************************
 * @brief Process charging command.
 * @param[in] cmd: Command string.
 *****************************************************************************************
 */
void process_charging_command(const char *cmd);

/**
 *****************************************************************************************
 * @brief Handle UART data as command.
 * @param[in] data: Pointer to UART data.
 * @param[in] length: Data length.
 *****************************************************************************************
 */
void handle_uart_command(uint8_t *data, uint16_t length);

#endif /* _CHARGING_COMMANDS_H_ */

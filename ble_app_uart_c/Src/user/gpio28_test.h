/**
 *****************************************************************************************
 *
 * @file gpio28_test.h
 *
 * @brief GPIO28 Test Header for ETA69631 Charging IC.
 *
 *****************************************************************************************
 * @attention
 *  #####Copyright (c) 2024
 *  All rights reserved.
 *
 *****************************************************************************************
 */

#ifndef _GPIO28_TEST_H_
#define _GPIO28_TEST_H_

#include <stdbool.h>

/**
 *****************************************************************************************
 * @brief Test GPIO28 configuration for ETA69631 SDA.
 * @return true if GPIO28 is configured correctly, false otherwise.
 *****************************************************************************************
 */
bool test_gpio28_config(void);

/**
 *****************************************************************************************
 * @brief Test AON_GPIO4 and AON_GPIO5 configuration.
 * @return true if AON GPIOs are configured correctly, false otherwise.
 *****************************************************************************************
 */
bool test_aon_gpio_config(void);

/**
 *****************************************************************************************
 * @brief Run complete GPIO test for ETA69631.
 *****************************************************************************************
 */
void run_gpio_test_for_eta69631(void);

#endif /* _GPIO28_TEST_H_ */
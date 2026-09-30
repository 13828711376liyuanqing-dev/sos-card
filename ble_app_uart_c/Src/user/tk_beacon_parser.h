/**
 * @file tk_beacon_parser.h
 * @brief TK Beacon 广播数据解析器
 */

#ifndef TK_BEACON_PARSER_H
#define TK_BEACON_PARSER_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "ble_gapm.h"
/* ----------------------------------------------------------------------------
// 用户配置区（可在包含本文件前覆盖）
case BLE_GAPM_EVT_ADV_REPORT:
        {
                const ble_gap_evt_adv_report_t *p_adv = &p_evt->evt.gapm_evt.params.adv_report;
                tk_beacon_process(p_adv,true);
// ----------------------------------------------------------------------------
*/
// 日志宏（用户需自行定义，如映射到 printf 或项目日志系统）
#ifndef printf
#define printf APP_LOG_INFO
#endif
#ifndef TK_BEACON_LOG_RAW
#define TK_BEACON_LOG_RAW  APP_LOG_RAW_INFO
#endif

// MAC 地址前缀过滤条件（默认 19:18:FC，可修改）
#ifndef TK_BEACON_MAC_PREFIX
#define TK_BEACON_MAC_PREFIX {0x19, 0x18, 0xFC}
#endif

// AD 类型定义（若 SDK 已提供，可移除）
#ifndef GAP_ADTYPE_FLAGS
#define GAP_ADTYPE_FLAGS                    0x01
#endif
#ifndef GAP_ADTYPE_MANUFACTURER_SPECIFIC
#define GAP_ADTYPE_MANUFACTURER_SPECIFIC    0xFF
#endif

// ----------------------------------------------------------------------------
// 数据结构
// ----------------------------------------------------------------------------

/**
 * @brief TK Beacon 广播数据内容结构
 */
typedef struct {
    uint8_t flags;          // 标志位
    uint8_t apple_pre[4];   // Apple 前缀 (4字节)
    uint8_t uuid[16];       // 16字节 UUID
    uint16_t major;         // Major 值
    uint16_t minor;         // Minor 值
    uint8_t last_byte;      // 最后一个字节 (0xCD)
} tk_beacon_data_t;

// ----------------------------------------------------------------------------
// 解析函数
// ----------------------------------------------------------------------------

/**
 * @brief 解析 TK Beacon 广播数据
 * @param p_data 指向广播数据起始的指针（原始 AD 结构）
 * @param length 广播数据总长度
 * @param p_out 输出解析结果
 * @return true 解析成功，false 失败
 */
static inline bool tk_beacon_parse(const uint8_t *p_data, uint8_t length, tk_beacon_data_t *p_out)
{
    if (!p_data || !p_out || length == 0) {
        return false;
    }

    uint8_t offset = 0;
    bool found_flags = false;
    bool found_mfg = false;

    while (offset + 1 < length) {
        uint8_t ad_len = p_data[offset];
        if (ad_len == 0) break;
        if (offset + ad_len + 1 > length) break;

        uint8_t ad_type = p_data[offset + 1];
        const uint8_t *ad_data = p_data + offset + 2;
        uint8_t data_len = ad_len - 1;

        if (ad_type == GAP_ADTYPE_FLAGS && data_len >= 1) {
            p_out->flags = ad_data[0];
            found_flags = true;
        }
        else if (ad_type == GAP_ADTYPE_MANUFACTURER_SPECIFIC && data_len >= 25) {
            memcpy(p_out->apple_pre, ad_data, 4);
            memcpy(p_out->uuid, ad_data + 4, 16);
            p_out->major = (uint16_t)((ad_data[20] << 8) | ad_data[21]);
            p_out->minor = (uint16_t)((ad_data[22] << 8) | ad_data[23]);
            p_out->last_byte = ad_data[24];
            found_mfg = true;
        }

        offset += (ad_len + 1);
    }

    return found_flags && found_mfg;
}

/**
 * @brief 处理广播报告（内置 MAC 前缀过滤）
 * @param p_adv 指向广播报告结构体的指针（类型为 ble_gap_evt_adv_report_t*）
 * @param log_enable 是否打印解析结果
 * @return true 匹配并解析成功，false 失败
 */
// 必须保持和应用一致的函数签名：返回bool，参数 p_adv, addr[6], *rssi, *data
static inline bool tk_beacon_process(const void *p_adv, uint8_t addr[6], int8_t *rssi, tk_beacon_data_t *data)
{
    // 1. 空指针安全检查
    const ble_gap_evt_adv_report_t *adv = (const ble_gap_evt_adv_report_t *)p_adv;
    if (adv == NULL || addr == NULL || rssi == NULL || data == NULL) {
        return false;
    }

    // 2. 过滤广播类型（只处理合法Beacon广播）
    if ((adv->adv_type != BLE_GAP_ADV_TYPE_ADV_IND) &&
        (adv->adv_type != BLE_GAP_ADV_TYPE_ADV_SCAN_IND) &&
        (adv->adv_type != BLE_GAP_ADV_TYPE_ADV_NONCONN_IND)) {
        return false;
    }

    // 3. 拷贝MAC地址到输出 addr[6]（按蓝牙地址顺序复制）
    const uint8_t *mac_addr = adv->broadcaster_addr.gap_addr.addr;
    for (uint8_t i = 0; i < 6; i++) {
        addr[i] = mac_addr[i];
    }

    // 4. 过滤指定MAC前缀（0xFC:18:19:xx:xx:xx）
    if (!(addr[5] == 0x19 && addr[4] == 0x18 && addr[3] == 0xFC)) {
        return false;
    }

    // 5. 解析Beacon数据 → 输出到 data
    if (!tk_beacon_parse(adv->data, adv->length, data)) {
        return false;
    }

    // 6. 输出RSSI到 *rssi
    *rssi = adv->rssi;

    // 7. 打印调试信息（保持你原有格式）
    // printf("Recv BLE rssi = %d dB, len = %u, Address: %02X:%02X:%02X:%02X:%02X:%02X\n",
    //        *rssi, adv->length,
    //        addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);

    // printf("Parsed successfully:\n");
    // printf("  flags = 0x%02X\n", data->flags);
    // printf("  apple_pre = %02X %02X %02X %02X\n",
    //        data->apple_pre[0], data->apple_pre[1],
    //        data->apple_pre[2], data->apple_pre[3]);

    // TK_BEACON_LOG_RAW("UUID = ");
    // for (int i = 0; i < 16; i++) {
    //     TK_BEACON_LOG_RAW("%02X ", data->uuid[i]);
    // }
    // TK_BEACON_LOG_RAW("\n");

    // printf("  major = %d (0x%04X)\n", data->major, data->major);
    // printf("  minor = %d (0x%04X)\n", data->minor, data->minor);
    // printf("  last_byte = 0x%02X\n", data->last_byte);

    // 8. 全部成功 → 返回true（上层就会发送Q_NEW事件）
    return true;
}

#endif /* TK_BEACON_PARSER_H */
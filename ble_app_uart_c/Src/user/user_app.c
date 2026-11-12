/**
 *****************************************************************************************
 *
 * @file user_app.c
 *
 * @brief User function Implementation.
 *
 */
/*
 * INCLUDE FILES
 *****************************************************************************************
 */
#include "user_app.h"
#include "transport_scheduler.h"
#include "user_periph_setup.h"
#include "ble_scanner.h"
#include "utility.h"
#include "app_log.h"
#include "app_error.h"
#include "gus.h"
#include "tk_beacon_parser.h"
#include "app.h"
#include "cli.h"
#include "yp001_scan_sched.h"
/* SAM | 2026-10-13 15:00 +08:00 | Add actual GATT server for sealed factory BLE tool. */
#include "factory/yp001_factory_ble.h"

#if APP_LOG_STORE_ENABLE
#include "app_log_dump_port.h"
#endif

/*

 * DEFINES
 *****************************************************************************************
 */
/**@brief Gapm config data. */
#define APP_SCAN_INTERVAL                   100             /**< Determines scan interval(in units of 0.625 ms). */
#define APP_SCAN_WINDOW                     100              /**< Determines scan window(in units of 0.625 ms). */
#define APP_SCAN_DURATION                   0               /**< Duration of the scanning(in units of 10 ms). */
#define APP_CONN_INTERVAL_MIN               6               /**< Minimal connection interval(in unit of 1.25ms). */
#define APP_CONN_INTERVAL_MAX               24              /**< Maximal connection interval(in unit of 1.25ms). */
#define APP_CONN_SLAVE_LATENCY              0               /**< Slave latency. */
#define APP_CONN_SUP_TIMEOUT                400             /**< Connection supervisory timeout(in unit of 10 ms). */

#define MAX_MTU_DEFUALT                     247             /**< Defualt length of maximal MTU acceptable for device. */
#define MAX_MPS_DEFUALT                     247             /**< Defualt length of maximal packet size acceptable for device. */
#define MAX_NB_LECB_DEFUALT                 2              /**< Defualt length of maximal number of LE Credit based connection. */
#define MAX_TX_OCTET_DEFUALT                251             /**< Default maximum transmitted number of payload octets. */
#define MAX_TX_TIME_DEFUALT                 2120            /**< Defualt maximum packet transmission time. */

#define UART_UUID_LEN                       16              /**< Defualt UART UUID length. */
/*
 * LOCAL VARIABLE DEFINITIONS
 *****************************************************************************************
 */
static const char     s_target_name[] = "Goodix_UART";                                          /**< Target name string. */
static const uint8_t  s_target_addr[SYS_BD_ADDR_LEN] = {0x13, 0x00, 0xcf, 0x3e, 0xcb, 0xea};    /**< Target board address. */
static const uint8_t  s_target_uuid[UART_UUID_LEN] = {GUS_SERVICE_UUID};                        /**< Target uuid string. */
static bool g_beacon_process_enable = true;  // 默认开启

/* YP_BEACON_DEFER_BEGIN */
/* SAM | 2026-11-05 +08:00 | SDK callbacks can arrive with BASEPRI set; copy legacy Beacon reports here and call QP only from foreground to avoid qv_port:110. */
#define YP_BEACON_DEFER_CAP 8U
#define YP_BEACON_DEFER_BYTES 31U
typedef struct {
    ble_gap_evt_adv_report_t report;
    uint8_t data[YP_BEACON_DEFER_BYTES];
} yp_beacon_pending_t;
static yp_beacon_pending_t s_beacon_pending[YP_BEACON_DEFER_CAP];
static volatile uint8_t s_beacon_write;
static volatile uint8_t s_beacon_read;
static volatile uint32_t s_beacon_deferred_dropped;
static volatile uint32_t s_beacon_deferred_delivered;

static void beacon_report_defer(const ble_gap_evt_adv_report_t *report)
{
    uint8_t addr[6];
    int8_t rssi;
    tk_beacon_data_t decoded;
    uint8_t write, next;
    if (!report || !report->data || report->length > YP_BEACON_DEFER_BYTES ||
        !tk_beacon_process(report, addr, &rssi, &decoded)) return;
    write = s_beacon_write;
    next = (uint8_t)((write + 1U) % YP_BEACON_DEFER_CAP);
    if (next == s_beacon_read) {
        ++s_beacon_deferred_dropped;
        return;
    }
    s_beacon_pending[write].report = *report;
    memcpy(s_beacon_pending[write].data, report->data, report->length);
    s_beacon_pending[write].report.data = s_beacon_pending[write].data;
    __DMB();
    s_beacon_write = next;
}

void yp_beacon_deferred_poll(void)
{
    uint8_t budget = 4U;
    if (__get_IPSR() != 0U || __get_BASEPRI() != 0U || __get_PRIMASK() != 0U) return;
    if (!g_beacon_process_enable) {
        s_beacon_read = s_beacon_write;
        __DMB();
        return;
    }
    while (budget-- && s_beacon_read != s_beacon_write) {
        uint8_t read = s_beacon_read;
        ble_gap_evt_adv_report_t report;
        uint8_t data[YP_BEACON_DEFER_BYTES];
        __DMB();
        report = s_beacon_pending[read].report;
        memcpy(data, s_beacon_pending[read].data, report.length);
        report.data = data;
        __DMB();
        s_beacon_read = (uint8_t)((read + 1U) % YP_BEACON_DEFER_CAP);
        BeaconDataEvt_send(&report);
        yp_scan_sched_on_adv_report(&report);
        ++s_beacon_deferred_delivered;
    }
}
/* YP_BEACON_DEFER_END */

/* SAM | 2026-10-08 22:08 +08:00 | Enable phone discovery and connection;
 * location scanning remains deferred. Follow SDK ble_app_uart GAP setup. */
#define YP001_BLE_NAME "YP001"

static ble_gap_adv_time_param_t s_adv_time;
static bool s_adv_ready;
static bool s_adv_active;
static uint8_t s_phone_conn = 0xFF;
static const uint8_t s_phone_adv[] = {
    6, BLE_GAP_AD_TYPE_COMPLETE_NAME, 'Y', 'P', '0', '0', '1'
};

static void phone_advertising_start(void)
{
    if (!s_adv_ready || s_phone_conn != 0xFF) return;
    sdk_err_t err = ble_gap_adv_start(0, &s_adv_time);
    APP_LOG_INFO("[BLE] ADV request name=%s result=0x%04X", YP001_BLE_NAME, err);
}

static void phone_advertising_init(void)
{
    ble_gap_adv_param_t param = {0};
    sdk_err_t err = ble_gap_device_name_set(BLE_GAP_WRITE_PERM_DISABLE,
                         (uint8_t *)YP001_BLE_NAME, sizeof(YP001_BLE_NAME) - 1U);
    if (err != SDK_SUCCESS) {
        APP_LOG_ERROR("[BLE] name setup failed: 0x%04X", err);
        return;
    }
    param.adv_intv_min = 160; /* 100 ms, units of 0.625 ms. */
    param.adv_intv_max = 240;
    param.adv_mode = BLE_GAP_ADV_TYPE_ADV_IND;
    param.chnl_map = BLE_GAP_ADV_CHANNEL_37_38_39;
    param.disc_mode = BLE_GAP_DISC_MODE_GEN_DISCOVERABLE;
    param.filter_pol = BLE_GAP_ADV_ALLOW_SCAN_ANY_CON_ANY;
    err = ble_gap_adv_param_set(0, BLE_GAP_OWN_ADDR_STATIC, &param);
    if (err == SDK_SUCCESS)
        err = ble_gap_adv_data_set(0, BLE_GAP_ADV_DATA_TYPE_DATA,
                                  s_phone_adv, sizeof(s_phone_adv));
    if (err != SDK_SUCCESS) {
        APP_LOG_ERROR("[BLE] advertising setup failed: 0x%04X", err);
        return;
    }
    s_adv_time.duration = 0;
    s_adv_time.max_adv_evt = 0;
    s_adv_ready = true;
    phone_advertising_start();
}

/*
 * LOCAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */
/**
 *****************************************************************************************
 *@brief Handle ble scanner module event.
 *****************************************************************************************
 */
static void ble_scanner_evt_handler(ble_scanner_evt_t *p_evt)
{
    sdk_err_t    error_code;

    switch (p_evt->evt_type)
    {
        case BLE_SCANNER_EVT_CONNECTED:
            error_code = ble_gattc_mtu_exchange(p_evt->param.conn_idx);
            APP_ERROR_CHECK(error_code);
            break;

        case BLE_SCANNER_EVT_FILTER_MATCH:
            APP_LOG_INFO("Found target device.");
            break;

        default:
            break;
    }
}

/**
 *****************************************************************************************
 *@brief Initialize the GAP parameters.
 *****************************************************************************************
 */
static void gap_params_init(void)
{
    sdk_err_t   error_code;

    error_code = ble_gap_l2cap_params_set(MAX_MTU_DEFUALT, MAX_MPS_DEFUALT, MAX_NB_LECB_DEFUALT);
    APP_ERROR_CHECK(error_code);

    error_code = ble_gap_data_length_set(MAX_TX_OCTET_DEFUALT, MAX_TX_TIME_DEFUALT);
    APP_ERROR_CHECK(error_code);

    ble_gap_pref_phy_set(BLE_GAP_PHY_ANY, BLE_GAP_PHY_ANY);
}

/**
 *****************************************************************************************
 *@brief Initialize the BLE scan module.
 *****************************************************************************************
 */
static void gap_scan_init(void)
{
    sdk_err_t                 error_code;
    ble_scanner_init_t        scan_init;
    // ble_scanner_filter_data_t filter_data;

    memset(&scan_init, 0x00, sizeof(ble_scanner_init_t));
    // memset(&filter_data, 0x00, sizeof(ble_scanner_filter_data_t));
    
    scan_init.scan_param.scan_type      = BLE_GAP_SCAN_ACTIVE;
    scan_init.scan_param.scan_mode      = BLE_GAP_SCAN_GEN_DISC_MODE;
    scan_init.scan_param.scan_dup_filt  = BLE_GAP_SCAN_FILT_DUPLIC_EN;
    scan_init.scan_param.use_whitelist  = false;
    scan_init.scan_param.interval       = APP_SCAN_INTERVAL;
    scan_init.scan_param.window         = APP_SCAN_WINDOW;
    scan_init.scan_param.timeout        = APP_SCAN_DURATION;
    scan_init.conn_param.type           = BLE_GAP_INIT_TYPE_DIRECT_CONN_EST;
    // scan_init.conn_param.interval_min   = APP_CONN_INTERVAL_MIN;
    // scan_init.conn_param.interval_max   = APP_CONN_INTERVAL_MAX;
    // scan_init.conn_param.slave_latency  = APP_CONN_SLAVE_LATENCY;
    // scan_init.conn_param.sup_timeout    = APP_CONN_SUP_TIMEOUT;
    // scan_init.connect_auto              = false;
    // scan_init.err_handler               = NULL;
    // scan_init.evt_handler               = ble_scanner_evt_handler;

    // filter_data.svr_uuid.length         = UART_UUID_LEN;
    // filter_data.svr_uuid.p_data         = s_target_uuid;
    // filter_data.dev_name.length         = strlen(s_target_name);
    // filter_data.dev_name.p_data         = (uint8_t *)s_target_name;
    // filter_data.target_addr.addr_type   = BLE_GAP_ADDR_TYPE_PUBLIC;
    // memcpy(filter_data.target_addr.gap_addr.addr, s_target_addr, SYS_BD_ADDR_LEN);

    // ble_scanner_filter_set(BLE_SCANNER_UUID_FILTER | BLE_SCANNER_ADDR_FILTER, &filter_data);

    error_code = ble_scanner_init(&scan_init);
    APP_ERROR_CHECK(error_code);

    // ble_scanner_filter_enable(BLE_SCANNER_FILTER_ALL_MATCH);

    APP_LOG_WARNING("BLE scan disabled: scan start triggers INVSTATE HardFault on YP001.");
}

/**
 *****************************************************************************************
 *@brief Handle event of Goodix UART Client.
 *****************************************************************************************
 */
static void gus_c_evt_process(gus_c_evt_t *p_evt)
{
    sdk_err_t   error_code;

    APP_LOG_DEBUG("GUS Client Event: Type=%d, ConnIdx=%d, Length=%d",
                  p_evt->evt_type, p_evt->conn_idx, p_evt->length);

    switch (p_evt->evt_type)
    {
        case GUS_C_EVT_DISCOVERY_COMPLETE:
            APP_LOG_INFO("GUS Service discovery completed (ConnIdx: %d).", p_evt->conn_idx);
            APP_LOG_DEBUG("Enabling TX Notification...");
            error_code = gus_c_tx_notify_set(p_evt->conn_idx, true);
            APP_ERROR_CHECK(error_code);
            transport_flag_set(BLE_TX_FLOW_ON, true);
            APP_LOG_DEBUG("TX Notification enabled, BLE_TX_FLOW_ON flag set.");
            break;

        case GUS_C_EVT_TX_NTF_SET_SUCCESS:
            APP_LOG_INFO("TX Notification enabled successfully (ConnIdx: %d).", p_evt->conn_idx);
            APP_LOG_DEBUG("Enabling Flow Control Notification...");
            error_code = gus_c_flow_ctrl_notify_set(p_evt->conn_idx, true);
            APP_ERROR_CHECK(error_code);
            break;

        case GUS_C_EVT_FLOW_CTRL_NTF_SET_SUCCESS:
            APP_LOG_INFO("Flow Control Notification enabled (ConnIdx: %d).", p_evt->conn_idx);
            transport_flag_set(BLE_FLOW_CTRL_ENABLE, true);
            APP_LOG_DEBUG("BLE_FLOW_CTRL_ENABLE flag set.");
            break;

        case GUS_C_EVT_PEER_DATA_RECEIVE:
            APP_LOG_DEBUG("Data received from peer (ConnIdx: %d, Length: %d bytes).",
                         p_evt->conn_idx, p_evt->length);
            ble_to_uart_push(p_evt->p_data, p_evt->length);
            break;

        case GUS_C_EVT_TX_FLOW_OFF:
            APP_LOG_INFO("TX Flow Control: OFF (ConnIdx: %d).", p_evt->conn_idx);
            transport_flag_set(BLE_TX_FLOW_ON, false);
            APP_LOG_DEBUG("BLE_TX_FLOW_ON flag cleared.");
            break;

        case GUS_C_EVT_TX_FLOW_ON:
            APP_LOG_INFO("TX Flow Control: ON (ConnIdx: %d).", p_evt->conn_idx);
            transport_flag_set(BLE_TX_FLOW_ON, true);
            APP_LOG_DEBUG("BLE_TX_FLOW_ON flag set.");
            break;

        case GUS_C_EVT_TX_CPLT:
            APP_LOG_DEBUG("TX Complete (ConnIdx: %d).", p_evt->conn_idx);
            transport_flag_set(BLE_TX_CPLT, true);
            APP_LOG_DEBUG("BLE_TX_CPLT flag set, continuing send...");
            transport_ble_continue_send();
            break;

        default:
            APP_LOG_DEBUG("Unhandled GUS Client event: %d", p_evt->evt_type);
            break;
    }
}

/**
 *****************************************************************************************
 * @brief Deal MTU exchange task.
 *****************************************************************************************
 */
static void app_mtu_exchange_handler(uint8_t conn_idx)
{
    sdk_err_t   error_code;

    APP_LOG_INFO("Starting GUS Service discovery (ConnIdx: %d)...", conn_idx);
    error_code = gus_c_disc_srvc_start(conn_idx);
    APP_ERROR_CHECK(error_code);
    APP_LOG_DEBUG("GUS Service discovery started.");
}

/**
 *****************************************************************************************
 * @brief Deal device disconnect task.
 *
 * @param[in] conn_idx: index of connection.
 * @param[in] disconnect_reason: disconnect reason.
 *****************************************************************************************
 */
static void app_disconnected_handler(uint8_t conn_idx, const uint8_t disconnect_reason)
{
    APP_LOG_INFO("Handling disconnection (ConnIdx: %d, Reason: 0x%02X)...", conn_idx, disconnect_reason);

    APP_LOG_DEBUG("Reinitializing BLE transport...");
    transport_ble_init();
    APP_LOG_DEBUG("BLE transport reinitialized.");

    /* SAM | 2026-10-08 22:08 +08:00 | Restore phone discovery on disconnect. */
    s_phone_conn = 0xFF;
    /* SAM | 2026-10-13 15:00 +08:00 | Drop factory permission and queued traffic on disconnect. */
    yp_factory_ble_disconnected(conn_idx);
    s_adv_active = false;
    phone_advertising_start();
}

/*
 * GLOBAL FUNCTION DEFINITIONS
 *****************************************************************************************
 */
void ble_evt_handler(const ble_evt_t *p_evt)
{
	//APP_LOG_INFO("ble_evt_handler evt_id = 0x%x",p_evt->evt_id);
    ble_scanner_evt_on_ble_capture(p_evt);
    switch(p_evt->evt_id)
    {
        case BLE_COMMON_EVT_STACK_INIT:
            APP_LOG_INFO("BLE Stack Initialized.");
            ble_app_init();
            break;

        case BLE_GAPM_EVT_SCAN_START:
            if (BLE_SUCCESS != p_evt->evt_status)
            {
                APP_LOG_WARNING("Scan start failed (Error: 0x%02X).", p_evt->evt_status);
            }
            else
            {
                APP_LOG_INFO("BLE Scanning started.");
            }
            break;

        case BLE_GAPM_EVT_SCAN_STOP:
            /* SAM | 2026-11-07 12:18 +08:00 | Confirm the periodic stop barrier using the controller event, not the API return. */
            yp_scan_sched_on_radio_stop(p_evt->evt_status == BLE_SUCCESS);
            if (BLE_GAP_STOPPED_REASON_TIMEOUT == p_evt->evt.gapm_evt.params.scan_stop.reason)
            {
                APP_LOG_INFO("Scan stopped: Timeout.");
            }
            else
            {
                APP_LOG_INFO("Scan stopped (Reason: %d).", p_evt->evt.gapm_evt.params.scan_stop.reason);
            }
            break;

        case BLE_GAPM_EVT_ADV_REPORT:
        {
                const ble_gap_evt_adv_report_t *p_adv = &p_evt->evt.gapm_evt.params.adv_report;
                if (g_beacon_process_enable)  // 添加开关判断
                {
                    beacon_report_defer(p_adv);
                }
        }
            break;

        case BLE_GAPC_EVT_CONNECTED:
            if (BLE_SUCCESS == p_evt->evt_status)
            {
                APP_LOG_INFO("BLE Connection established (ConnIdx: %d).", p_evt->evt.gapc_evt.index);
                /* SAM | 2026-10-08 22:08 +08:00 | Track phone link state. */
                s_phone_conn = p_evt->evt.gapc_evt.index;
                s_adv_active = false;
            }
            else
            {
                APP_LOG_WARNING("Connection attempt failed (Error: 0x%02X).", p_evt->evt_status);
            }
            break;

        case BLE_GAPC_EVT_DISCONNECTED:
            if (BLE_SUCCESS == p_evt->evt_status)
            {
                APP_LOG_INFO("BLE Disconnected (ConnIdx: %d, Reason: 0x%02X).",
                           p_evt->evt.gapc_evt.index,
                           p_evt->evt.gapc_evt.params.disconnected.reason);
                app_disconnected_handler(p_evt->evt.gapc_evt.index, p_evt->evt.gapc_evt.params.disconnected.reason);
            }
            break;

        case BLE_GAPC_EVT_CONN_PARAM_UPDATE_REQ:
            APP_LOG_DEBUG("Connection parameter update requested (ConnIdx: %d).", p_evt->evt.gapc_evt.index);
            ble_gap_conn_param_update_reply(p_evt->evt.gapc_evt.index, true);
            break;

        case BLE_GATT_COMMON_EVT_MTU_EXCHANGE:
            if (BLE_SUCCESS == p_evt->evt_status)
            {
                APP_LOG_INFO("MTU Exchange completed (ConnIdx: %d, MTU: %d).",
                           p_evt->evt.gapc_evt.index,
                           p_evt->evt.gatt_common_evt.params.mtu_exchange.mtu);
                update_mtu_size(p_evt->evt.gatt_common_evt.params.mtu_exchange.mtu);
                /* SAM | 2026-10-08 22:08 +08:00 | Do not invoke the
                 * uninitialized GUS client on this phone-facing link. */
                #if APP_LOG_STORE_ENABLE
                lms_update_mtu_size(p_evt->evt.gatt_common_evt.params.mtu_exchange.mtu);
                #endif
            }
            else
            {
                APP_LOG_WARNING("MTU Exchange failed (Error: 0x%02X).", p_evt->evt_status);
            }
            break;

        /* SAM | 2026-10-08 22:08 +08:00 | Confirm asynchronous ADV events. */
        case BLE_GAPM_EVT_ADV_START:
            s_adv_active = (p_evt->evt_status == BLE_SUCCESS);
            APP_LOG_INFO("[BLE] ADV started=%u name=%s status=0x%04X",
                         s_adv_active, YP001_BLE_NAME, p_evt->evt_status);
            break;
        case BLE_GAPM_EVT_ADV_STOP:
            s_adv_active = false;
            APP_LOG_INFO("[BLE] ADV stopped status=0x%04X", p_evt->evt_status);
            break;
        default:
            APP_LOG_DEBUG("Unhandled BLE event: 0x%04X", p_evt->evt_id);
            break;
    }
}

void ble_app_init(void)
{
    ble_gap_bdaddr_t  bd_addr;
    sdk_version_t version;
    sdk_err_t    error_code;

    APP_LOG_INFO("=== BLE Application Initialization ===");

    // Get SDK version
    sys_sdk_verison_get(&version);
    APP_LOG_INFO("Goodix BLE SDK V%d.%d.%d (commit %x)",
                 version.major, version.minor, version.build, version.commit_id);

    // Get local Bluetooth address
    error_code = ble_gap_addr_get(&bd_addr);
    APP_ERROR_CHECK(error_code);
    APP_LOG_INFO("Local Board Address: %02X:%02X:%02X:%02X:%02X:%02X",
                 bd_addr.gap_addr.addr[5],
                 bd_addr.gap_addr.addr[4],
                 bd_addr.gap_addr.addr[3],
                 bd_addr.gap_addr.addr[2],
                 bd_addr.gap_addr.addr[1],
                 bd_addr.gap_addr.addr[0]);
    /* SAM | 2026-10-08 22:08 +08:00 | Report the phone-facing role. */
    APP_LOG_INFO("YP001 connectable BLE peripheral starting.");

    // Initialize transport layers
    APP_LOG_DEBUG("Initializing BLE transport...");
    transport_ble_init();
    APP_LOG_DEBUG("Initializing UART transport...");
    transport_uart_init();
    APP_LOG_DEBUG("Transport layers initialized.");

    // Initialize GUS Client
    // APP_LOG_DEBUG("Initializing GUS Client...");
    // error_code = gus_client_init(gus_c_evt_process);
    // APP_ERROR_CHECK(error_code);
    // APP_LOG_DEBUG("GUS Client initialized.");

	#if APP_LOG_STORE_ENABLE
    app_log_dump_service_init();
	#endif
    // Initialize GAP parameters and start scanning
    APP_LOG_DEBUG("Initializing GAP parameters...");
    gap_params_init();
    /* SAM | 2026-10-13 15:00 +08:00 | SDK ble_app_uart initializes GUS before advertising. */
    yp_factory_ble_init();
    APP_LOG_DEBUG("Configuring BLE scanning...");
    gap_scan_init();
    /* SAM | 2026-10-08 22:08 +08:00 | Start phone discovery on boot. */
    phone_advertising_init();
    APP_LOG_INFO("BLE application initialization completed.");
}

static int cmd_beacon_process_ctrl(int argc, char *argv[])
{
    if (argc < 2)
    {
        cli_printf("Usage: beacon_ctrl [on/off/status]\r\n");
        cli_printf("  on   - Enable beacon processing\r\n");
        cli_printf("  off  - Disable beacon processing\r\n");
        cli_printf("  status - Show current status\r\n");
        return -1;
    }
    
    if (strcmp(argv[1], "on") == 0)
    {
        g_beacon_process_enable = true;
        cli_printf("Beacon processing enabled\r\n");
    }
    else if (strcmp(argv[1], "off") == 0)
    {
        g_beacon_process_enable = false;
        cli_printf("Beacon processing disabled\r\n");
    }
    else if (strcmp(argv[1], "status") == 0)
    {
        cli_printf("Beacon processing is %s\r\n", 
                   g_beacon_process_enable ? "enabled" : "disabled");
    }
    else
    {
        cli_printf("Invalid parameter: %s\r\n", argv[1]);
        cli_printf("Use: on, off, or status\r\n");
        return -1;
    }
    
    return 0;
}

// 注册命令
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("beacon_ctrl", "Beacon on|off|status", cmd_beacon_process_ctrl);

/* SAM | 2026-11-05 +08:00 | Read identity, configured TX power and IRQ state because an ADV-start event alone does not prove an on-air packet. */
static int cmd_ble_status(int argc, char *argv[])
{
    ble_gap_bdaddr_t address = {0};
    int8_t tx_power = 0;
    sdk_err_t address_result;
    sdk_err_t power_result;
    (void)argv;
    if (argc != 1) return -1;
    cli_printf("[BLE] name=%s ready=%u advertising=%u conn=%u (255=none)\r\n",
               YP001_BLE_NAME, s_adv_ready, s_adv_active, s_phone_conn);
    if (!s_adv_ready) {
        cli_printf("[BLE_DIAG] identity/power query skipped: advertising setup incomplete\r\n");
        return 0;
    }
    address_result = ble_gap_addr_get(&address);
    if (address_result == SDK_SUCCESS) {
        cli_printf("[BLE_DIAG] identity=%02X:%02X:%02X:%02X:%02X:%02X type=%u\r\n",
                   address.gap_addr.addr[5], address.gap_addr.addr[4],
                   address.gap_addr.addr[3], address.gap_addr.addr[2],
                   address.gap_addr.addr[1], address.gap_addr.addr[0],
                   (unsigned)address.addr_type);
    } else {
        cli_printf("[BLE_DIAG] identity unavailable rc=0x%04X\r\n", (unsigned)address_result);
    }
    power_result = ble_gap_tx_power_get(BLE_GAP_ACTIVITY_ROLE_ADV, 0, &tx_power);
    if (power_result == SDK_SUCCESS) {
        cli_printf("[BLE_DIAG] configured_adv_tx_dbm=%d (on-air verification required)\r\n", (int)tx_power);
    } else {
        cli_printf("[BLE_DIAG] configured_adv_tx unavailable rc=0x%04X\r\n", (unsigned)power_result);
    }
    cli_printf("[BLE_DIAG] ipsr=%lu basepri=0x%02lX irq_enable sdk=%lu ble=%lu sleep=%lu\r\n",
               (unsigned long)__get_IPSR(), (unsigned long)__get_BASEPRI(),
               (unsigned long)NVIC_GetEnableIRQ(BLE_SDK_IRQn),
               (unsigned long)NVIC_GetEnableIRQ(BLE_IRQn),
               (unsigned long)NVIC_GetEnableIRQ(BLESLP_IRQn));
    /* SAM | 2026-11-05 +08:00 | Report actual deferred delivery and overflow so idle stability cannot hide a disabled Beacon path. */
    cli_printf("[BLE_DIAG] beacon_deferred delivered=%lu dropped=%lu pending=%u\r\n",
               (unsigned long)s_beacon_deferred_delivered,
               (unsigned long)s_beacon_deferred_dropped,
               (unsigned)((s_beacon_write + YP_BEACON_DEFER_CAP - s_beacon_read) % YP_BEACON_DEFER_CAP));
    return 0;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("ble_status", "Advertising/connection state", cmd_ble_status);

static int cmd_ble_scan(int argc, char *argv[])
{
    sdk_err_t result;
    if (argc != 2) {
        cli_printf("Usage: ble_scan [start|stop]\r\n");
        return -1;
    }
    if (strcmp(argv[1], "start") == 0) {
        cli_printf("[BLE_DIAG] scan start request\r\n");
        /* SAM | 2026-11-07 12:22 +08:00 | Claim before start because a pending stop event can complete inside the SDK call. */
        yp_scan_sched_radio_hold(YP_SCAN_HOLD_MANUAL, true);
        result = ble_scanner_start();
        if (result != BLE_SUCCESS && result != 0x0FU)
            yp_scan_sched_radio_hold(YP_SCAN_HOLD_MANUAL, false);
    } else if (strcmp(argv[1], "stop") == 0) {
        cli_printf("[BLE_DIAG] scan stop request\r\n");
        result = ble_scanner_stop();
        /* SAM | 2026-11-07 12:17 +08:00 | A manual stop releases its request; the SDK result remains visible below. */
        yp_scan_sched_radio_hold(YP_SCAN_HOLD_MANUAL, false);
    } else {
        cli_printf("Usage: ble_scan [start|stop]\r\n");
        return -1;
    }
    cli_printf("[BLE_DIAG] request result=0x%04X\r\n", (unsigned)result);
    return (int)result;
}
/* SAM | 2026-10-30 21:32 +08:00 | Compact help only to retain OTA signature space; command behavior unchanged. */
CLI_CMD_REGISTER("ble_scan", "BLE scan start|stop", cmd_ble_scan);

bool ble_phone_connected(void) { return s_phone_conn != 0xFFU; }
/* SAM | 2026-10-12 19:23 +08:00 | Explicit certified port contract because no OTA erase region is provisioned. */
#ifndef YP001_OTA_PORT_H
#define YP001_OTA_PORT_H
#include "yp001_ota.h"
#include "yp001_ota_usb_bench.h"
/* SAM | 2026-11-07 07:14 +08:00 | User policy: measured battery >=50 percent OR healthy live USB; 255 denotes unknown battery. */
bool yp001_ota_port_usb_power(void);
static inline bool yp001_ota_commit_power(uint8_t battery)
{
    return (battery >= 50U && battery <= 100U) || yp001_ota_port_usb_power();
}
typedef struct {
    bool known, stable, charging, alarm, call, activity, peer_stable;
    uint8_t battery;
} yp001_ota_gates;
/* SAM | 2026-10-26 +08:00 | Outer quiet rejection precedes the RX port; retain the gates used by that decision separately in RAM. Mask: unknown/alarm/call/activity/peer in bits 0..4. */
typedef struct {
    uint32_t sequence, count, token, kind, epoch, owner_phase;
    uint32_t mask, gate_bits, battery, observed_ms;
} yp001_ota_quiet_denial_t;
extern volatile yp001_ota_quiet_denial_t yp001_ota_quiet_denial;
/* SAM | 2026-10-25 +08:00 | RAM-only denial evidence, committed by sequence; no reset/retry interface. */
typedef struct {
    uint32_t sequence, count, mask, evidence[5], epoch, total, accepted, durable;
    uint32_t gate_bits, watchdog, owner_epoch, owner_phase, saved_total;
    /* SAM | 2026-10-25 +08:00 | Append peer provenance; keep the original 68-byte diagnostic prefix unchanged. */
    uint32_t peer[12];
} yp001_ota_rx_denial_t;
extern volatile yp001_ota_rx_denial_t yp001_ota_rx_denial;
/* load: 1 valid durable record, 0 certified empty, -1 unavailable/corrupt.
 * store: atomic durable write+readback of full record; false may mean uncertain write.
 * Implementations must isolate OTA erase blocks from ALL existing user data. */
bool yp001_ota_port_provisioned(void);
int yp001_ota_port_load(yp001_ota_record *record);
bool yp001_ota_port_store(const yp001_ota_record *record);
/* SAM | 2026-10-23 +08:00 | Persist B-slot progress in the existing isolated coordinator pages; never in user NVDS. */
bool yp001_ota_port_progress_load(const yp001_ota_record *owner, uint32_t *total, uint32_t *durable);
bool yp001_ota_port_progress_store(const yp001_ota_record *owner, uint32_t total, uint32_t durable);
/* SAM | 2026-10-23 +08:00 | Foreground OTA2 endpoint emits capabilities/explicit rejection until trusted storage is bound. */
void yp001_ota_port_wire(const uint8_t *frame, size_t length);
/* SAM | 2026-10-23 +08:00 | Trusted coordinator supplies bounded component size after durable ownership; UART BEGIN cannot create authority. */
bool yp001_ota_port_receive_prepare(const yp001_ota_record *owner, uint32_t total);
/* SAM | 2026-10-24 +08:00 | Read-only proof for cancelling an empty GR download, never a native CAT1 or Boot install. */
bool yp001_ota_port_retire(const yp001_ota_record *record);
bool yp001_ota_port_cancel_empty(const yp001_ota_record *owner);
void yp001_ota_port_gates(yp001_ota_gates *gates);
/* These checks require signature/model/data compatibility and actual target evidence. */
/* SAM | 2026-10-12 19:32 +08:00 | Capture trusted source because rollback results must name a permitted actual version. */
bool yp001_ota_port_source_version(const yp001_ota_record *record, char *version, size_t capacity);
/* SAM | 2026-10-24 +08:00 | completed requires actual permitted version, measured
 * healthy peer, verified installation and durable result; no vendor-pending claim. */
bool yp001_ota_port_package_ready(const yp001_ota_record *record);
/* SAM | 2026-10-23 22:30 +08:00 | Volatile signed CAT evidence; reset discards it and requires retransmission, never a new Flash region. */
void yp001_ota_port_cat_proof_reset(void);
bool yp001_ota_port_cat_proof_present(const yp001_ota_record*);
bool yp001_ota_port_cat_proof(const yp001_ota_record*,uint32_t,const uint8_t*,uint32_t,uint32_t*);
/* SAM | 2026-10-23 +08:00 | Trusted physical UART report is challenge-bound; local version/network observation remains mandatory. */
bool yp001_ota_port_cat_challenge(const yp001_ota_record*,char nonce[33]);
bool yp001_ota_port_cat_result(const yp001_ota_record*,const char *nonce,const char *actual_version,bool confirmed_report);
/* SAM | 2026-10-23 19:26 +08:00 | Boot preparation and activation are separate durable operations; neither is a download ACK. */
bool yp001_ota_port_install_prepare(const yp001_ota_record *record);
/* SAM | 2026-10-27 +08:00 | Foreground read-only activation validation: -1 refused, 0 another foreground pass required, 1 verified. Reset ends the exact outstanding command's authority. */
void yp001_ota_port_install_check_reset(void);
int yp001_ota_port_install_check_step(const yp001_ota_record *record);
bool yp001_ota_port_install_check_ready(const yp001_ota_record *record);
/* SAM | 2026-11-06 +08:00 | Current sample time/ages/flags plus verifier stage; read-only diagnostic snapshot. */
void yp001_ota_port_activation_evidence(uint32_t out[6]);
bool yp001_ota_port_install_commit(const yp001_ota_record *record);
/* SAM | 2026-10-29 21:51 +08:00 | Round-1 defect 1: ACTIVATE (PREPARED) passed safe(true) and then the Boot-journal/owner Flash writes stalled the motion sampler,
 * so the commit's own gate re-evaluation saw a >1500 ms sample and denied boot_commit_failed. This variant reuses that pre-Flash gate result
 * (same handler, same lease); every identity/receipt/Boot check is unchanged. */
bool yp001_ota_port_install_commit_prechecked(const yp001_ota_record *record);
/* SAM | 2026-10-27 +08:00 | First internal install refusal, sequence-last RAM publication. Stages 1..7: owner/Boot/receipt/generation/descriptors/gates/activation; 10..16: validation prerequisites/A/B/owner/context/Boot generation/internal stage. */
extern volatile uint32_t g_ota_install_first_error[16];
bool yp001_ota_port_completed(const yp001_ota_record *record);
/* SAM | 2026-10-23 19:26 +08:00 | Foreground reset/health service and locally authenticated durable result. */
void yp001_ota_port_poll(void);
/* SAM | 2026-10-27 +08:00 | Read-only foreground health preparation may authenticate executing A once, then yields before any short lease; installation intent alone is ineligible. */
bool yp001_ota_port_result_pending(const yp001_ota_record *record);
bool yp001_ota_port_result(const yp001_ota_record *record,yp001_ota_record *result);
/* SAM | 2026-10-23 19:26 +08:00 | A completed Boot swap must not hold CAT1 awake just to accumulate health time. */
bool yp001_ota_port_power_safe(const yp001_ota_record *record);
/* SAM | 2026-10-27 +08:00 | Narrow non-destructive recovery admission, separate from power-off/reset permission. PREPARED is not a committed install. */
bool yp001_ota_port_recovery_prepared(const yp001_ota_record *record);
bool yp001_ota_recovery_control_allowed(void);
void yp001_ota_port_reply(const char *line, size_t length);
#endif

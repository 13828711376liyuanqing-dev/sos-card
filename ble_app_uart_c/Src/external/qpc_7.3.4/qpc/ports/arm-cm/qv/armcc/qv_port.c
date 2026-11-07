#define QP_IMPL 1U
#include "qp_port.h"
#include "qsafe.h"
#ifndef __FPU_PRESENT
#define __FPU_PRESENT 1U
#endif
#include "gr55xx.h"

#define SCB_SYSPRI   ((uint32_t volatile *)0xE000ED18U)
#define NVIC_IP      ((uint32_t volatile *)0xE000E400U)
#define SCB_CPACR   *((uint32_t volatile *)0xE000ED88U)
#define FPU_FPCCR   *((uint32_t volatile *)0xE000EF34U)

extern char const QF_port_module_[];
char const QF_port_module_[] = "qv_port_armcc";

__weak void QF_int_disable_(void) {
#if (__ARM_ARCH == 6)
    __disable_irq();
#else
    if (__get_BASEPRI() != 0U) {
        Q_onError(QF_port_module_, 100);
    }
    __set_BASEPRI(QF_BASEPRI);
#endif
}

__weak void QF_int_enable_(void) {
#if (__ARM_ARCH == 6)
    __enable_irq();
#else
    if (__get_BASEPRI() == 0U) {
        Q_onError(QF_port_module_, 101);
    }
    __set_BASEPRI(0U);
#endif
}

__weak void QF_crit_entry_(void) {
    QF_int_disable_();
}

__weak void QF_crit_exit_(void) {
    QF_int_enable_();
}

void QV_init(void) {

#if (__ARM_ARCH != 6)   //--------- if ARMv7-M and higher...

    // SCB_SYSPRI[2]:  SysTick
    SCB_SYSPRI[2] = (SCB_SYSPRI[2] | (QF_BASEPRI << 24U));

    // set all 240 possible IRQ priories to QF_BASEPRI...
    for (uint_fast8_t n = 0U; n < (240U/sizeof(uint32_t)); ++n) {
        NVIC_IP[n] = (QF_BASEPRI << 24U) | (QF_BASEPRI << 16U)
                     | (QF_BASEPRI << 8U) | QF_BASEPRI;
    }

#endif                  //--------- ARMv7-M or higher

#ifdef __ARM_FP         //--------- if VFP available...
    // make sure that the FPU is enabled by setting CP10 & CP11 Full Access
    SCB_CPACR = (SCB_CPACR | ((3UL << 20U) | (3UL << 22U)));

    // FPU automatic state preservation (ASPEN) lazy stacking (LSPEN)
    FPU_FPCCR = (FPU_FPCCR | (1U << 30U) | (1U << 31U));
#endif                  //--------- VFP available
}

//============================================================================
#if (__ARM_ARCH == 6) // if ARMv6-M...

// hand-optimized quick LOG2 in assembly (no CLZ instruction in ARMv6-M)
__attribute__ ((naked))
uint_fast8_t QF_qlog2(uint32_t x) {
__asm volatile (
    "  MOVS    r1,#0            \n"
#if (QF_MAX_ACTIVE > 16U)
    "  LSRS    r2,r0,#16        \n"
    "  BEQ     QF_qlog2_1       \n"
    "  MOVS    r1,#16           \n"
    "  MOVS    r0,r2            \n"
    "QF_qlog2_1:                \n"
#endif
#if (QF_MAX_ACTIVE > 8U)
    "  LSRS    r2,r0,#8         \n"
    "  BEQ     QF_qlog2_2       \n"
    "  ADDS    r1, r1,#8        \n"
    "  MOVS    r0, r2           \n"
    "QF_qlog2_2:                \n"
#endif
    "  LSRS    r2,r0,#4         \n"
    "  BEQ     QF_qlog2_3       \n"
    "  ADDS    r1,r1,#4         \n"
    "  MOV     r0,r2            \n"
    "QF_qlog2_3:                \n"
    "  LDR     r2,=QF_qlog2_LUT \n"
    "  LDRB    r0,[r2,r0]       \n"
    "  ADDS    r0,r1,r0         \n"
    "  BX      lr               \n"
    "  .align                   \n"
    "QF_qlog2_LUT:              \n"
    "  .byte 0, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4"
    );
}

#endif // ARMv6-M

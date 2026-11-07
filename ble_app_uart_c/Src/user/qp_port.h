#ifndef GCC_KEIL_QP_PORT_WRAPPER_H
#define GCC_KEIL_QP_PORT_WRAPPER_H

#if defined(__ARMCC_VERSION) && (__ARMCC_VERSION >= 6000000)
#include "../external/qpc_7.3.4/qpc/ports/arm-cm/qv/armclang/qp_port.h"
#else
#include "../external/qpc_7.3.4/qpc/ports/arm-cm/qv/gnu/qp_port.h"
#endif

#endif

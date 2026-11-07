"""SAM | 2026-11-07 10:57 +08:00 | Exercise actual call states with QPC to catch lost SIP disconnects."""
from pathlib import Path
import argparse
import os
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
QPC = ROOT / 'ble_app_uart_c/Src/external/qpc_7.3.4/qpc'
OUT = ROOT / 'logs/svn_integration_20261107/sip_disconnect'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='green')
    args = parser.parse_args()
    out = OUT / args.label
    out.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'ble_app_uart_c/Src/user/cat1svr.c').read_text(encoding='utf-8')
    states = source[source.index('void Cat_Sip_ctor('):source.index('void Cat_Mqtts_ctor(')]
    names = re.findall(r'^QState (Cat_Sip_\w+)\(', states, re.MULTILINE)
    signals = sorted(set(re.findall(r'\b[A-Z][A-Z0-9_]*_SIG\b', states)) -
                     {'Q_ENTRY_SIG', 'Q_EXIT_SIG'})
    port = '''#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define Q_NORETURN _Noreturn void
#define QF_MAX_EPOOL 0U
#define QF_CRIT_STAT
#define QF_CRIT_ENTRY() ((void)0)
#define QF_CRIT_EXIT() ((void)0)
#include "qp.h"
'''
    (out / 'qp_port.h').write_text(port, encoding='utf-8')
    # Compile identical QPC bytes beside the host port because its source directory has a board wrapper.
    qep = out / 'qep_hsm.c'
    qep.write_bytes((QPC / 'src/qf/qep_hsm.c').read_bytes())
    preamble = r'''
#include "qp_port.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(v) do { if (!(v)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #v); exit(1); } } while (0)
typedef struct { QHsm super; } Cat_Sip;
static unsigned commands;
static char last_command[64];
static void cli_execute_string(char const *command) {
    ++commands;
    CHECK(strlen(command) < sizeof(last_command));
    strcpy(last_command, command);
}
_Noreturn void Q_onError(char const *module, int id) {
    fprintf(stderr, "QP assertion %s %d\n", module, id);
    exit(2);
}
'''
    declarations = '\n'.join(
        'QState ' + name + '(Cat_Sip * const me, ' +
        ('void const * const par);' if name == 'Cat_Sip_initial' else 'QEvt const * const e);')
        for name in names)
    checks = r'''
static void dispatch(Cat_Sip *me, unsigned sig) {
    QEvt e = QEVT_INITIALIZER(sig);
    QHsm_dispatch_(&me->super.super, &e, 0U);
}
static void connected(Cat_Sip *me) {
    Cat_Sip_ctor(me);
    QHsm_init_(&me->super.super, NULL, 0U);
    dispatch(me, SIP_DAIL_SIG);
    CHECK(commands == 1U && strcmp(last_command, "at SIP_DIAL") == 0);
    dispatch(me, CC_SPEECH_START_SIG);
    CHECK(QHsm_state(&me->super) == Q_STATE_CAST(&Cat_Sip_connected));
    commands = 0U;
}
int main(void) {
    Cat_Sip me;
    /* SAM | 2026-11-07 11:04 +08:00 | A remote end must work without a preceding local hangup. */
    connected(&me);
    dispatch(&me, SIP_DISCONNECT_SIG);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_idle));
    CHECK(commands == 0U);
    dispatch(&me, SIP_DISCONNECT_SIG);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_idle));
    CHECK(commands == 0U);
    connected(&me);
    QEvt unrelated = QEVT_INITIALIZER(Q_USER_SIG + 100U);
    QStateHandler saved_temp = me.super.super.temp.fun;
    CHECK(Cat_Sip_connected(&me, &unrelated) == Q_RET_SUPER);
    CHECK(me.super.super.temp.fun == Q_STATE_CAST(&QHsm_top));
    me.super.super.temp.fun = saved_temp;
    QHsm_dispatch_(&me.super.super, &unrelated, 0U);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_connected));
    CHECK(commands == 0U);
    dispatch(&me, SIP_HANGUP_KEY_SIG);
#ifdef CC_CALL
    CHECK(strcmp(last_command, "at CC_HANGUP") == 0);
#else
    CHECK(strcmp(last_command, "at SIP_HANGUP") == 0);
#endif
    CHECK(commands == 1U);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_connected));
    commands = 0U;
    dispatch(&me, SIP_DISCONNECT_SIG);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_idle));
    CHECK(commands == 0U);
    dispatch(&me, SIP_DISCONNECT_SIG);
    dispatch(&me, CAT1_TIMEOUT_SIG);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_idle));
    CHECK(commands == 0U);
    connected(&me);
    dispatch(&me, CC_DISCONNECT_SIG);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_idle));
    CHECK(commands == 0U);
    connected(&me);
    dispatch(&me, CAT1_TIMEOUT_SIG);
    CHECK(QHsm_state(&me.super) == Q_STATE_CAST(&Cat_Sip_idle));
    CHECK(commands == 0U);
    puts("PASS actual Cat_Sip states + real QPC: SIP/CC disconnect, hangup command, no redial, timeout, unrelated delegation.");
    return 0;
}
'''
    unit = out / 'sip_states.c'
    unit.write_text(preamble + '\nenum { HOST_FIRST_SIG = Q_USER_SIG, ' +
                    ', '.join(signals) + ' };\n' + declarations + '\n' + states + checks,
                    encoding='utf-8')
    gcc = Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
    env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ['PATH'])
    failed = False
    for mode in ('sip', 'cc'):
        exe = out / (mode + '_states.exe')
        command = [str(gcc), '-std=c11', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-parameter', '-I' + str(out), '-I' + str(QPC / 'include'),
                   str(unit), str(qep), '-o', str(exe)]
        if mode == 'cc':
            command.append('-DCC_CALL')
        build = subprocess.run(command, env=env, capture_output=True, timeout=60)
        log = build.stdout + build.stderr
        result = build
        if build.returncode == 0:
            result = subprocess.run([str(exe)], env=env, capture_output=True, timeout=20)
            log += result.stdout + result.stderr
        log += ('\nexit_code=' + str(result.returncode) + '\n').encode()
        (out / (mode + '.log')).write_bytes(log)
        print(mode + '\n' + log.decode('utf-8', 'replace'))
        failed |= result.returncode != 0
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())

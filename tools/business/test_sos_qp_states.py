"""SAM | 2026-11-04 +08:00 | Compile the actual QP bridge/parent handlers with a host queue boundary."""
from pathlib import Path
import os
import subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'logs/sos_qp_fix_20261104'
source=(ROOT/'ble_app_uart_c/Src/user/cat1svr.c').read_text(encoding='utf-8')
bridge=source[source.index('bool yp_business_port_sos(bool start)'):source.index('void start_find_device')]
parent=source[source.index('static bool s_qp_sos_started;'):source.index('QState LocaSvr_initial')]
preamble=r"""
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(v) do { if (!(v)) abort(); } while(0)
typedef unsigned QState;
typedef struct { unsigned sig; } QEvt;
typedef struct { unsigned prio; } QActive;
typedef struct { unsigned locate_type; } LocaSvr;
static QActive actor={1};
static QActive *app_state_machine=&actor;
enum {SOS_START_SIG=100,SOS_STOP_SIG,LOCATE_TYPE_SOS=10};
static unsigned queued,transitions,stop_acks;
static bool queue_ok=true,allowed=true;
static bool post(QActive *a,const QEvt *e,unsigned margin,unsigned sender) {
    (void)a;(void)margin;(void)sender;
    if (!queue_ok) return false;
    queued=e->sig;return true;
}
#define QEVT_INITIALIZER(sig) {sig}
#define QACTIVE_POST_X(a,e,m,s) post(a,e,m,s)
static bool yp_business_sos_start_allowed(void) {return allowed;}
static void yp_business_sos_stopped(void) {++stop_acks;}
static bool yp_business_start_alarm(void) {return true;}
static void LocaSvr_SOS_KEY_OK(void) {transitions=1;}
static void LocaSvr_Idle(void) {transitions=2;}
static void QHsm_top(void) {}
#define Q_TRAN(f) ((f)(),1U)
#define Q_HANDLED() 2U
#define Q_SUPER(f) ((void)(f),3U)
"""
checks=r"""
int main(void) {
    LocaSvr me={0};QEvt start={SOS_START_SIG},stop={SOS_STOP_SIG};
    app_state_machine=NULL;CHECK(!yp_business_port_sos(true));
    app_state_machine=&actor;actor.prio=0;CHECK(!yp_business_port_sos(true));
    actor.prio=1;queue_ok=false;CHECK(!yp_business_port_sos(true));
    queue_ok=true;CHECK(yp_business_port_sos(true) && queued==SOS_START_SIG);
    allowed=false;CHECK(LocaSvr_SosControl(&me,&start)==2 && transitions==0);
    allowed=true;CHECK(LocaSvr_SosControl(&me,&start)==1 && transitions==1);
    CHECK(me.locate_type==LOCATE_TYPE_SOS && s_qp_sos_started);
    transitions=0;CHECK(LocaSvr_SosControl(&me,&start)==2 && transitions==0);
    CHECK(yp_business_port_sos(false) && queued==SOS_STOP_SIG);
    CHECK(LocaSvr_SosControl(&me,&stop)==1 && transitions==2 && !s_qp_sos_started && stop_acks==1);
    me.locate_type=0;transitions=0;
    CHECK(LocaSvr_SosControl(&me,&stop)==2 && transitions==0);
    CHECK(LocaSvr_SosControl(&me,&start)==1 && transitions==1);
    puts("Actual QP handlers passed: queue admission, confirmed start, duplicate start, cancellation before dispatch, stop and restart.");
    return 0;
}
"""
unit=OUT/'qp_state_handlers.c';unit.write_text(preamble+bridge+parent+checks,encoding='utf-8')
gcc=Path(r'D:\Program Files\GUI Guider\environment\mingw\bin\gcc.exe')
env=dict(os.environ,PATH=str(gcc.parent)+os.pathsep+os.environ['PATH'])
exe=OUT/'qp_state_handlers.exe'
r=subprocess.run([str(gcc),'-std=c99','-Wall','-Wextra','-Werror',str(unit),'-o',str(exe)],env=env,capture_output=True)
log=r.stdout+r.stderr
if r.returncode==0:
    r=subprocess.run([str(exe)],env=env,capture_output=True,timeout=20);log+=r.stdout+r.stderr
(OUT/'qp_states.log').write_bytes(log);print(log.decode('utf-8','replace'))
raise SystemExit(r.returncode)

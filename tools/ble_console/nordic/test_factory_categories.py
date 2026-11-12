# SAM | 2026-11-06 +08:00 | Check actual dropdown isolation and prevent execution of a stale selection from another category.
import tkinter as tk
from com31_console import Console, is_port_busy_error, port_busy, PORT_BUSY_HINT
import com31_console
import serial

root = tk.Tk()
app = Console(root)
expected = {
    '船运模式': ('进入船运模式',),
    '工厂授权': ('按键授权',),
    'CAT1 电源': ('查询电源状态', '打开 CAT1 电源', '开启保电', '取消保电', '关闭 CAT1 模块'),
    '设备通信检查': ('检查设备通信',),
    '低功耗测试': ('进入深度睡眠（测电流）', '查询睡眠状态'),
}
assert tuple(app.feature['values']) == tuple(expected)
sent = []
app.request = lambda *args, **kwargs: sent.append((args, kwargs))
app.connected = True
for category, items in expected.items():
    app.feature.set(category)
    app.select_feature()
    assert tuple(app.action['values']) == items, category
    assert app.action.get() == items[0], category
    assert items[0] in app.ACTIONS
app.feature.set('设备通信检查')
app.select_feature()
app.action.set('关闭 CAT1 模块')
app.select_action()
assert str(app.execute_button['state']) == 'disabled'
app.run_action()
assert not sent, 'cross-category action must not execute'
# SAM | 2026-11-08 +08:00 | Single-button acceptance, progress and uncertainty are visibly distinct.
app.feature.set('船运模式');app.select_feature();app.run_action()
assert sent[-1] == (('factory',), {'action': 'SHIP_START'})
app.factory_result(dict(op='SHIP_START',ok='1',auto_phase='5',reason='remove_card_USB'))
assert app.result.get() == '命令已下达 · PASS' and app.ship_monitoring and app.ship_stage == 'started'
app.factory_result(dict(op='SHIP_STATUS',ok='1',auto_phase='1',reason='qualifying'))
assert app.result.get() == '命令已下达 · PASS' and app.ship_monitoring
app.factory_result(dict(op='SHIP_STATUS',ok='1',auto_phase='2',reason='BATFET_readback_confirmed'))
assert app.result.get() == 'PASS · 船运成功' and not app.ship_monitoring and app.ship_stage == 'confirmed'
app.factory_result(dict(op='SHIP_STATUS',ok='1',auto_phase='4',reason='BATFET_write_uncertain'))
assert app.result.get() == '结果待确认' and not app.ship_monitoring
app.factory_result(dict(op='SHIP_START',ok='0',auto_phase='3',reason='CAT1_cleanup_unavailable'))
assert app.result.get() == 'FAIL · 失败' and not app.ship_monitoring and app.ship_stage == 'failed'
# SAM | 2026-11-08 +08:00 | Forced shipment: the two remaining refusals explain themselves; no pre-condition text is shown for a forced start.
app.factory_result(dict(op='SHIP_START',ok='0',auto_phase='3',reason='OTA_guard'))
assert app.result.get() == 'FAIL · 失败' and 'OTA 安装' in app.result_detail.get() and not app.ship_monitoring
app.factory_result(dict(op='SHIP_START',ok='0',auto_phase='3',reason='CAT1_power_off_failed'))
assert app.result.get() == 'FAIL · 失败' and '强制关闭' in app.result_detail.get() and not app.ship_monitoring
app.feature.set('船运模式');app.select_feature()
assert '强制' in app.hint.get() and '无前置条件' in app.ship_notice.cget('text') and '先关闭' not in app.hint.get()
# SAM | 2026-11-08 +08:00 | The BLE drop that ends every shipment must keep a PASS, and must never turn an unconfirmed job into a green PASS.
app.feature.set('船运模式');app.select_feature();app.run_action()
app.factory_result(dict(op='SHIP_START',ok='1',auto_phase='5',reason='remove_card_USB'))
app.factory_result(dict(op='SHIP_STATUS',ok='1',auto_phase='2',reason='BATFET_readback_confirmed'))
assert app.ship_disconnect_result() and app.result.get() == 'PASS · 船运成功' and '熄屏' in app.result_detail.get()
app.feature.set('船运模式');app.select_feature();app.run_action()
app.factory_result(dict(op='SHIP_START',ok='1',auto_phase='5',reason='remove_card_USB'))
assert app.ship_disconnect_result() and app.result.get() == '已断开 · 结果待确认' and 'PASS' not in app.result.get()
# any link error text (timeout / write failed), not only 'disconnected', is judged by the stage, never red once the device confirmed
app.feature.set('船运模式');app.select_feature();app.run_action()
app.factory_result(dict(op='SHIP_START',ok='1',auto_phase='5',reason='remove_card_USB'))
app.factory_result(dict(op='SHIP_STATUS',ok='1',auto_phase='2',reason='BATFET_readback_confirmed'))
assert app.ship_disconnect_result() and app.result.get() == 'PASS · 船运成功'
app.feature.set('船运模式');app.select_feature();app.run_action()
assert app.ship_stage is None and not app.ship_disconnect_result()      # no job started: a drop is not a shipment result
# SAM | 2026-11-08 +08:00 | A busy receiver port is named plainly, using the exact driver error from the field (0x8029), and the operator can retry.
field_error = '{"message":"Error occurred opening serial port.","description":{"message":"Error occured when opening port. Errorcode: Unknown value (0x8029)"}}'
assert is_port_busy_error(field_error) and is_port_busy_error('Failed to open the nRF5 BLE driver.')
assert not is_port_busy_error('{"message":"Device disconnected"}') and not is_port_busy_error('response timeout')
class Boom(serial.SerialException): pass
real_serial = com31_console.serial.Serial
def raise_busy(*a, **k): raise serial.SerialException("could not open port 'COM31': PermissionError(13, '拒绝访问。', None, 5)")
def raise_other(*a, **k): raise serial.SerialException("could not open port 'COM31': FileNotFoundError(2, 'x')")
class Free:
    def __init__(self, *a, **k): pass
    def close(self): pass
com31_console.serial.Serial = raise_busy;  assert port_busy('COM31') is True
com31_console.serial.Serial = raise_other; assert port_busy('COM31') is None
com31_console.serial.Serial = Free;        assert port_busy('COM31') is False
com31_console.serial.Serial = real_serial
app.connected = False
app.events.put(dict(type='error', data=field_error)); app.poll()
assert app.result.get() == '接收器端口被占用' and '任务管理器' in app.result_detail.get() and 'COM' in app.result_detail.get()
assert '被占用' in app.status.get() and '0x8029' not in app.status.get() and not app.suppress_exit
# SAM | 2026-11-12 +08:00 | Deep-sleep action sends exactly the GR-whitelisted CLI line, with no confirmation (factory forced entry).
app.busy = False; app.pending_action = None; app.connected = True
app.feature.set('低功耗测试'); app.select_feature()
app.run_action()
assert sent[-1] == (('factory',), {'action': 'CLI', 'command': 'sleep_test enter force'}), sent[-1]
app.factory_result(dict(op='CLI', ok='1'))
assert app.result.get().startswith('OK') and app.factory_cli is None
app.action.set('查询睡眠状态'); app.select_action(); app.run_action()
assert sent[-1] == (('factory',), {'action': 'CLI', 'command': 'sleep_test status'})
app.factory_result(dict(op='CLI', ok='0', reason='command_not_enabled'))
assert app.result.get() == '失败'
print('sleep actions ok')
root.destroy()
print('PASS category filtering, selection reset and stale-action rejection')

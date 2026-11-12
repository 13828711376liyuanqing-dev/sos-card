# SAM | 2026-11-05 +08:00 | Serial-style GUI for the COM31 Nordic driver worker, with manual target selection.
import ctypes
import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import serial
from serial.tools import list_ports
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

BASE = Path(__file__).resolve().parent

# SAM | 2026-11-08 +08:00 | A busy receiver port must say so directly (a left-over tool window/driver holds COM31), not show a driver error code.
PORT_BUSY_HINT = ('接收器端口 {port} 被占用，没有打开。\n'
                  '常见原因：另一个“YP001 工厂测试工具”窗口还开着，或上次没有退干净。\n'
                  '处理：① 关掉其他工具窗口；② 关不掉时，到任务管理器“详细信息”里结束 pythonw.exe 和 '
                  'nRF Connect for Desktop Bluetooth Low Energy.exe；③ 还不行就把接收器拔掉重插。然后再点“打开接收器”。')
_BUSY_WORDS = ('0x8029', 'opening serial port', 'error occured when opening port', 'failed to open the nrf5 ble driver',
               'access is denied', '拒绝访问', 'permissionerror')


def is_port_busy_error(text):
    t = str(text).lower()
    return any(word in t for word in _BUSY_WORDS)


def port_busy(device):
    """True = another program holds the port, False = free, None = could not tell."""
    try:
        port = serial.Serial(device, 115200, timeout=0.1)
    except (serial.SerialException, OSError) as error:
        text = str(error)
        return True if ('PermissionError' in text or 'denied' in text.lower() or '拒绝访问' in text or 'Errno 13' in text) else None
    port.close()
    return False


_instance_mutex = None


def another_instance_running():
    """SAM | 2026-11-08 | One tool window per user: a second window can never get the receiver port anyway."""
    global _instance_mutex
    try:
        _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\YP001_FactoryTool_COM31')
        return ctypes.windll.kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    except (AttributeError, OSError):
        return False


class Console:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.events = queue.Queue(maxsize=2000)
        self.dropped = 0
        self.devices = {}
        self.buttons = []
        self.closing = False
        self.suppress_exit = False   # a deliberately killed failed driver must not overwrite the busy-port message
        # SAM | 2026-11-06 +08:00 | Mouse-only factory workflow keeps raw commands in a separate diagnostics tab.
        self.connected = False
        self.busy = False
        self.manual_ship_pending = False
        self.factory_cli = None
        self.ship_monitoring = False
        self.ship_stage = None   # SAM | 2026-11-08: None / 'started' (command accepted) / 'confirmed' (cutoff confirmed) / 'failed'
        self.ship_poll_at = 0
        self.ship_token = None
        self.token_since = 0
        self.attempted = False
        self.pending_action = None
        root.title('YP001 工厂测试工具 0.2.5')
        root.geometry('1120x820')
        root.minsize(1000, 760)
        root.option_add('*Font', ('Microsoft YaHei UI', 11))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TButton', padding=(12, 7))
        style.configure('Go.TButton', font=('Microsoft YaHei UI', 11, 'bold'), padding=(16, 7))
        panel = ttk.Frame(root, padding=20)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='YP001  工厂测试', font=('Microsoft YaHei UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='① 连接设备     ② 选择功能和操作     ③ 点击执行，查看结果', foreground='#526077').pack(anchor='w', pady=(4, 12))
        connection = ttk.LabelFrame(panel, text='1  连接设备', padding=12)
        connection.pack(fill='x')
        row = ttk.Frame(connection)
        row.pack(fill='x')
        self.port_box = ttk.Combobox(row, state='readonly', width=29)
        self.port_box.pack(side='left', padx=(0, 6))
        ttk.Button(row, text='刷新', command=self.refresh_ports).pack(side='left', padx=(0, 6))
        self.button(row, '打开接收器', self.open_dongle)
        self.button(row, '搜索设备', self.scan)
        self.button(row, '连接选中设备', self.connect)
        self.button(row, '断开', lambda: self.request('disconnect'))
        self.status = tk.StringVar(value='请插入 USB 蓝牙接收器')
        ttk.Label(connection, textvariable=self.status, wraplength=1000).pack(anchor='w', pady=6)
        self.table = ttk.Treeview(connection, columns=('name', 'address', 'type', 'rssi'), show='headings', height=3, selectmode='browse', displaycolumns=('name', 'address', 'rssi'))
        for key, title, width in [('name', '设备名称', 280), ('address', '设备地址（核对卡片）', 340), ('type', '地址类型', 100), ('rssi', '信号', 100)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width)
        self.table.pack(fill='x')
        self.tabs = ttk.Notebook(panel)
        self.tabs.pack(fill='both', expand=True, pady=(14, 0))
        factory = ttk.Frame(self.tabs, padding=16)
        serial_panel = ttk.Frame(self.tabs, padding=12)
        diagnostic = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(factory, text='工厂操作')
        self.tabs.add(serial_panel, text='串口收发')
        self.tabs.add(diagnostic, text='诊断记录')
        ttk.Label(factory, text='2  选择操作', font=('Microsoft YaHei UI', 13, 'bold')).pack(anchor='w')
        row = ttk.Frame(factory)
        row.pack(fill='x', pady=12)
        ttk.Label(row, text='大类').pack(side='left', padx=(0, 8))
        self.feature = ttk.Combobox(row, state='readonly', values=list(self.CATEGORIES), width=20)
        self.feature.current(0)
        self.feature.pack(side='left', padx=(0, 20))
        ttk.Label(row, text='分项').pack(side='left', padx=(0, 8))
        self.action = ttk.Combobox(row, state='readonly', width=24)
        self.action.pack(side='left')
        self.feature.bind('<<ComboboxSelected>>', self.select_feature)
        self.action.bind('<<ComboboxSelected>>', self.select_action)
        # SAM | 2026-11-06 +08:00 | Keep selection and execution on one row and show only the current action's short instruction.
        self.execute_button = ttk.Button(row, text='执行', style='Go.TButton', command=self.run_action, state='disabled')
        self.execute_button.pack(side='left', padx=(16, 0))
        self.hint = tk.StringVar()
        ttk.Label(factory, textvariable=self.hint, wraplength=960, justify='left', foreground='#34465d').pack(anchor='w', pady=(0, 12))
        result_box = ttk.LabelFrame(factory, text='3  执行结果', padding=16)
        result_box.pack(fill='both', expand=True, pady=(18, 0))
        self.result = tk.StringVar(value='等待连接')
        self.result_label = ttk.Label(result_box, textvariable=self.result, font=('Microsoft YaHei UI', 30, 'bold'), foreground='#526077')
        self.result_label.pack(anchor='w')
        self.result_detail = tk.StringVar(value='连接设备后，选择操作并点击执行。')
        ttk.Label(result_box, textvariable=self.result_detail, wraplength=930, justify='left').pack(anchor='w', pady=8)
        self.ship_notice = ttk.Label(result_box, text='出厂前强制执行，无前置条件：点进入船运模式，GR 会强制关闭 CAT1；按提示拔掉卡端 USB，保持电池连接；插入 5V 恢复。', foreground='#805a20')
        # SAM | 2026-11-06 +08:00 | Operator serial view contains only input and decoded device bytes, with transport diagnostics kept separate.
        serial_row = ttk.Frame(serial_panel)
        serial_row.pack(fill='x', pady=(0, 8))
        self.serial_command = ttk.Entry(serial_row)
        self.serial_command.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.serial_command.insert(0, 'fw_version')
        self.serial_command.bind('<Return>', lambda event: self.send_serial())
        self.button(serial_row, '发送', self.send_serial)
        self.button(serial_row, '开启调试打印', lambda: self.request('factory', action='SERIAL_ON'))
        self.button(serial_row, '关闭调试打印', lambda: self.request('factory', action='SERIAL_OFF'))
        # SAM | 2026-11-06 11:05 +08:00 | Keep input examples visible when connection and command status messages change.
        ttk.Label(serial_panel, text='输入串口命令（文本模式）：命令和参数用空格分隔，每次一条；回车或点击“发送”，自动加换行。',
                  foreground='#526077', wraplength=950).pack(anchor='w', pady=(0, 3))
        ttk.Label(serial_panel, text='示例：fw_version  → 查询固件版本     cat1_power status  → 查询 CAT1 电源状态',
                  foreground='#526077', wraplength=950).pack(anchor='w', pady=(0, 8))
        self.serial_status = tk.StringVar(value='连接设备后可发送命令；连续打印需先完成工厂授权。')
        ttk.Label(serial_panel, textvariable=self.serial_status, wraplength=950).pack(anchor='w', pady=(0, 8))
        serial_controls = ttk.Frame(serial_panel)
        serial_controls.pack(fill='x', pady=(0, 8))
        self.print_mode = tk.StringVar(value='调试打印：关闭')
        ttk.Label(serial_controls, textvariable=self.print_mode).pack(side='right')
        self.button(serial_controls, '按键授权', lambda: self.request('factory', action='UNLOCK'))
        ttk.Button(serial_controls, text='清空输出', command=self.clear_serial).pack(side='left')
        ttk.Button(serial_controls, text='保存串口输出', command=self.save_serial).pack(side='left', padx=8)
        serial_area = ttk.Frame(serial_panel)
        serial_area.pack(fill='both', expand=True)
        self.serial_output = tk.Text(serial_area, wrap='word', font=('Consolas', 11), background='#ffffff', foreground='#182230', state='disabled')
        serial_scroll = ttk.Scrollbar(serial_area, command=self.serial_output.yview)
        self.serial_output.configure(yscrollcommand=serial_scroll.set)
        serial_scroll.pack(side='right', fill='y')
        self.serial_output.pack(side='left', fill='both', expand=True)
        self.tabs.select(serial_panel)
        row = ttk.Frame(diagnostic)
        row.pack(fill='x')
        self.command = ttk.Entry(row)
        self.command.pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.command.insert(0, 'FT INFO 1')
        self.button(row, '发送原始指令', self.send)
        self.button(row, 'INFO 查询', lambda: self.request('info'))
        row = ttk.Frame(diagnostic)
        row.pack(fill='x', pady=8)
        ttk.Button(row, text='保存日志', command=self.save).pack(side='left')
        ttk.Button(row, text='清空显示', command=lambda: self.output.delete('1.0', 'end')).pack(side='left', padx=8)
        log_panel = ttk.Frame(diagnostic)
        log_panel.pack(fill='both', expand=True)
        self.output = tk.Text(log_panel, wrap='none', font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(log_panel, command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.output.pack(side='left', fill='both', expand=True)
        self.output.bind('<Key>', lambda event: 'break')
        self.select_feature()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_ports()
        root.after(80, self.poll)

    def clear_serial(self):
        self.serial_output.configure(state='normal')
        self.serial_output.delete('1.0', 'end')
        self.serial_output.configure(state='disabled')

    def append_serial(self, text):
        self.serial_output.configure(state='normal')
        if int(self.serial_output.index('end-1c').split('.')[0]) > 3000:
            self.serial_output.delete('1.0', '1000.0')
        self.serial_output.insert('end', text)
        self.serial_output.see('end')
        self.serial_output.configure(state='disabled')

    def send_serial(self):
        if not self.connected or self.busy:
            self.serial_status.set('请先连接设备，并等待上一操作结束。')
            return
        command = self.serial_command.get().strip()
        if not 1 <= len(command) <= 1023 or any(not 32 <= ord(c) <= 126 for c in command):
            self.serial_status.set('请输入 1～1023 个 ASCII 字符，不含换行。')
            return
        self.append_serial('> ' + command + '\n')
        self.serial_status.set('正在等待设备执行；不会自动重发。')
        self.manual_ship_pending = command == 'charger ship start'
        if self.manual_ship_pending:
            self.ship_stage = None
        self.request('factory', action='CLI', command=command)

    def save_serial(self):
        name = filedialog.asksaveasfilename(defaultextension='.log', initialfile='YP001_串口输出.log')
        if name:
            try:
                Path(name).write_text(self.serial_output.get('1.0', 'end-1c'), encoding='utf-8-sig')
            except OSError as error:
                messagebox.showerror('保存失败', str(error))

    # SAM | 2026-11-06 +08:00 | Explicit category membership keeps unrelated actions out of each dropdown as the tool grows.
    CATEGORIES = {
        '船运模式': ('进入船运模式',),
        '工厂授权': ('按键授权',),
        'CAT1 电源': ('查询电源状态', '打开 CAT1 电源', '开启保电', '取消保电', '关闭 CAT1 模块'),
        '设备通信检查': ('检查设备通信',),
        # SAM | 2026-11-12 +08:00 | Deep-sleep current test: GR sleep_test turns off CAT1/EPD rails, keeps G-sensor powered.
        '低功耗测试': ('进入深度睡眠（测电流）', '查询睡眠状态'),
    }
    # SAM | 2026-11-12 +08:00 | Fixed wireless CLI lines for factory-tab actions (GR whitelists exactly these strings).
    CLI_COMMANDS = {
        '进入深度睡眠（测电流）': 'sleep_test enter force',
        '查询睡眠状态': 'sleep_test status',
    }
    # SAM | 2026-11-08 20:30 +08:00 | Operators use one action; GR owns preparation and confirmation.
    ACTIONS = {
        '进入船运模式': ('SHIP_START', '出厂前强制执行：点击一次，GR 强制关闭 CAT1 并取消保电；设备提示后拔掉卡端 USB（保持电池连接），自动完成检查与确认。'),
        '查询电源状态': ('CAT_STATUS', '读取电源请求和保电状态；不代表模块已启动。'),
        '打开 CAT1 电源': ('CAT_ON', '打开供电；模块是否启动需看真实启动输出。'),
        '开启保电': ('CAT_HOLD_ON', '先完成工厂授权；持续供电，直到手动取消或设备重启。'),
        '取消保电': ('CAT_HOLD_OFF', '取消厂测保电并恢复正常电源策略，不立即关机。'),
        '查询船运状态': ('SHIP_STATUS', '读取船运状态；准备后等待至少 2 秒，再查询是否可确认。'),
        '按键授权': ('UNLOCK', '单独按住卡片左键后执行；成功后松开，授权有效 60 秒。'),
        '关闭 CAT1 模块': ('CAT_OFF', '请先完成工厂授权；执行后核对 CAT1 模块已下电。'),
        '准备进入船运': ('SHIP_PREP', '先授权并关闭 CAT1，接好电池、拔掉卡片 USB、松开双键，再执行准备。'),
        '确认进入船运': ('SHIP_CONFIRM', '状态可确认后 30 秒内执行；约 12 秒后关断，插入 5V 恢复。'),
        '取消本次准备': ('SHIP_CANCEL', '仅在尚未尝试断电时可取消；已确认或结果未知时插入 5V 恢复。'),
        '检查设备通信': ('INFO', '检查设备是否正常回应，不修改设备设置。'),
        '进入深度睡眠（测电流）': ('CLI', '工厂测电流：直接强制进入，不需要授权。GR 关闭 CAT1、屏幕电源和 LED，保留 G-sensor 供电，进入深度睡眠；蓝牙随即断开、搜不到。按左/右键、晃动卡片或约 5～7 分钟后自动唤醒并重启。执行时不要按着按键。'),
        '查询睡眠状态': ('CLI', '只读：查询深度睡眠测试是否在进行（醒来后会重启，正常为 active=0）。'),
    }

    def select_feature(self, event=None):
        names = self.CATEGORIES.get(self.feature.get(), ())
        self.action.set('')
        self.action['values'] = names
        if names:
            self.action.current(0)
        self.ship_notice.pack_forget()
        if self.feature.get() == '船运模式':
            self.ship_notice.pack(anchor='w', pady=(6, 0))
        self.select_action()

    def selected_action(self):
        name = self.action.get()
        if name not in self.CATEGORIES.get(self.feature.get(), ()):
            return None
        return self.ACTIONS.get(name)

    def select_action(self, event=None):
        action = self.selected_action()
        self.hint.set(action[1] if action else '请在当前大类中选择一个分项。')
        self.execute_button.configure(text='进入船运模式' if action and action[0] == 'SHIP_START' else '执行')
        self.update_execute()

    def update_execute(self):
        action = self.selected_action()
        confirm = action and action[0] == 'SHIP_CONFIRM'
        valid_token = self.ship_token and time.monotonic() - self.token_since < 28
        enabled = action and self.connected and not self.busy and (not confirm or (valid_token and not self.attempted))
        self.execute_button.configure(state='normal' if enabled else 'disabled')

    def show_result(self, title, detail, color='#526077'):
        self.result.set(title)
        self.result_detail.set(detail)
        self.result_label.configure(foreground=color)

    def run_action(self):
        action = self.selected_action()
        if not action or not self.connected or self.busy:
            return
        operation = action[0]
        values = {'action': operation}
        if operation == 'SHIP_CONFIRM':
            if not self.ship_token or self.attempted or time.monotonic() - self.token_since >= 28:
                self.show_result('失败', '确认码已失效，请重新查询或准备。', '#b42318')
                return
            if not messagebox.askyesno('确认进入船运', '设备将断电，插入 5V 才能恢复。现在执行？'):
                return
            values['token'] = self.ship_token
            self.ship_token = None
        if operation in ('SHIP_PREP', 'SHIP_CANCEL'):
            self.ship_token = None
        if operation == 'SHIP_START':
            self.ship_stage = None
        if operation == 'CLI':
            name = self.action.get()
            command = self.CLI_COMMANDS.get(name)
            if not command:
                return
            values['command'] = command
            self.factory_cli = name
            self.append_serial('> ' + command + chr(10))
        self.pending_action = operation
        self.show_result('执行中…', '正在等待设备回应，请勿重复点击。')
        self.request('factory', **values)

    # SAM | 2026-11-08 20:30 +08:00 | Poll read-only state; never replay start or confirmation after a lost response.
    def shipping_progress(self, values):
        phase = values.get('auto_phase')
        reason = values.get('reason', '')
        details = {
            'OTA_guard': '设备正在 OTA 安装过程中，为避免损坏升级而不执行；出厂前不会出现，OTA 结束后重试。',
            'CAT1_power_off_failed': 'CAT1 电源未能强制关闭，本次未断电；请检查 CAT1 电源控制后重试。',
            'business_busy': '报警、通话或找人处理中。',
            'CAT1_cleanup_unavailable': 'CAT1 电源还开着，或与 CAT1 的通信、姓名更新、报警任务尚未结束；本次未关电。请先在“CAT1 电源”里关闭 CAT1 模块，等通信断开后重试。',
            'key_pressed': '按键未松开，本次未关电。',
            'USB_wait_timeout': '等待移除卡端 USB 超时。',
            'input_state_unknown': '无法确认外部供电状态。',
            'prepare_rejected': '电池或充电芯片准备检查未通过。',
            'qualification_failed': '稳定检查失败，未继续关断。',
            'confirm_rejected': '最终检查未通过，未确认关断。',
            'cancelled': '流程已取消。',
        }
        self.ship_monitoring = phase in ('1', '5')
        self.ship_poll_at = time.monotonic() + 1
        # SAM | 2026-11-08 | Two explicit checkpoints for factory operators: (1) command accepted, (2) cutoff confirmed. A later BLE drop is expected.
        if phase in ('5', '1'):
            self.ship_stage = 'started'
        if phase == '5':
            self.show_result('命令已下达 · PASS', '第 1 步完成。请现在拔掉卡端 USB（60 秒内），保持电池连接；设备自动继续。', '#16803c')
        elif phase == '1':
            self.show_result('命令已下达 · PASS', '设备正在检查并自动确认船运关断，请稍候，不要重复点击。', '#16803c')
        elif phase == '2':
            self.ship_stage = 'confirmed'
            self.show_result('PASS · 船运成功', '关断指令已确认，约 12 秒后卡片自动断电（熄屏）。蓝牙随后断开是正常现象，请勿重复操作。需要恢复时插入 5V。', '#16803c')
        elif phase == '4':
            self.ship_stage = 'started'
            self.show_result('结果待确认', '关断写入可能已执行：卡片熄屏 = 船运成功；仍亮 = 未成功。工具不会自动重发，不要重复点击。', '#805a20')
        elif phase == '3':
            self.ship_stage = 'failed'
            self.show_result('FAIL · 失败', details.get(reason, '设备拒绝执行：' + reason), '#b42318')
        else:
            self.show_result('结果待确认', '设备未返回单命令船运状态，请核对固件版本。', '#805a20')
        self.pending_action = None

    def port_busy_failure(self):
        """The driver reported it could not open the port (e.g. 0x8029): say it plainly and let the operator retry without restarting."""
        port = (self.port_box.get() or 'COM31').split(' ')[0]
        hint = PORT_BUSY_HINT.format(port=port)
        self.show_result('接收器端口被占用', hint, '#b42318')
        self.status.set('接收器端口 ' + port + ' 被占用，请先关闭其他工具窗口')
        if self.process is not None and self.process.poll() is None:
            self.suppress_exit = True
            self.process.kill()
        self.port_box.configure(state='readonly')

    def ship_disconnect_result(self):
        """SAM | 2026-11-08 | The card powers off ~12 s after the cutoff is confirmed, so the BLE link ends. Judge by what the device confirmed before the drop."""
        if self.ship_stage == 'confirmed':
            self.show_result('PASS · 船运成功', '关断已确认，蓝牙已断开：卡片已断电（熄屏）。请勿重复操作；需要恢复时插入 5V。', '#16803c')
            return True
        if self.ship_stage == 'started':
            self.show_result('已断开 · 结果待确认', '命令已下达，但没收到最终确认就断开了。卡片已熄屏 = 船运成功；仍亮 = 未成功，重新连接后可再点一次。', '#805a20')
            return True
        return False

    def factory_result(self, values):
        operation = values['op']
        ok = values['ok'] == '1'
        if operation == 'SHIP_START' or (operation == 'SHIP_STATUS' and values.get('auto_phase', '0') != '0'):
            self.shipping_progress(values)
            return
        if operation == 'UNLOCK':
            self.serial_status.set('已授权 60 秒，请松开左键。' if ok else '授权失败：请单独按住左键，并检查业务状态。')
        if operation == 'CLI' and self.manual_ship_pending:
            self.manual_ship_pending = False
            if ok:
                self.ship_monitoring = True
                self.ship_poll_at = 0
                self.show_result('执行中…', '正在读取 GR 船运任务状态。')
        if operation == 'CLI' and getattr(self, 'factory_cli', None):
            name, self.factory_cli = self.factory_cli, None
            reason = values.get('reason', '')
            if ok and name.startswith('进入深度睡眠'):
                self.show_result('OK · 已进入深度睡眠', '现在可以测电流。蓝牙会断开；按键、晃动或约 5～7 分钟后设备唤醒并重启，之后重新搜索连接。', '#16803c')
            elif ok:
                self.show_result('OK', '查询完成，结果见“串口收发”页的设备输出。', '#16803c')
            else:
                detail = {'command_not_enabled': 'GR 固件还没有开放这个命令，需要更新 GR 固件。',
                          'physical_unlock_or_business_guard': 'GR 固件还是旧的强制规则，需要烧入 2026-11-12 之后的 GR 固件。'}.get(
                    reason, '设备拒绝进入：按键按着、OTA 进行中或已进入船运锁定，详情见“串口收发”页输出。')
                self.show_result('失败', detail, '#b42318')
            self.pending_action = None
            return
        if operation in ('CLI', 'SERIAL_ON', 'SERIAL_OFF'):
            if ok and operation in ('SERIAL_ON', 'SERIAL_OFF'):
                self.print_mode.set('调试打印：已开启（OTA 时暂停）' if operation == 'SERIAL_ON' else '调试打印：关闭')
            reason = values.get('reason', '')
            if not ok:
                detail = {'command_not_enabled': '此命令尚未开放到无线串口。',
                          'physical_unlock_or_business_guard': '请先完成工厂授权，或检查报警、通话与 OTA 状态。',
                          'ship_locked': '船运流程已锁定，请先查询船运状态。'}.get(reason, '命令执行失败，请看设备输出。')
                self.serial_status.set(detail)
                self.append_serial('[提示] ' + detail + '\n')
            else:
                self.serial_status.set({'CLI': '命令已执行，请看设备输出。', 'SERIAL_ON': '连续打印已开启；OTA 期间自动暂停。', 'SERIAL_OFF': '调试打印已关闭，待发输出已清除；手动命令仍可使用。'}[operation])
            self.pending_action = None
            return
        if operation in ('CAT_ON', 'CAT_OFF', 'CAT_STATUS', 'CAT_HOLD_ON', 'CAT_HOLD_OFF'):
            if 'rail' not in values or 'hold' not in values:
                self.show_result('OK' if ok else '失败', '旧固件仅返回请求结果；保电和完整电源状态需更新固件。', '#805a20')
                self.pending_action = None
                return
            rail = '打开' if values.get('rail') == '1' else '关闭'
            hold = '开启' if values.get('hold') == '1' else '关闭'
            detail = '电源请求：' + rail + '；保电：' + hold + '。模块真实启动请看串口输出。'
            if operation == 'CAT_HOLD_OFF' and ok:
                detail = '已取消厂测保电，恢复正常策略；未主动关闭电源。'
            if not ok:
                detail = '操作失败：请检查授权、保电、船运及 OTA 状态。'
            self.show_result('OK' if ok else '失败', detail, '#16803c' if ok else '#b42318')
            self.pending_action = None
            return
        state = values.get('state')
        if state is not None:
            self.ship_token = None
            self.attempted = values.get('attempted') == '1'
            if state == '2' and not self.attempted:
                token = values.get('token', '')
                if token.isdigit() and 0 < int(token) <= 0xffffffff:
                    self.ship_token = int(token)
                    self.token_since = time.monotonic()
        if not ok:
            reason = values.get('reason', '')
            detail = {'hold_left_only': '请单独按住左键，并确认无报警、通话或 OTA 操作。',
                      'physical_unlock_or_business_guard': '未授权、授权已过期，或设备业务条件不满足。',
                      'ship_locked': '已有船运流程，请先查询状态。'}.get(reason,
                      '设备拒绝：请检查电池、外部 5V、CAT1、按键及 OTA 配置。当前固件未返回更详细原因。')
            if self.attempted:
                detail = '断电写入结果不确定，请勿重试；插入 5V 恢复并检查实际状态。'
            self.show_result('失败', detail, '#b42318')
        elif operation == 'SHIP_CONFIRM' or state == '3':
            self.show_result('指令 OK · 待验收', '预计约 12 秒关断。请测 SYS 电压、电池电流；插入 5V 后检查恢复。', '#805a20')
        elif state == '4':
            self.show_result('失败', '准备失败或已超时。尚未尝试断电时可取消，再检查条件；已尝试时插入 5V 恢复。', '#b42318')
        else:
            details = {'INFO': '设备已正确回应，蓝牙通信正常。', 'UNLOCK': '授权 OK。请松开左键，60 秒内继续操作。',
                       'CAT_OFF': '下电请求 OK。请核对 CAT1 实际下电，再拔掉卡片 USB。',
                       'SHIP_PREP': '准备请求 OK。等待至少 2 秒，选择“查询船运状态”检查是否可确认。',
                       'SHIP_CANCEL': '本次准备已取消。'}
            if operation == 'SHIP_STATUS':
                details[operation] = {'0': '当前空闲，可以开始按键授权。', '1': '正在准备，稍后再次查询。',
                                      '2': '已准备好，请在设备确认期限内选择“确认进入船运”。'}.get(state, '已取得设备状态。')
            self.show_result('OK', details.get(operation, '设备已受理。'), '#16803c')
        self.pending_action = None
        self.update_execute()

    def refresh_ports(self):
        self.ports = {f'{p.device} | {p.description}': p for p in list_ports.comports() if p.vid == 0x1915 and p.pid == 0xC00A}
        self.port_box['values'] = list(self.ports)
        if self.ports and not self.port_box.get():
            self.port_box.current(0)
        self.status.set('请选择 Nordic Dongle 端口并打开' if self.ports else '未发现 Nordic connectivity Dongle，请插入设备后刷新端口')

    def open_dongle(self):
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo('已有驱动进程', '接收器已经打开。更换端口请关闭并重新打开本工具。')
            return
        self.process = None
        selected = self.ports.get(self.port_box.get())
        if selected is None:
            messagebox.showerror('端口无效', '请插入 Nordic Dongle 并刷新端口。')
            return
        if port_busy(selected.device):
            hint = PORT_BUSY_HINT.format(port=selected.device)
            self.show_result('接收器端口被占用', hint, '#b42318')
            self.status.set('接收器端口 ' + selected.device + ' 被占用，请先关闭其他工具窗口')
            self.log('ERROR', hint)
            messagebox.showwarning('端口被占用', hint)
            return
        try:
            env = dict(os.environ, ELECTRON_RUN_AS_NODE='1', YP001_DONGLE_PORT=selected.device)
            self.process = subprocess.Popen(
                [str(BASE / 'runtime' / 'nRF Connect for Desktop Bluetooth Low Energy.exe'), str(BASE / 'worker.js')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding='utf-8', errors='replace', bufsize=1, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            threading.Thread(target=self.read_worker, args=(self.process,), daemon=True).start()
            self.port_box.configure(state='disabled')
            self.request('open')
        except OSError as error:
            self.status.set('驱动启动失败')
            self.log('ERROR', str(error))

    def button(self, parent, title, callback):
        button = ttk.Button(parent, text=title, command=callback)
        button.pack(side='left', padx=(0, 6))
        self.buttons.append(button)

    def log(self, kind, data):
        if int(self.output.index('end-1c').split('.')[0]) > 3000:
            self.output.delete('1.0', '1000.0')
        self.output.insert('end', f'{datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")} {kind} {data}\n')
        self.output.see('end')

    def read_worker(self, proc):
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                event = {'type': 'driver', 'data': line.rstrip()}
            try:
                self.events.put(event, timeout=0.1)
            except queue.Full:
                self.dropped += 1
        self.events.put({'type': 'exit', 'data': proc.wait()})

    def poll(self):
        if self.closing:
            return
        for _ in range(150):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, data = event['type'], event.get('data')
            if kind == 'device':
                key = data['address'] + '|' + data['type']
                values = (data['name'] or '(无名称)', data['address'], data['type'], data['rssi'])
                if key in self.devices:
                    self.table.item(key, values=values)
                else:
                    self.table.insert('', 'end', iid=key, values=values)
                self.devices[key] = data
            elif kind == 'link':
                self.connected = bool(data['ready'])
                self.print_mode.set('调试打印：关闭')
                self.serial_status.set('设备已连接，可以输入命令。' if self.connected else '设备已断开；打印停止，未收到回应的命令结果未知。')
                self.ship_token = None
                self.attempted = False
                if self.connected:
                    self.ship_stage = None   # a fresh connection starts a new job
                if self.connected and self.ship_monitoring:
                    self.ship_poll_at = 0
                elif self.connected:
                    self.show_result('等待执行', '设备已连接。选择功能和操作，点击执行。')
                elif self.ship_disconnect_result():
                    pass
                elif self.result.get() not in ('指令 OK · 待验收', 'OK · 关断指令已确认'):
                    self.show_result('未连接', '连接已断开；未收到确认回应时，操作结果未知。')
                self.update_execute()
            elif kind == 'serial':
                self.append_serial(str(data))
            elif kind == 'factoryResult':
                self.factory_result(data)
            elif kind == 'done':
                self.set_busy(False)
            elif kind == 'exit':
                self.set_busy(True)
                self.connected = False
                self.ship_token = None
                self.update_execute()
                if self.suppress_exit:
                    self.suppress_exit = False
                else:
                    self.show_result('失败', '接收器驱动已退出，请重新打开工具。', '#b42318')
                    self.status.set(f'驱动进程已退出 {data}，请重新打开工具')
                self.log('EXIT', data)
            else:
                if kind == 'error' and not self.connected and is_port_busy_error(data):
                    self.port_busy_failure()
                elif kind == 'error':
                    self.serial_status.set(str(data))
                    self.print_mode.set('调试打印：状态待确认')
                    self.ship_token = None
                    self.pending_action = None
                    self.ship_monitoring = False
                    # SAM | 2026-11-08 | During/after a shipment any link error (drop, timeout, write failure) is the card powering off, not a red failure.
                    # SAM | 2026-11-12 +08:00 | A link drop right after the forced deep-sleep command is the expected radio power-off, not a failure; current must be checked on the meter.
                    sleeping = (self.factory_cli or '').startswith('进入深度睡眠')
                    self.factory_cli = None
                    if sleeping:
                        self.show_result('蓝牙已断开（预期）', '设备收到深睡命令后蓝牙断开。请点"搜索设备"：搜不到 YP001 才说明已进入深睡；仍能搜到说明没睡下去，请看 COM30 串口日志。以电流表读数为准。', '#805a20')
                    elif not self.ship_disconnect_result():
                        self.show_result('失败 / 结果未知', str(data), '#b42318')
                if kind in ('status', 'error', 'result') and not (kind == 'error' and not self.connected and is_port_busy_error(data)):
                    self.status.set(str(data))
                if kind == 'rx':
                    self.log('RX', repr(data['text']) + ' HEX=' + data['hex'])
                else:
                    self.log(kind.upper(), data)
        if self.dropped:
            self.log('WARN', f'界面事件队列溢出 {self.dropped} 条，当前日志证据不完整')
            self.dropped = 0
        if self.ship_monitoring and self.connected and not self.busy and time.monotonic() >= self.ship_poll_at:
            self.ship_poll_at = time.monotonic() + 1
            self.request('factory', action='SHIP_STATUS')
        self.update_execute()
        self.root.after(80, self.poll)

    def set_busy(self, busy):
        self.busy = busy
        self.feature.configure(state='disabled' if busy else 'readonly')
        self.action.configure(state='disabled' if busy else 'readonly')
        self.update_execute()
        for button in self.buttons:
            button.configure(state='disabled' if busy else 'normal')

    def request(self, operation, **values):
        if self.process is None or self.process.poll() is not None:
            messagebox.showerror('驱动不可用', '请重新打开工具，核对 runtime 文件完整。')
            return
        try:
            self.process.stdin.write(json.dumps(dict(op=operation, **values)) + '\n')
            self.process.stdin.flush()
            self.set_busy(True)
        except (OSError, ValueError) as error:
            self.set_busy(False)
            self.show_result('失败 / 结果未知', str(error), '#b42318')
            self.log('ERROR', str(error))

    def scan(self):
        self.table.delete(*self.table.get_children())
        self.devices.clear()
        self.request('scan')

    def connect(self):
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo('选择设备', '请扫描并核对目标设备的 BLE 地址。')
            return
        self.request('connect', key=selected[0])

    def send(self):
        value = self.command.get()
        if not 1 <= len(value) <= 63 or any(not 32 <= ord(char) <= 126 for char in value):
            messagebox.showerror('输入无效', '请输入 1～63 个可打印 ASCII 字符，不含换行。')
            return
        self.request('send', text=value)

    def save(self):
        filename = filedialog.asksaveasfilename(defaultextension='.log', filetypes=[('日志', '*.log')], initialfile='YP001_COM31.log')
        if filename:
            try:
                Path(filename).write_text(self.output.get('1.0', 'end-1c'), encoding='utf-8-sig')
            except OSError as error:
                messagebox.showerror('保存失败', str(error))

    def close(self):
        self.closing = True
        # SAM | 2026-11-08 | Watchdog: whatever blocks below, the process ends in 8 s and releases the receiver port.
        watchdog = threading.Timer(8.0, lambda: os._exit(0))
        watchdog.daemon = True
        watchdog.start()
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # kill the whole driver tree, not only its first process
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=4)
        self.root.destroy()


if __name__ == '__main__':
    if '--self-test' not in sys.argv and another_instance_running():
        guard = tk.Tk()
        guard.withdraw()
        messagebox.showwarning('已有工具在运行', '已经有一个 YP001 工厂测试工具在运行（看任务栏，或上次没有退干净）。\n请先关闭它；关不掉时，到任务管理器结束 pythonw.exe 和 nRF Connect for Desktop Bluetooth Low Energy.exe，再重新打开。')
        sys.exit(0)
    window = tk.Tk()
    console = Console(window)
    if '--self-test' in sys.argv:
        window.update()
        assert len(console.buttons) == 10
        console.factory_result(dict(op='SERIAL_ON',ok='1'))
        assert '已开启' in console.print_mode.get()
        console.factory_result(dict(op='SERIAL_OFF',ok='1'))
        assert console.print_mode.get() == '调试打印：关闭'
        assert console.command.get() == 'FT INFO 1'
        assert window.winfo_width() >= 1000
        assert console.feature.get() == '船运模式'
        console.append_serial('版本输出\n')
        console.events.put(dict(type='rx', data=dict(text='FT packet',hex='4654')))
        console.poll()
        assert console.serial_output.get('1.0','end-1c') == '版本输出\n'
        console.clear_serial()
        assert not console.serial_output.get('1.0','end-1c')
        assert str(console.execute_button['state']) == 'disabled'
        console.connected = True
        console.factory_result(dict(op='SHIP_STATUS', ok='1', state='2', token='123', attempted='0'))
        assert console.ship_token == 123
        console.factory_result(dict(op='SHIP_STATUS', ok='1', state='4', token='0', attempted='0'))
        assert console.ship_token is None and console.result.get() == '失败'
        console.factory_result(dict(op='SHIP_CONFIRM', ok='1', state='3', token='0', attempted='1'))
        assert console.result.get() == '指令 OK · 待验收'
        console.factory_result(dict(op='UNLOCK', ok='0', reason='hold_left_only'))
        assert console.result.get() == '失败'
        window.destroy()
        print('PASS GUI creation, default command, controls and layout sizing')
    else:
        window.mainloop()

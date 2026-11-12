"""YP001 e-paper LVGL page selector.

Requires: pyserial (pip install pyserial)
The firmware CLI expects one page command terminated by CR.
"""

import argparse
import threading
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # Keep the GUI importable and show a useful message on start.
    serial = None
    list_ports = None


# SAM | 2026-10-11 11:20 +08:00 | Add a small host page selector because page
# changes are intended to be exercised through the existing UART CLI.
PAGES = (
    ("screen", "默认 IMEI/二维码"),
    ("screen_main", "主页"),
    ("screen_time", "时间页"),
    ("screen_lowbat", "低电页"),
    ("screen_calling", "呼叫中"),
    ("screen_callend", "呼叫结束"),
)


class PageSelector(tk.Tk):
    def __init__(self, port=None, baud=115200):
        super().__init__()
        self.title("YP001 LVGL 页面切换")
        self.resizable(False, False)
        self.ser = None

        self.port_var = tk.StringVar(value=port or "")
        self.baud_var = tk.StringVar(value=str(baud))
        self.status_var = tk.StringVar(value="未连接")
        self._build_ui()
        self._refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        body = ttk.Frame(self, padding=12)
        body.grid()
        ttk.Label(body, text="串口").grid(row=0, column=0, sticky="w")
        self.port_box = ttk.Combobox(body, textvariable=self.port_var, width=14)
        self.port_box.grid(row=0, column=1, padx=6)
        ttk.Button(body, text="刷新", command=self._refresh_ports).grid(row=0, column=2)
        ttk.Label(body, text="波特率").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            body, textvariable=self.baud_var, values=("115200", "460800"), width=14
        ).grid(row=1, column=1, padx=6, pady=(8, 0))
        self.connect_button = ttk.Button(body, text="打开串口", command=self._toggle)
        self.connect_button.grid(row=1, column=2, pady=(8, 0))

        pages = ttk.LabelFrame(body, text="发送页面", padding=8)
        pages.grid(row=2, column=0, columnspan=3, pady=12, sticky="ew")
        for index, (name, label) in enumerate(PAGES):
            ttk.Button(
                pages,
                text=f"{label}  ({name})",
                command=lambda value=name: self._send(value),
                width=27,
            ).grid(row=index // 2, column=index % 2, padx=4, pady=4, sticky="ew")

        ttk.Label(body, textvariable=self.status_var, foreground="#444").grid(
            row=3, column=0, columnspan=3, sticky="w"
        )
        self.log = tk.Text(body, width=64, height=8, state="disabled")
        self.log.grid(row=4, column=0, columnspan=3, pady=(8, 0))

    def _refresh_ports(self):
        if list_ports is None:
            return
        ports = [item.device for item in list_ports.comports()]
        self.port_box["values"] = ports
        if not self.port_var.get() and ports:
            self.port_var.set(ports[0])

    def _toggle(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            self.connect_button.configure(text="打开串口")
            self.status_var.set("未连接")
            return
        if serial is None:
            messagebox.showerror("缺少依赖", "请先安装 pyserial：python -m pip install pyserial")
            return
        if not self.port_var.get():
            messagebox.showwarning("未选择串口", "请先选择汇顶 UART0 的 COM 口，例如 COM26")
            return
        try:
            self.ser = serial.Serial(
                self.port_var.get(), int(self.baud_var.get()), timeout=0.1,
                dsrdtr=False, rtscts=False, xonxoff=False
            )
        except (ValueError, serial.SerialException) as exc:
            messagebox.showerror("打开失败", str(exc))
            return
        self.connect_button.configure(text="关闭串口")
        self.status_var.set(f"已连接 {self.port_var.get()} / {self.baud_var.get()} 8N1")
        threading.Thread(target=self._reader, daemon=True).start()

    def _send(self, page):
        if not self.ser or not self.ser.is_open:
            messagebox.showwarning("未连接", "请先打开串口")
            return
        command = f"epd_page {page}\r".encode("ascii")
        try:
            self.ser.write(command)
            self._append(f">> epd_page {page}")
        except serial.SerialException as exc:
            self._append(f"发送失败: {exc}")

    def _reader(self):
        while self.ser and self.ser.is_open:
            try:
                line = self.ser.readline()
            except serial.SerialException:
                break
            if line:
                self.after(0, self._append, line.decode(errors="replace").rstrip())

    def _append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="YP001 LVGL 页面串口切换上位机")
    parser.add_argument("--port", help="串口，例如 COM26")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    if serial is None:
        print("缺少 pyserial，请执行: python -m pip install pyserial")
        return 2
    PageSelector(args.port, args.baud).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

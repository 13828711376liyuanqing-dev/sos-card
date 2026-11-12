"""SAM | 2026-11-13 00:17 +08:00 | Add responsive C2 display with smoothing and raw CSV capture."""
from collections import deque
import argparse
import csv
from datetime import datetime
import math
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

if __package__:
    from .c2_meter import C2Meter
else:
    from c2_meter import C2Meter


LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "c2_meter"
FIELDS = ("voltage_v", "current_ma", "power_w")


class DisplayFilter:
    """Time-based EMA avoids dependence on the host's UI refresh frequency."""
    def __init__(self, time_constant=1.0):
        self.time_constant = time_constant
        self.values = None
        self.last_time = None

    def update(self, values, now):
        if self.values is None or self.time_constant <= 0:
            self.values = dict(values)
        else:
            alpha = -math.expm1(-max(0, now - self.last_time) / self.time_constant)
            self.values = {key: self.values[key] + alpha * (value - self.values[key])
                           for key, value in values.items()}
        self.last_time = now
        return dict(self.values)


def capture(stop, events, path, meter_factory=C2Meter):
    """Worker owns USB and CSV. Only queued data crosses into the Tk thread."""
    total = 0
    error = None
    try:
        with meter_factory() as meter:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="") as stream:
                writer = None
                events.put(("started", str(path)))
                last_preview = last_flush = time.monotonic()
                sums = dict.fromkeys(FIELDS, 0.0)
                preview_count = 0
                while not stop.is_set():
                    samples = meter.read()
                    if not samples:
                        continue
                    if writer is None:
                        writer = csv.DictWriter(stream, fieldnames=samples[0].keys())
                        writer.writeheader()
                    writer.writerows(samples)
                    total += len(samples)
                    preview_count += len(samples)
                    for field in FIELDS:
                        sums[field] += sum(sample[field] for sample in samples)
                    now = time.monotonic()
                    if now - last_preview >= 0.1 or stop.is_set():
                        mean = {field: value / preview_count for field, value in sums.items()}
                        events.put(("sample", (mean, now, total)))
                        sums = dict.fromkeys(FIELDS, 0.0)
                        preview_count = 0
                        last_preview = now
                    if now - last_flush >= 1:
                        stream.flush()
                        last_flush = now
    except Exception as exc:
        error = str(exc)
    finally:
        events.put(("done", dict(samples=total, error=error, path=str(path))))


class MeterWindow:
    def __init__(self, root):
        self.root = root
        root.title("C2 电流电压采集")
        root.geometry("800x540")
        root.minsize(680, 490)
        root.configure(bg="#f1f5f9")
        self.events = queue.SimpleQueue()
        self.stop = threading.Event()
        self.worker = None
        self.closing = False
        self.history = deque()
        self.filter = DisplayFilter()
        self.last_received = None
        self.started_at = None
        self.smoothing = tk.StringVar(value="1 秒")
        self.status = tk.StringVar(value="就绪 · 请退出 ATK-C 后开始采集")
        self.filepath = tk.StringVar(value="采集记录自动保存到 logs\\c2_meter")
        self.stats = tk.StringVar(value="")
        self.values = {}
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", font=("Microsoft YaHei UI", 11), padding=(16, 9))
        style.configure("TCombobox", padding=5)
        top = tk.Frame(root, bg="#f1f5f9")
        top.pack(fill="x", padx=24, pady=(20, 16))
        tk.Label(top, text="C2 电流电压", font=("Microsoft YaHei UI", 19, "bold"),
                 bg="#f1f5f9", fg="#0f172a").pack(side="left")
        self.button = ttk.Button(top, text="开始采集", command=self.toggle)
        self.button.pack(side="right")
        cards = tk.Frame(root, bg="#f1f5f9")
        cards.pack(fill="x", padx=24)
        for index, (field, label, unit) in enumerate([
                ("voltage_v", "电压", "V"), ("current_ma", "电流", "mA"),
                ("power_w", "功率", "W")]):
            cards.columnconfigure(index, weight=1, uniform="cards")
            card = tk.Frame(cards, bg="white", padx=16, pady=12)
            card.grid(row=0, column=index, sticky="ew", padx=(0, 10 if index < 2 else 0))
            tk.Label(card, text=f"{label}  {unit}", font=("Microsoft YaHei UI", 11),
                     bg="white", fg="#64748b").pack(anchor="w")
            value = tk.StringVar(value="—")
            self.values[field] = value
            tk.Label(card, textvariable=value, font=("Segoe UI", 29, "bold"),
                     bg="white", fg="#0f172a").pack(anchor="w")
        controls = tk.Frame(root, bg="#f1f5f9")
        controls.pack(fill="x", padx=24, pady=(16, 8))
        tk.Label(controls, text="电流趋势 · 最近 30 秒", font=("Microsoft YaHei UI", 10),
                 bg="#f1f5f9", fg="#334155").pack(side="left")
        self.combo = ttk.Combobox(controls, textvariable=self.smoothing,
                                  values=["关闭", "0.5 秒", "1 秒", "2 秒"],
                                  width=7, state="readonly")
        self.combo.pack(side="right")
        tk.Label(controls, text="显示平滑", bg="#f1f5f9", fg="#475569",
                 font=("Microsoft YaHei UI", 10)).pack(side="right", padx=8)
        self.chart = tk.Canvas(root, height=180, bg="white", highlightthickness=0)
        self.chart.pack(fill="both", expand=True, padx=24)
        self.chart.bind("<Configure>", lambda event: self.draw_chart())
        footer = tk.Frame(root, bg="#f1f5f9")
        footer.pack(fill="x", padx=24, pady=14)
        self.status_label = tk.Label(footer, textvariable=self.status, anchor="w", bg="#f1f5f9",
                                    fg="#334155", font=("Microsoft YaHei UI", 10))
        self.status_label.pack(fill="x")
        tk.Label(footer, textvariable=self.stats, anchor="w", bg="#f1f5f9", fg="#64748b",
                 font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(4, 0))
        self.path_entry = ttk.Entry(footer, textvariable=self.filepath, state="readonly")
        self.path_entry.pack(fill="x", pady=(6, 0))
        tk.Label(footer, text="CSV 保存全部原始样本 · 曲线和数字按显示平滑设置更新",
                 anchor="w", bg="#f1f5f9", fg="#64748b",
                 font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(5, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.button.focus_set()
        root.after(100, self.poll)

    def toggle(self):
        if self.worker is not None:
            self.request_stop()
            return
        self.stop = threading.Event()
        self.filter = DisplayFilter()
        self.history.clear()
        self.last_received = None
        self.started_at = time.monotonic()
        self.clear_values()
        self.stats.set("")
        self.status.set("正在连接 C2…")
        path = LOG_DIR / ("c2_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".csv")
        self.worker = threading.Thread(target=capture, args=(self.stop, self.events, path), daemon=True)
        self.button.configure(text="停止采集", state="normal")
        self.worker.start()

    def request_stop(self):
        self.stop.set()
        self.button.configure(text="正在停止…", state="disabled")
        self.status.set("正在停止，保存记录并释放 USB…")

    def clear_values(self):
        for value in self.values.values():
            value.set("—")

    def poll(self):
        while not self.events.empty():
            kind, payload = self.events.get()
            if kind == "started":
                self.filepath.set(payload)
            elif kind == "sample":
                mean, received, total = payload
                self.filter.time_constant = {"关闭": 0, "0.5 秒": 0.5, "1 秒": 1, "2 秒": 2}[self.smoothing.get()]
                values = self.filter.update(mean, received)
                for field, value in values.items():
                    self.values[field].set(f"{value:.2f}" if field == "current_ma" else f"{value:.3f}")
                self.last_received = received
                self.history.append((received, values["current_ma"]))
                while self.history and received - self.history[0][0] > 30:
                    self.history.popleft()
                self.stats.set(f"已采集 {total:,} 个原始样本 · {received - self.started_at:.1f} 秒")
                if not self.stop.is_set():
                    self.status.set("正在采集 · C2 USB 已连接")
                    self.root.title(f"C2 电流电压采集 · {values['voltage_v']:.3f} V · {values['current_ma']:.2f} mA")
            elif kind == "done":
                self.worker.join()
                self.worker = None
                self.button.configure(text="开始采集", state="normal")
                if payload["error"]:
                    self.clear_values()
                    self.status.set("采集失败 · " + payload["error"])
                    self.root.title("C2 电流电压采集 · 采集失败")
                else:
                    self.status.set(f"已停止 · 最后读数 · 已保存 {payload['samples']:,} 个样本")
                    self.root.title("C2 电流电压采集 · 已停止")
        if self.worker is not None and self.last_received is not None and time.monotonic() - self.last_received > 1:
            self.clear_values()
            if not self.stop.is_set():
                self.status.set("等待新数据…")
                self.root.title("C2 电流电压采集 · 等待新数据")
        self.draw_chart()
        if self.closing and self.worker is None:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def draw_chart(self):
        self.chart.delete("all")
        width, height = self.chart.winfo_width(), self.chart.winfo_height()
        left, right, top, bottom = 58, width - 16, 18, height - 26
        if right <= left or bottom <= top:
            return
        values = [point[1] for point in self.history]
        low = min(values, default=0)
        high = max(values, default=1)
        span = max(high - low, 1)
        low, high = max(0, low - span * 0.15), high + span * 0.15
        for fraction in (0, 0.5, 1):
            y = bottom - (bottom - top) * fraction
            self.chart.create_line(left, y, right, y, fill="#e2e8f0")
            self.chart.create_text(left - 8, y, text=f"{low + (high-low)*fraction:.1f}",
                                   anchor="e", fill="#64748b", font=("Segoe UI", 9))
        self.chart.create_text(left, height - 10, text="mA", anchor="w", fill="#64748b")
        self.chart.create_text(right, height - 10, text="时间 / 秒", anchor="e", fill="#64748b")
        if len(self.history) < 2:
            return
        end = self.history[-1][0]
        points = []
        for stamp, value in self.history:
            points.extend((right - (end-stamp) / 30 * (right-left),
                           bottom - (value-low) / (high-low) * (bottom-top)))
        self.chart.create_line(*points, fill="#0284c7", width=2)

    def close(self):
        self.closing = True
        if self.worker is not None:
            self.request_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="Start capture when the window opens")
    args = parser.parse_args()
    root = tk.Tk()
    window = MeterWindow(root)
    if args.start:
        root.after(200, window.toggle)
    root.mainloop()


if __name__ == "__main__":
    main()

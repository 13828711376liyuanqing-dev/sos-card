"""ATK C2 USB voltage/current reader for Windows.

SAM | 2026-11-13 +08:00 | Read observed measurement frames through WinUSB for AI diagnostics.
"""
import argparse
import csv
import ctypes as ct
from ctypes import wintypes as wt
from datetime import datetime, timezone
import json
import math
import sys
import time
import uuid


INTERFACE_GUID = "13eb360b-bc1e-46cb-ac8b-ef3da47b4062"
HEADER = b"\xee\x04\x39"


def decode_frame(frame):
    """Decode four samples. Framing is checked, checksum remains undocumented."""
    if len(frame) != 63 or not frame.startswith(HEADER) or frame[-2:] != b"\xff\x00":
        raise ValueError("Invalid C2 measurement frame")
    samples = []
    for index in range(4):
        voltage = int.from_bytes(frame[3 + index * 3:6 + index * 3], "little") / 100000
        current = int.from_bytes(frame[15 + index * 3:18 + index * 3], "little") / 100000
        samples.append(dict(voltage_v=voltage, current_a=current,
                            current_ma=current * 1000, power_w=voltage * current))
    return samples


class FrameDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(HEADER)
            if start < 0:
                self.buffer[:] = self.buffer[-2:]
                break
            del self.buffer[:start]
            if len(self.buffer) < 63:
                break
            frame = bytes(self.buffer[:63])
            if frame[-2:] != b"\xff\x00":
                del self.buffer[0]
                continue
            frames.append(frame)
            del self.buffer[:63]
        return frames


class GUID(ct.Structure):
    _fields_ = [("data", ct.c_ubyte * 16)]


class DeviceInterface(ct.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("guid", GUID),
                ("flags", wt.DWORD), ("reserved", ct.c_void_p)]


def windows_apis():
    if sys.platform != "win32":
        raise OSError("ATK C2 WinUSB reader requires Windows")
    setup = ct.WinDLL("setupapi", use_last_error=True)
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    usb = ct.WinDLL("winusb", use_last_error=True)
    signatures = [
        (setup, "SetupDiGetClassDevsW", [ct.POINTER(GUID), wt.LPCWSTR, ct.c_void_p, wt.DWORD], ct.c_void_p),
        (setup, "SetupDiEnumDeviceInterfaces", [ct.c_void_p, ct.c_void_p, ct.POINTER(GUID), wt.DWORD, ct.POINTER(DeviceInterface)], wt.BOOL),
        (setup, "SetupDiGetDeviceInterfaceDetailW", [ct.c_void_p, ct.POINTER(DeviceInterface), ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD), ct.c_void_p], wt.BOOL),
        (setup, "SetupDiDestroyDeviceInfoList", [ct.c_void_p], wt.BOOL),
        (kernel, "CreateFileW", [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.c_void_p, wt.DWORD, wt.DWORD, ct.c_void_p], ct.c_void_p),
        (kernel, "CloseHandle", [ct.c_void_p], wt.BOOL),
        (usb, "WinUsb_Initialize", [ct.c_void_p, ct.POINTER(ct.c_void_p)], wt.BOOL),
        (usb, "WinUsb_Free", [ct.c_void_p], wt.BOOL),
        (usb, "WinUsb_SetPipePolicy", [ct.c_void_p, ct.c_ubyte, wt.DWORD, wt.DWORD, ct.c_void_p], wt.BOOL),
        (usb, "WinUsb_ReadPipe", [ct.c_void_p, ct.c_ubyte, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD), ct.c_void_p], wt.BOOL),
    ]
    for library, name, args, result in signatures:
        function = getattr(library, name)
        function.argtypes = args
        function.restype = result
    return setup, kernel, usb


def checked(result):
    if not result:
        raise ct.WinError(ct.get_last_error())
    return result


def list_devices():
    setup, _, _ = windows_apis()
    guid = GUID((ct.c_ubyte * 16).from_buffer_copy(uuid.UUID(INTERFACE_GUID).bytes_le))
    handle = setup.SetupDiGetClassDevsW(ct.byref(guid), None, None, 18)
    if handle == ct.c_void_p(-1).value:
        raise ct.WinError(ct.get_last_error())
    paths = []
    try:
        index = 0
        while True:
            interface = DeviceInterface()
            interface.cbSize = ct.sizeof(interface)
            if not setup.SetupDiEnumDeviceInterfaces(handle, None, ct.byref(guid), index, ct.byref(interface)):
                if ct.get_last_error() == 259:
                    break
                raise ct.WinError(ct.get_last_error())
            size = wt.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(handle, ct.byref(interface), None, 0, ct.byref(size), None)
            detail = ct.create_string_buffer(size.value)
            ct.cast(detail, ct.POINTER(wt.DWORD))[0] = 8 if ct.sizeof(ct.c_void_p) == 8 else 6
            checked(setup.SetupDiGetDeviceInterfaceDetailW(handle, ct.byref(interface), detail, size, None, None))
            path = ct.wstring_at(ct.addressof(detail) + 4)
            if "vid_2e88&pid_c2c2" in path.lower():
                paths.append(path)
            index += 1
    finally:
        setup.SetupDiDestroyDeviceInfoList(handle)
    return paths


class C2Meter:
    def __init__(self, path=None, timeout_ms=2000):
        if not isinstance(timeout_ms, int) or not 0 < timeout_ms < 2**32:
            raise ValueError("timeout_ms must be an integer from 1 to 4294967295")
        self.path = path
        self.timeout_ms = timeout_ms
        self.file = None
        self.interface = ct.c_void_p()
        self.decoder = FrameDecoder()

    def __enter__(self):
        _, self.kernel, self.usb = windows_apis()
        paths = [self.path] if self.path else list_devices()
        if len(paths) != 1:
            raise OSError(f"Expected one C2 meter, found {len(paths)}. Use --device for selection.")
        self.path = paths[0]
        # Exclusive access prevents two readers from splitting the measurement stream.
        self.file = self.kernel.CreateFileW(self.path, 0xC0000000, 0, None, 3, 0x40000000, None)
        if self.file == ct.c_void_p(-1).value:
            self.file = None
            raise ct.WinError(ct.get_last_error())
        try:
            checked(self.usb.WinUsb_Initialize(self.file, ct.byref(self.interface)))
            timeout = wt.ULONG(self.timeout_ms)
            checked(self.usb.WinUsb_SetPipePolicy(self.interface, 0x82, 3, ct.sizeof(timeout), ct.byref(timeout)))
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        if self.interface.value:
            self.usb.WinUsb_Free(self.interface)
            self.interface = ct.c_void_p()
        if self.file:
            self.kernel.CloseHandle(self.file)
            self.file = None

    def __exit__(self, *args):
        self.close()

    def read(self):
        deadline = time.monotonic() + self.timeout_ms / 1000
        while time.monotonic() < deadline:
            buffer = ct.create_string_buffer(4096)
            count = wt.DWORD()
            checked(self.usb.WinUsb_ReadPipe(self.interface, 0x82, buffer, len(buffer), ct.byref(count), None))
            frames = self.decoder.feed(buffer.raw[:count.value])
            if frames:
                timestamp = datetime.now(timezone.utc).isoformat()
                return [dict(timestamp_utc=timestamp, sample_index=index, **sample)
                        for frame in frames for index, sample in enumerate(decode_frame(frame))]
        raise TimeoutError("No complete C2 measurement frame before timeout")


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Must be a finite positive number")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "read", "record"])
    parser.add_argument("--device")
    parser.add_argument("--seconds", type=positive_number, default=10)
    parser.add_argument("--timeout-ms", type=int, default=2000)
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    parser.add_argument("--output", help="New output file, refuses to overwrite")
    args = parser.parse_args()
    if args.timeout_ms <= 0:
        parser.error("--timeout-ms must be positive")
    try:
        if args.command == "list":
            print(json.dumps({"devices": list_devices()}))
            return 0
        with C2Meter(args.device, args.timeout_ms) as meter:
            if args.command == "read":
                print(json.dumps(meter.read()[-1]))
                return 0
            output = open(args.output, "x", encoding="utf-8", newline="") if args.output else sys.stdout
            try:
                writer = None
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    for sample in meter.read():
                        if args.format == "csv":
                            if writer is None:
                                writer = csv.DictWriter(output, fieldnames=sample.keys())
                                writer.writeheader()
                            writer.writerow(sample)
                        else:
                            output.write(json.dumps(sample) + "\n")
                    output.flush()
            finally:
                if output is not sys.stdout:
                    output.close()
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

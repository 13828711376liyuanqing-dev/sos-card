"""SAM | 2026-10-26 +08:00 | Read frozen evidence without device access."""
import bisect
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/r6_causal_audit_20261026"
LIVE = ROOT / "logs/r6_handoff_20261026/mqtt_live"


def main():
    OUT.mkdir(exist_ok=True)
    timeline = []
    for ch in range(2):
        data = (LIVE / f"decode/D{ch}.bin").read_bytes()
        times = json.loads((LIVE / f"decode/D{ch}_times.json").read_text())
        frames = json.loads((LIVE / "decode/decode.json").read_text())["channels"][ch]["frames"]
        for frame in frames:
            at = bisect.bisect_left(times, frame["time"] - 0.00000001)
            assert abs(times[at] - frame["time"]) < 0.000001
            assert data[at:at+4] == b"OTA2"
            timeline.append(dict(frame, channel=ch, end=times[at+frame["bytes"]-1]+10/460800))
    timeline.sort(key=lambda x:x["time"])
    windows = []
    for req in timeline:
        if req["channel"] != 1 or req["type"] != 240:
            continue
        token = req["sequence"]
        ack = next((x for x in timeline if x["channel"] == 0 and x["type"] == 241 and x["sequence"] == token and x["time"] > req["time"]), None)
        release = next((x for x in timeline if x["channel"] == 1 and x["type"] == 242 and x["sequence"] == token and x["time"] > req["time"]), None)
        if not ack or not release:
            windows.append({"token":token, "complete":False})
            continue
        d0_times = json.loads((LIVE / "decode/D0_times.json").read_text())
        left = bisect.bisect_left(d0_times, ack["end"] + 0.000001)
        right = bisect.bisect_left(d0_times, release["time"])
        windows.append({"token":token, "ack_start":ack["time"], "ack_end":ack["end"], "release_start":release["time"], "release_end":release["end"], "release_denied":bool(release["offset"]), "d0_bytes_after_ack_before_release":max(0,right-left), "silence_ms":(release["time"]-ack["end"])*1000})
    (OUT / "wire_timeline.json").write_text(json.dumps(timeline,indent=2))
    (OUT / "quiet_window_audit.json").write_text(json.dumps(windows,indent=2))
    # Retain direct mask/call neighborhoods, not an invented timing estimate.
    function = "?"
    history = []
    masked = []
    for line in (OUT / "deployed_disassembly.txt").read_text().splitlines():
        if re.fullmatch(r"    [A-Za-z_][\w.$]*",line) and not line.strip().startswith(("i.","$")):
            function = line.strip()
        history.append(line)
        if re.search(r"\b(?:CPSID|MSR\s+(?:BASEPRI|PRIMASK))\b",line):
            masked.append({"function":function,"instruction":line.strip(),"preceding":history[-5:-1]})
    (OUT / "mask_sites.json").write_text(json.dumps(masked,indent=2))
    axf = ROOT / "firmware_releases/gr_uart_recovery_20261025/baseline/Objects/YP001_GR5526.axf"
    frozen = json.loads((ROOT / "firmware_releases/gr_r6_retire_recovery_20261026/frozen_build.json").read_text())
    actual = hashlib.sha256(axf.read_bytes()).hexdigest()
    assert actual == frozen["axf_sha256"]
    relevant = {}
    for path, digest in frozen["dependencies"].items():
        if Path(path).name in {"user_periph_setup.c","yp001_ota.c","yp001_ota_port.c","sensor.c","app_uart.c","app_i2c.c","app_log.c"}:
            relevant[path] = {"matches_frozen":hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,"frozen_sha256":digest}
    manifest = {"axf_sha256":actual,"matches_frozen":True,"source_check":relevant,"frame_count":len(timeline),"mask_sites":len(masked)}
    (OUT / "audit_manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({"manifest":manifest,"quiet_windows":windows,"frames_after_106s":[x for x in timeline if 106 <= x["time"] < 111]},indent=2))


if __name__ == "__main__":
    main()

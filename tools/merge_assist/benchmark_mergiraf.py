"""SAM | 2026-11-07 +08:00 | Benchmark isolated three-way proposals; never writes firmware sources or Git state."""
from pathlib import Path
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import statistics
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ("gr_src", "platform/bsp.c"),
    ("gr_src", "user/AOs.h"),
    ("gr_src", "user/business/yp001_business.c"),
    ("gr_src", "user/business/yp001_business.h"),
    ("gr_src", "user/cat1svr.c"),
    ("gr_src", "user/charger/yp001_charger.c"),
    ("gr_src", "user/yp001_scan_sched.c"),
    ("cat1", "main.lua"),
    ("cat1", "mqtts_receiver.lua"),
    ("cat1", "business_core.lua"),
    ("cat1", "ota_trial.lua"),
]


def legacy_merge(base, ours, theirs):
    spec = importlib.util.spec_from_file_location("yp001_legacy_merge", ROOT / "tools/tree_sync/merge3.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lines, count, _ = module.merge(base.split("\n"), ours.split("\n"), theirs.split("\n"))
    return "\n".join(lines), count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--legacy-case", type=Path)
    args = parser.parse_args()
    if args.legacy_case:
        d = args.legacy_case
        result, count = legacy_merge(*[(d / n).read_text(encoding="utf-8") for n in ("base", "ours", "theirs")])
        (d / "legacy_result").write_text(result, encoding="utf-8")
        print(count)
        return
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    out = args.out.resolve()
    if out.exists():
        parser.error("output directory already exists; use a fresh evidence directory")
    out.mkdir(parents=True)
    archive = Path("D:/CODEX/_archive/tree_sync_base_20261104_173820.zip")
    catalog = json.loads((ROOT / "tools/tree_sync/baseline.json").read_text(encoding="utf-8"))
    exe = ROOT / "tools/merge_assist/vendor/mergiraf-0.20.0/mergiraf.exe"
    rows = []
    originals = {}
    with zipfile.ZipFile(archive) as z:
        for number, (group, name) in enumerate(CASES):
            key = group + ":" + name
            folder = out / f"{number:02d}_{Path(name).name}"
            folder.mkdir()
            ours_path = ROOT / ("ble_app_uart_c/Src" if group == "gr_src" else "Air780EGH") / name
            theirs_path = Path("D:/SVN") / ("ble_app_uart_c/Src" if group == "gr_src" else "Air780EGH") / name
            raw = [z.read(group + "/" + name), ours_path.read_bytes(), theirs_path.read_bytes()]
            hashes = [hashlib.sha256(b).hexdigest() for b in raw]
            if hashes[0] != catalog[key]:
                raise ValueError("unproven base " + key)
            originals[str(ours_path)] = hashes[1]
            originals[str(theirs_path)] = hashes[2]
            try:
                decoded = [b.decode("utf-8-sig") for b in raw]
                encoding = "utf-8"
            except UnicodeDecodeError:
                decoded = [b.decode("latin1") for b in raw]
                encoding = "latin1-byte-preserving-transcode"
            texts = [text.replace("\r\n", "\n") for text in decoded]
            for label, text in zip(("base", "ours", "theirs"), texts):
                (folder / label).write_text(text, encoding="utf-8", newline="\n")
            row = {"file": key, "hashes": dict(zip(("base", "ours", "theirs"), hashes)),
                   "benchmark_encoding": encoding,
                   "both_changed": texts[0] != texts[1] and texts[0] != texts[2],
                   "ours_equals_theirs": texts[1] == texts[2], "engines": {}}
            commands = {
                "legacy": [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--out", str(out), "--legacy-case", str(folder)],
                "git": ["git", "-c", "gc.auto=0", "merge-file", "-p", "--diff3", "-L", "OURS", "-L", "BASE", "-L", "THEIRS", str(folder / "ours"), str(folder / "base"), str(folder / "theirs")],
                "mergiraf": [str(exe), "merge", str(folder / "base"), str(folder / "ours"), str(folder / "theirs"), "-p", name, "-o", str(folder / ("mergiraf_result" + Path(name).suffix)), "-t", "5000"],
            }
            for engine, command in commands.items():
                times = []
                outputs = []
                error = None
                for repeat in range(args.repeats):
                    started = time.perf_counter()
                    try:
                        result = subprocess.run(command, capture_output=True, timeout=12, cwd=folder)
                    except subprocess.TimeoutExpired:
                        error = "12s process timeout"
                        break
                    times.append(time.perf_counter() - started)
                    (folder / f"{engine}_{repeat}.stderr").write_bytes(result.stderr)
                    if engine == "legacy":
                        if result.returncode:
                            error = result.stderr.decode("utf-8", errors="replace")
                            break
                        merged = (folder / "legacy_result").read_bytes()
                    elif engine == "git":
                        if result.returncode < 0 or result.returncode >= 128:
                            error = f"git error {result.returncode}"
                            break
                        merged = result.stdout
                    else:
                        target = folder / ("mergiraf_result" + Path(name).suffix)
                        if result.returncode not in (0, 1) or not target.is_file():
                            error = f"mergiraf error {result.returncode}: " + result.stderr.decode("utf-8", errors="replace")
                            break
                        merged = target.read_bytes()
                    outputs.append(hashlib.sha256(merged).hexdigest())
                if error:
                    row["engines"][engine] = {"error": error, "seconds": times}
                    continue
                text = merged.decode("utf-8", errors="replace")
                target = folder / (engine + Path(name).suffix)
                target.write_bytes(merged)
                conflicts = len(re.findall(r"^<<<<<<<", text, re.M))
                row["engines"][engine] = {"median_seconds": statistics.median(times), "seconds": times,
                    "conflicts": conflicts, "conflict_lines": sum(len(m.splitlines()) for m in re.findall(r"^<<<<<<<.*?^>>>>>>>[^\n]*", text, re.M | re.S)),
                    "output_sha256": outputs[-1], "deterministic": len(set(outputs)) == 1,
                    "output": str(target.relative_to(out)),
                    "ours_diff_lines": sum(1 for line in difflib.unified_diff(texts[1].splitlines(), text.splitlines()) if line[:1] in ("+", "-") and not line.startswith(("+++", "---")))}
            rows.append(row)
            (out / "results.json").write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"file": key, "engines": {k: {a: b for a, b in v.items() if a in ("conflicts", "median_seconds", "error")} for k, v in row["engines"].items()}}, ensure_ascii=False), flush=True)
    changed = [p for p, digest in originals.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest]
    report = {"tool_version": subprocess.check_output([str(exe), "--version"]).decode().strip(), "repeats": args.repeats,
              "baseline_archive": str(archive), "input_normalization": "UTF8 files decoded strictly; mixed/invalid encoding cases use reversible Latin1 byte mapping for all three inputs; shared UTF8/LF benchmark copies only; raw hashes preserved",
              "source_paths_changed": changed, "rows": rows,
              "scope": "proposals only; protected-file policy intentionally assessed separately; no source/index/build/flash changes"}
    (out / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if changed:
        raise RuntimeError("source inputs changed during benchmark")


if __name__ == "__main__":
    main()

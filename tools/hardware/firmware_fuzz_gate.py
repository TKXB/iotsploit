"""Own-engine USBTMC firmware gate. Run explicitly on a rig, never from default hooks."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import subprocess
import sys
import time
from pathlib import Path

from iotsploit_django.adapters.filelock.resource_lease import FileResourceLease
from iotsploit_fuzzer.analysis.logger import TestLogger
from iotsploit_fuzzer.core.config import CampaignConfig
from iotsploit_fuzzer.core.fuzzing_engine import FuzzingEngine
from iotsploit_fuzzer.core.orchestrator import Orchestrator
from iotsploit_fuzzer.generators.strategy_generator import SelectedCaseGenerator
from iotsploit_fuzzer.harnesses.monitor_set_harness import MonitorSetHarness
from iotsploit_fuzzer.harnesses.usbtmc_harness import USBTMCHarness
from iotsploit_fuzzer.interfaces.usbtmc_interface import USBTMCInterface, resource_key
from iotsploit_fuzzer.monitors.health import HealthMonitor

ROOT = Path(__file__).resolve().parents[2]
QUERY = [{"op": "clear"}, {"op": "write_message"}, {"op": "request_read"}]


def load(path):
    return json.loads(Path(path).read_text())


def revision(path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()
    files = subprocess.check_output(["git", "-C", str(path), "ls-files", "-z",
                                     "--cached", "--others", "--exclude-standard"]).split(b"\0")
    digest = hashlib.sha256()
    for name in sorted(set(files) - {b""}):
        file = Path(path) / name.decode()
        digest.update(name + b"\0")
        if file.is_file():
            digest.update(file.read_bytes())
    return {"sha": git("rev-parse", "HEAD"), "content_sha256": digest.hexdigest(),
            "dirty": bool(git("status", "--porcelain"))}


def query(harness, command):
    result = harness.execute(command.encode() + b"\n", sequence=QUERY)
    if not result.ok:
        raise RuntimeError(result.error)
    return result.response.decode().strip()


class BootObservation:
    """Board-neutral boot continuity from the firmware's per-boot token."""
    def __init__(self, harness):
        self.harness = harness
        self.baseline = query(harness, "SYST:BOOT?")
        if not re.fullmatch(r"[0-9a-fA-F]{16}", self.baseline):
            raise ValueError("Firmware must expose a 64-bit SYST:BOOT? token")

    def observe(self):
        try:
            token = query(self.harness, "SYST:BOOT?")
        except (RuntimeError, UnicodeError) as exc:
            return {"health": "unavailable", "reasons": [str(exc)]}
        changed = token != self.baseline
        return {"health": "fault" if changed else "ok", "boot_id": token,
                "baseline_boot_id": self.baseline,
                "reasons": ["Unexpected firmware reboot"] if changed else []}


def run_target(name, target, rig, suites, args):
    out = args.output / name
    out.mkdir(parents=True, exist_ok=True)
    report = {"target": name, "status": "incomplete", "seed": args.seed, "phases": []}
    interface = None
    lease = FileResourceLease()
    owner = f"Firmware fuzz: {name}"
    resources = []
    try:
        manifest = load(args.manifest)
        image = manifest[target["firmware_entry"]]
        options = image["flash_options"]
        images = options["files"] if "files" in options else [{
            "address": options["address"], "path": image["path"], "sha256": options["sha256"]}]
        for entry in images:
            actual = hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
            if entry["sha256"] != actual:
                raise ValueError(f"Image checksum mismatch: {entry['path']}")
        report["images"] = images
        report["sources"] = {"python": revision(ROOT), "ui": revision(args.ui_root),
                             "firmware": revision(args.firmware_root)}
        selected = USBTMCInterface.select(rig["usb"])
        for resource in [resource_key(selected), *([rig["programmer_resource"]] if args.flash else [])]:
            lease.acquire(resource, owner)
            resources.append(resource)
        report["flashed_by_run"] = args.flash
        if args.flash:
            command = [str(args.flasher), "flash", "--device-type", image["device_type"],
                       "--port", rig["programmer"]]
            for entry in images:
                command += ["--image", f"{entry['address']}:{entry['path']}"]
            with (out / "flash.log").open("w") as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
            time.sleep(rig.get("settle_seconds", 4))
        interface = USBTMCInterface(rig["usb"])
        harness = USBTMCHarness(interface, {"timeout": 1000, "case_deadline_ms": 5000,
                                           "max_response_bytes": 8192})
        report["device"] = interface.identity
        idn = harness.preflight().decode().strip()
        report["idn"] = idn
        parts = idn.split(",")
        if len(parts) != 4 or parts[1] != target["product"] or parts[3] != image["version"]:
            raise ValueError(f"Candidate identity mismatch: {idn}")
        observer = BootObservation(harness)
        monitored = MonitorSetHarness(harness, [HealthMonitor("boot", "firmware_boot", observer.observe)])
        report["boot_id"] = observer.baseline
        log = TestLogger(str(out), metadata={"target": name, "sources": report["sources"], "images": images})
        cases = []
        for suite_name in target["suites"]:
            suite = load(suites / f"{suite_name}.json")
            for baseline in suite["baseline"]:
                response = query(harness, baseline["query"])
                if not re.search(baseline["response_regex"], response):
                    raise ValueError(f"Baseline {baseline['query']}: unexpected response {response!r}")
            for case in suite["cases"]:
                cases.append({**case, "id": f"{suite_name}:{case['id']}", "protocol_type": "usbtmc",
                              "frame_data": bytes.fromhex(case["payload_hex"]), "iterations": args.iterations})
        if not cases:
            raise ValueError("Target suites contain no executable cases")
        report["status"] = "fail"
        # All retained cases execute before mutation, regardless of discovery budget.
        replay = []
        if args.replay:
            replay = [json.loads(line) for line in args.replay.read_text().splitlines() if line]
            replay = [record for record in replay if record["target"] == name]
        for record in replay:
            harness.use_case(record["evidence"]["config"])
            result = monitored.execute(bytes.fromhex(record["evidence"]["payload_hex"]))
            log.record(log.total + 1, bytes.fromhex(record["evidence"]["payload_hex"]), result)
            if not result.ok:
                raise RuntimeError(f"Regression replay failed: {result.error}")
        report["replayed"] = len(replay)
        for case in cases:
            # Each seed must reach the firmware before its mutations.
            harness.use_case(case["protocol_config"])
            seed_result = monitored.execute(case["frame_data"])
            log.record(log.total + 1, case["frame_data"], seed_result)
            if not seed_result.ok:
                raise RuntimeError(f"Seed {case['id']} failed: {seed_result.error}")
            generator = SelectedCaseGenerator(FuzzingEngine(rng=random.Random(args.seed)), [case])
            generator.on_case = harness.use_case
            orchestrator = Orchestrator(generator, monitored, logger_backend=log,
                                        config=CampaignConfig(iterations=generator.total))
            orchestrator.run()
            stats = orchestrator.monitor.get_stats()
            report["phases"].append({"case": case["id"], "generated": generator.total, **stats})
            if orchestrator.stop_reason or stats["total_cases"] != generator.total or stats["errors"] or stats["crashes"]:
                raise RuntimeError(orchestrator.stop_reason or f"Failed/incomplete case {case['id']}")
        final = observer.observe()
        if final["health"] != "ok":
            raise RuntimeError(str(final))
        report["final_health"] = final
        report["status"] = "pass"
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        if interface is not None:
            interface.close()
        for resource in reversed(resources):
            lease.release(resource, owner)
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--targets", type=Path, default=ROOT / "conf/fuzz/targets.json")
    parser.add_argument("--rig", type=Path)
    parser.add_argument("--target", action="append")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--ui-root", type=Path)
    parser.add_argument("--firmware-root", type=Path)
    parser.add_argument("--flasher", type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--iterations", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/firmware-fuzz")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.discover:
        print(json.dumps(USBTMCInterface.discover(), indent=2))
        return 0
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    for option in ("rig", "manifest", "ui_root", "firmware_root"):
        if getattr(args, option) is None:
            parser.error(f"--{option.replace('_', '-')} is required")
    if args.flash and args.flasher is None:
        parser.error("--flash requires --flasher")
    try:
        targets = load(args.targets)
        rigs = load(args.rig)
        if not isinstance(targets, dict) or not targets or not isinstance(rigs, dict):
            raise ValueError("Targets must be a nonempty object and rig inventory must be an object")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    reports = []
    for name in args.target or list(targets):
        if name not in targets or name not in rigs:
            reports.append({"target": name, "status": "incomplete", "error": "Missing target or rig binding"})
        else:
            reports.append(run_target(name, targets[name], rigs[name], args.targets.parent / "features", args))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps([{k: r[k] for k in ("target", "status", "error") if k in r} for r in reports], indent=2))
    return 1 if any(r["status"] == "fail" for r in reports) else 2 if any(r["status"] != "pass" for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())

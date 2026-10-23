#!/usr/bin/env python3
"""Run checks against a disposable snapshot of the Ulva worktree.

Results stay in build/runs/. Only board-docs --update-docs copies
the four rendered images and two viewer assets back to the source repository.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "kicad/kicad:9.0.9"
ASSETS = (
    "docs/images/pcb-fabricated-top.png", "docs/images/pcb-fabricated-bottom.png",
    "docs/images/pcb-routing.png", "docs/images/pcb-placement.png",
    "docs/routing/index.html", "docs/routing/board.svg",
)


def safe_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or PurePosixPath(name).is_absolute() or any(
        part in {".", "..", ".git"} for part in parts
    ):
        raise ValueError(f"Unsafe path: {name}")
    path = root
    for part in parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"Symlinks are not supported: {path}")
    return path


def git(source, *args):
    return subprocess.check_output(["git", "--no-optional-locks", "-C", str(source), *args])


def read_worktree(source):
    """Include current edits and nonignored new files; exclude deleted files."""
    names = sorted(set(git(source, "ls-files", "--cached", "--others",
                           "--exclude-standard", "-z").split(b"\0")) - {b""})
    files = {}
    for raw in names:
        name = os.fsdecode(raw)
        path = safe_path(source, name)
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError(f"Expected a regular source file: {path}")
        files[name] = (path.read_bytes(), 0o755 if path.stat().st_mode & 0o111 else 0o644)
    return files


def hashes(files):
    return {name: hashlib.sha256(content).hexdigest()
            for name, (content, _) in sorted(files.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("buttons", "schematic", "pcb", "board-docs"))
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--update-docs", action="store_true",
                        help="Copy only six generated board-docs assets to the source")
    args = parser.parse_args()
    if args.update_docs and args.command != "board-docs":
        parser.error("--update-docs is only available with board-docs")
    source = args.source.expanduser().resolve()
    if Path(os.fsdecode(git(source, "rev-parse", "--show-toplevel")).strip()).resolve() != source:
        parser.error("--source must be the root of the Git checkout")
    files = read_worktree(source)
    required = {"ulva_controller.kicad_pcb", "ulva_controller.kicad_pro",
                "ulva_controller.kicad_sch", "docs/hardware.md"}
    if not required <= files.keys():
        parser.error("--source is missing the editable Ulva project or hardware reference")
    baseline = hashes(files)
    head = git(source, "rev-parse", "HEAD").decode().strip()
    status = os.fsdecode(git(source, "status", "--porcelain=v1"))

    if hashes(read_worktree(source)) != baseline:
        raise ValueError("Source files changed while the snapshot was being read; retry")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    work = ROOT / "build/runs" / f"{stamp}-{args.command}"
    work.mkdir(parents=True)
    for name, (content, mode) in files.items():
        destination = safe_path(work, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        destination.chmod(mode)
    # Renderers are host Python packages; KiCad containers only mount the snapshot.
    cache = ROOT / "build/preview-python"
    if args.command in {"pcb", "board-docs"} and cache.is_dir():
        shutil.copytree(cache, work / "build/preview-python")

    native_kicad = bool(shutil.which("kicad-cli") and importlib.util.find_spec("pcbnew"))
    receipt = {
        "command": args.command, "source": str(source), "source_head": head,
        "source_status": status, "source_files_sha256": baseline,
        "kicad_runtime": "native" if native_kicad else "docker",
        "docker_image": None if native_kicad else IMAGE,
        "started_at_utc": stamp, "result": "running", "commands": [],
        "public_assets_updated": [],
    }
    receipt_path = work / "receipt.json"

    def save_receipt():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    save_receipt()
    print(f"Snapshot and reports: {work}", flush=True)
    kicad_python = ([sys.executable] if native_kicad else
                    ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
                     "-v", f"{work}:/work", "-w", "/work", IMAGE, "python3"])
    if args.command == "buttons":
        commands = [
            ["cmake", "-S", "firmware/buttons_adc/tests", "-B", "build/buttons-tests"],
            ["cmake", "--build", "build/buttons-tests"],
            ["ctest", "--test-dir", "build/buttons-tests", "--output-on-failure"],
        ]
    elif args.command == "board-docs":
        commands = [[sys.executable, "scripts/export_board_docs.py"]]
    else:
        commands = [
            kicad_python + [f"scripts/export_{args.command}.py"],
            kicad_python + ["scripts/validate_button_adc.py"],
            kicad_python + ["scripts/validate_voltage_monitor.py", "build/controller.xml",
                      "--spice", "--report", "build/voltage-monitor-spice.json"],
        ]
        if args.command == "pcb":
            commands.append([sys.executable, "scripts/verify_gerbers.py"])
    try:
        with (work / "checks.log").open("w") as log:
            for command in commands:
                receipt["commands"].append(command)
                save_receipt()
                print("Run: " + " ".join(command), flush=True)
                log.write("\n$ " + " ".join(command) + "\n")
                log.flush()
                subprocess.run(command, cwd=work, check=True, stdout=log,
                               stderr=subprocess.STDOUT)
        current = hashes(read_worktree(source))
        receipt["source_unchanged_during_checks"] = current == baseline
        if args.update_docs:
            if current != baseline:
                raise ValueError("Source changed during checks; board docs were not updated")
            assets = {name: safe_path(work, name).read_bytes() for name in ASSETS}
            for name in ASSETS:
                destination = safe_path(source, name)
                if destination.exists() and not destination.is_file():
                    raise ValueError(f"Documentation destination is not a file: {destination}")
            # This fixed asset list is the only path from a run back to the source tree.
            for name, content in assets.items():
                destination = safe_path(source, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temp:
                    temporary = Path(temp.name)
                    temp.write(content)
                try:
                    temporary.chmod(0o644)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
                receipt["public_assets_updated"].append(name)
            receipt["public_assets_sha256"] = {
                name: hashlib.sha256(content).hexdigest() for name, content in assets.items()
            }
        receipt["result"] = "passed"
    except Exception as error:
        receipt["result"] = "failed"
        receipt["error"] = str(error)
        raise
    finally:
        receipt["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_receipt()
    print(f"Passed. Receipt: {receipt_path}; log: {work / 'checks.log'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Checks failed: {error}") from error

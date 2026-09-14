#!/usr/bin/env python3
"""Retain CI smoke logs and replayable MLA simulator inputs (stdlib only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import select
import signal
import subprocess
import sys
import tempfile
import time


SIMULATORS = ("mla-msim", "mla-asim", "mla-dsim", "mla-isim")
GDB_TIMEOUT = 120


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def collect_host(output: Path) -> None:
    # Deliberately avoid dumping the environment or package-index credentials.
    write_json(output / "environment.json", {
        name: os.environ.get(name) for name in (
            "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "RUNNER_ARCH",
            "VIRTUAL_ENV", "XLA_FLAGS", "SIMA_MLA_COMPILE_USE_JAX",
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        )
    })
    for name, command in (
        ("host", ["uname", "-a"]),
        ("cpu", ["lscpu"]),
        ("memory", ["free", "-h"]),
        ("disk", ["df", "-h"]),
        ("packages", [sys.executable, "-m", "pip", "list", "--format=json"]),
    ):
        with (output / f"{name}.log").open("w") as log:
            try:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                               timeout=30, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                log.write(f"Diagnostic unavailable: {error}\n")


def run_smoke(output: Path, command: list[str]) -> int:
    output.mkdir(parents=True, exist_ok=True)
    collect_host(output)
    shims = output / "bin"
    shims.mkdir(exist_ok=True)
    executables = {}
    for name in SIMULATORS:
        executable = shutil.which(name)
        if executable is None:
            continue  # The smoke preflight remains responsible for missing tools.
        executables[name] = {"path": executable, "sha256": sha256(Path(executable))}
        shim = shims / name
        invocation = [sys.executable, str(Path(__file__).resolve()), "simulator",
                      "--output", str(output / "simulators"),
                      "--executable", executable, "--"]
        shim.write_text("#!/bin/sh\nexec " + shlex.join(invocation) + ' "$@"\n')
        shim.chmod(0o755)
    write_json(output / "simulators.json", executables)
    env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ.get("PATH", ""))
    record = {"command": command, "cwd": os.getcwd(), "status": "running"}
    write_json(output / "smoke.json", record)
    # Tee incrementally so CI progress stays visible and partial logs survive cancellation.
    with (output / "smoke.log").open("wb") as log:
        proc = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with proc.stdout:
            while chunk := proc.stdout.read1(65536):
                log.write(chunk)
                log.flush()
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        returncode = proc.wait()
    record.update(status="finished", returncode=returncode)
    write_json(output / "smoke.json", record)
    return returncode


def save_inputs(directory: Path, arguments: list[str]) -> list[str]:
    inputs = directory / "inputs"
    inputs.mkdir()
    replay = []
    manifest = []
    for index, argument in enumerate(arguments):
        prefix, separator, value = argument.partition("=")
        candidate = value if separator and prefix in ("--data", "--check") else argument
        source = Path(candidate)
        # Only simulator input files; never recursively collect unrelated files.
        if not candidate.startswith("-") and source.is_file():
            saved = inputs / f"{index}-{source.name}"
            shutil.copyfile(source, saved)
            replacement = str(saved.relative_to(directory))
            replay.append(prefix + "=" + replacement if candidate != argument else replacement)
            manifest.append({"original": str(source.resolve()), "saved": replacement,
                             "sha256": sha256(saved)})
        else:
            replay.append(argument)
    write_json(directory / "inputs.json", manifest)
    return replay


def supervise_simulator(parent_fd: int, command: list[str]) -> int:
    # Only the wrapper owns the pipe's write end. EOF detects even SIGKILL,
    # which cannot be handled by signal forwarding in the wrapper itself.
    proc = subprocess.Popen(command, start_new_session=True)
    try:
        while proc.poll() is None:
            readable, _, _ = select.select([parent_fd], [], [], 0.1)
            if readable and not os.read(parent_fd, 1):
                return -signal.SIGTERM
        return proc.returncode
    finally:
        # The supervisor survives wrapper death and reaps its direct child.
        # Kill the process group as well so simulator workers cannot linger.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        os.close(parent_fd)


def run_supervised_simulator(command: list[str], stdout, stderr) -> int:
    read_fd, write_fd = os.pipe()
    try:
        supervisor = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "supervise",
             "--parent-fd", str(read_fd), "--", *command],
            pass_fds=(read_fd,), stdout=stdout, stderr=stderr,
            start_new_session=True,
        )
        os.close(read_fd)
        read_fd = None
        try:
            return supervisor.wait()
        finally:
            os.close(write_fd)
            write_fd = None
            supervisor.wait()
    finally:
        for descriptor in (read_fd, write_fd):
            if descriptor is not None:
                os.close(descriptor)


def run_simulator(output: Path, executable: str, arguments: list[str]) -> int:
    output.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=Path(executable).name + "-", dir=output))
    record = {"command": [executable, *arguments], "cwd": os.getcwd(),
              "started_at": time.time(), "status": "running"}
    write_json(directory / "command.json", record)
    replay = None
    try:
        replay = save_inputs(directory, arguments)
        script = '#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\n'
        script += "simulator=" + shlex.quote(executable) + "\n"
        script += 'exec "${MODELSDK_SIMULATOR:-$simulator}" ' + shlex.join(replay) + "\n"
        (directory / "replay.sh").write_text(script)
        (directory / "replay.sh").chmod(0o755)
    except OSError as error:
        # A diagnostic copy failure must not prevent the actual test from running.
        (directory / "capture-error.log").write_text(str(error) + "\n")
    with (directory / "stdout.log").open("wb") as stdout, \
            (directory / "stderr.log").open("wb") as stderr:
        returncode = run_supervised_simulator([executable, *arguments], stdout, stderr)
    record.update(status="finished", returncode=returncode, finished_at=time.time())
    write_json(directory / "command.json", record)
    # Forward each stream and preserve the original simulator result.
    for name, destination in (("stdout.log", sys.stdout.buffer), ("stderr.log", sys.stderr.buffer)):
        with (directory / name).open("rb") as source:
            shutil.copyfileobj(source, destination)
        destination.flush()
    if returncode != 0 and replay is not None:
        with (directory / "gdb.log").open("w") as log:
            command = ["gdb", "--batch", "-ex", "set pagination off",
                       "-ex", "set confirm off", "-ex", "run",
                       "-ex", "thread apply all bt", "-ex", "info registers",
                       "-ex", "x/12i $pc-16", "-ex", "info sharedlibrary",
                       "--args", executable, *replay]
            try:
                debugger = subprocess.Popen(command, cwd=directory, stdout=log,
                                            stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    debugger.wait(timeout=GDB_TIMEOUT)
                except subprocess.TimeoutExpired:
                    # Kill the inferior too; an abandoned replay must not keep CI busy.
                    os.killpg(debugger.pid, signal.SIGKILL)
                    debugger.wait()
                    raise
            except (OSError, subprocess.TimeoutExpired) as error:
                log.write(f"GDB replay unavailable or timed out: {error}\n")
    return returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "simulator", "supervise"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--parent-fd", type=int)
    parser.add_argument("--executable")
    options, command = parser.parse_known_args()
    if not command or command[0] != "--":
        parser.error("pass the command or simulator arguments after --")
    command = command[1:]
    if options.mode != "supervise" and options.output is None:
        parser.error("--output is required")
    if options.mode == "supervise":
        if options.parent_fd is None or not command:
            parser.error("supervise requires --parent-fd and a command")
        returncode = supervise_simulator(options.parent_fd, command)
    elif options.mode == "run":
        if not command:
            parser.error("a smoke command is required")
        returncode = run_smoke(options.output.resolve(), command)
    else:
        if not options.executable:
            parser.error("--executable is required in simulator mode")
        returncode = run_simulator(options.output.resolve(), options.executable, command)
    if returncode < 0:
        # AFE distinguishes SIGSEGV (-11) from an ordinary nonzero exit status.
        number = -returncode
        if number not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(number, signal.SIG_DFL)
        os.kill(os.getpid(), number)
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()

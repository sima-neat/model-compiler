import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/smoke_evidence.py"
SPEC = importlib.util.spec_from_file_location("smoke_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SmokeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.simulator = self.bin / "mla-msim"
        self.simulator.write_text(f"#!{sys.executable}\n" + '''
import os, resource, signal, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
print("simulator stdout", flush=True)
print("simulator stderr", file=sys.stderr, flush=True)
code = int(os.environ.get("FAKE_SIMULATOR_EXIT", "0"))
if code < 0:
    os.kill(os.getpid(), -code)
sys.exit(code)
''')
        self.simulator.chmod(0o755)
        debugger = self.bin / "gdb"
        debugger.write_text(f"#!{sys.executable}\n" + '''
from pathlib import Path
import sys
args = sys.argv[sys.argv.index("--args") + 2:]
for arg in args:
    path = arg.split("=", 1)[-1]
    if path.endswith((".elf", ".mlc")):
        assert Path(path).is_file(), path
print("GDB replay with preserved inputs")
''')
        debugger.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ["PATH"])

    def invoke(self, code=0):
        inputs = self.root / "original inputs"
        inputs.mkdir()
        elf = inputs / "model file.elf"
        data = inputs / "input.mlc"
        elf.write_bytes(b"ELF payload")
        data.write_bytes(b"data payload")
        output = self.root / "evidence"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "simulator", "--output", str(output),
             "--executable", str(self.simulator), "--", str(elf),
             "--data=" + str(data), "--check=" + str(data)],
            env=dict(self.env, FAKE_SIMULATOR_EXIT=str(code)), capture_output=True,
        )
        return result, next(output.iterdir()), inputs

    def test_success_preserves_both_streams_and_replay_survives_input_cleanup(self):
        result, directory, inputs = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"simulator stdout\n")
        self.assertEqual(result.stderr, b"simulator stderr\n")
        for path in inputs.iterdir():
            path.unlink()
        inputs.rmdir()
        replay = subprocess.run(["sh", str(directory / "replay.sh")],
                                env=self.env, capture_output=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        manifest = json.loads((directory / "inputs.json").read_text())
        self.assertEqual(len(manifest), 3)
        self.assertEqual((directory / manifest[0]["saved"]).read_bytes(), b"ELF payload")
        self.assertEqual((directory / "stdout.log").read_bytes(), result.stdout)
        self.assertEqual((directory / "stderr.log").read_bytes(), result.stderr)
        self.assertFalse((directory / "gdb.log").exists())

    def test_segmentation_fault_keeps_signal_and_runs_debugger(self):
        result, directory, _ = self.invoke(-signal.SIGSEGV)
        self.assertEqual(result.returncode, -signal.SIGSEGV)
        command = json.loads((directory / "command.json").read_text())
        self.assertEqual(command["returncode"], -signal.SIGSEGV)
        self.assertIn("GDB replay with preserved inputs", (directory / "gdb.log").read_text())

    def test_sigkill_is_not_changed_into_an_ordinary_error(self):
        result, directory, _ = self.invoke(-signal.SIGKILL)
        self.assertEqual(result.returncode, -signal.SIGKILL)
        self.assertEqual(json.loads((directory / "command.json").read_text())["returncode"],
                         -signal.SIGKILL)

    def test_nonzero_exit_is_not_hidden_by_successful_debugger(self):
        result, directory, _ = self.invoke(7)
        self.assertEqual(result.returncode, 7)
        self.assertIn("GDB replay with preserved inputs", (directory / "gdb.log").read_text())

    def test_missing_debugger_does_not_mask_failure(self):
        (self.bin / "gdb").unlink()
        self.env["PATH"] = str(self.bin)
        result, directory, _ = self.invoke(7)
        self.assertEqual(result.returncode, 7)
        self.assertIn("GDB replay unavailable", (directory / "gdb.log").read_text())

    def test_debugger_timeout_is_bounded_and_does_not_mask_failure(self):
        (self.bin / "gdb").write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
        output = self.root / "timeout"
        start = time.monotonic()
        with mock.patch.object(MODULE, "GDB_TIMEOUT", 0.1), mock.patch.dict(
            os.environ, dict(self.env, FAKE_SIMULATOR_EXIT="7")
        ):
            code = MODULE.run_simulator(output, str(self.simulator), [])
        self.assertEqual(code, 7)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn("timed out", next(output.glob("*/gdb.log")).read_text())

    def test_input_copy_failure_still_runs_simulator(self):
        output = self.root / "copy-error"
        with mock.patch.object(MODULE, "save_inputs", side_effect=OSError("disk full")), \
                mock.patch.dict(os.environ, dict(self.env, FAKE_SIMULATOR_EXIT="7")):
            code = MODULE.run_simulator(output, str(self.simulator), [])
        self.assertEqual(code, 7)
        directory = next(output.iterdir())
        self.assertIn("disk full", (directory / "capture-error.log").read_text())
        self.assertIn("simulator stdout", (directory / "stdout.log").read_text())

    def test_smoke_wrapper_propagates_failure_and_captures_nested_simulator(self):
        output = self.root / "smoke"
        with mock.patch.object(MODULE, "collect_host"), mock.patch.dict(os.environ, self.env):
            code = MODULE.run_smoke(output, [sys.executable, "-c",
                'import subprocess, sys; subprocess.run(["mla-msim", "--help"], check=True); sys.exit(9)'])
        self.assertEqual(code, 9)
        self.assertEqual(json.loads((output / "smoke.json").read_text())["returncode"], 9)
        self.assertEqual(len(list((output / "simulators").glob("mla-msim-*"))), 1)
        self.assertIn("simulator stdout", (output / "smoke.log").read_text())
        self.assertIn("sha256", json.loads((output / "simulators.json").read_text())["mla-msim"])

    def test_workflow_retains_evidence_even_when_smoke_fails(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        self.assertIn("scripts/smoke_evidence.py\n", workflow)
        self.assertIn('python scripts/smoke_evidence.py run --output', workflow)
        self.assertIn("name: Upload smoke evidence\n        if: ${{ always() }}", workflow)
        self.assertIn("name: Upload failed smoke work directory\n        if: ${{ failure() }}", workflow)
        self.assertIn("model-compiler-smoke-evidence-${{ matrix.arch }}-${{ github.run_attempt }}", workflow)
        self.assertIn("- test-package-install", workflow)
        self.assertNotIn("continue-on-error:", workflow.split("  test-package-install:")[1].split("  publish-amd64:")[0])


if __name__ == "__main__":
    unittest.main()

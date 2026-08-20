import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_modelsdk_wheels.sh"
SOURCE_JSON = ROOT / "scripts" / "source.json"


def generated_activation_block(model_compiler_dir: Path) -> str:
    script = INSTALLER.read_text(encoding="utf-8")
    start_marker = (
        '  write_managed_shell_block "$target_file" '
        '"$functions_marker_begin" "$functions_marker_end" <<EOF\n'
    )
    start = script.index(start_marker) + len(start_marker)
    end = script.index("\nEOF\n", start)
    block = script[start:end]

    # Reproduce the substitutions performed by the unquoted installer heredoc.
    block = block.replace("$functions_marker_begin", "# >>> model-compiler activation >>>")
    block = block.replace("$functions_marker_end", "# <<< model-compiler activation <<<")
    block = block.replace("$model_compiler_dir", str(model_compiler_dir))
    block = block.replace("$bin_dir", str(model_compiler_dir / "bin"))
    return block.replace("\\$", "$")


class ModelCompilerActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.model_compiler_dir = self.root / "model-compiler"
        self.bin_dir = self.model_compiler_dir / "bin"
        self.bin_dir.mkdir(parents=True)
        (self.model_compiler_dir / "lib" / "python3.12" / "site-packages" / "tvm").mkdir(
            parents=True
        )
        (self.bin_dir / "activate").write_text(
            'VIRTUAL_ENV="${VIRTUAL_ENV:-unused}"\n'
            f'VIRTUAL_ENV="{self.model_compiler_dir}"\n'
            "export VIRTUAL_ENV\n",
            encoding="utf-8",
        )
        self.functions_file = self.root / "activation-functions.sh"
        self.functions_file.write_text(
            generated_activation_block(self.model_compiler_dir),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_shell(self, arch: str, commands: str) -> subprocess.CompletedProcess:
        fake_bin = self.root / f"fake-{arch}"
        fake_bin.mkdir(exist_ok=True)
        uname = fake_bin / "uname"
        uname.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "{arch}"\n', encoding="utf-8")
        uname.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:{env['PATH']}"
        return subprocess.run(
            ["bash", "-c", f'source "{self.functions_file}"; {commands}'],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_arm64_activation_sets_and_deactivation_unsets_environment(self):
        for arch in ("aarch64", "arm64"):
            with self.subTest(arch=arch):
                result = self.run_shell(
                    arch,
                    'unset XLA_FLAGS SIMA_MLA_COMPILE_USE_JAX; '
                    "activate-model-compiler; "
                    'printf "active:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"; '
                    "deactivate-model-compiler; "
                    'printf "set:%s:%s\\n" "${XLA_FLAGS+x}" '
                    '"${SIMA_MLA_COMPILE_USE_JAX+x}"',
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("active:--xla_cpu_max_isa=NEON:1", result.stdout)
                self.assertIn("set::", result.stdout)

    def test_arm64_preserves_unrelated_xla_flags_and_restores_environment(self):
        result = self.run_shell(
            "aarch64",
            'export XLA_FLAGS="--xla_force_host_platform_device_count=4 '
            '--xla_cpu_max_isa=AVX2 --xla_dump_to=/tmp/xla"; '
            'export SIMA_MLA_COMPILE_USE_JAX="user-value"; '
            "activate-model-compiler; "
            "activate-model-compiler; "
            'printf "active:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"; '
            "deactivate-model-compiler; "
            'printf "restored:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "active:--xla_force_host_platform_device_count=4 "
            "--xla_dump_to=/tmp/xla --xla_cpu_max_isa=NEON:1",
            result.stdout,
        )
        self.assertIn(
            "restored:--xla_force_host_platform_device_count=4 "
            "--xla_cpu_max_isa=AVX2 --xla_dump_to=/tmp/xla:user-value",
            result.stdout,
        )

    def test_arm64_no_jax_removes_neon_and_preserves_unrelated_flags(self):
        result = self.run_shell(
            "aarch64",
            'export XLA_FLAGS="--xla_dump_to=/tmp/xla --xla_cpu_max_isa=NEON"; '
            'export SIMA_MLA_COMPILE_USE_JAX="user-value"; '
            "activate-model-compiler --no-jax; "
            "activate-model-compiler --no-jax; "
            'printf "active:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"; '
            "deactivate-model-compiler; "
            'printf "restored:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Model Compiler activated with JAX disabled.", result.stdout)
        self.assertIn("active:--xla_dump_to=/tmp/xla:0", result.stdout)
        self.assertIn(
            "restored:--xla_dump_to=/tmp/xla "
            "--xla_cpu_max_isa=NEON:user-value",
            result.stdout,
        )

    def test_arm64_can_switch_from_default_activation_to_no_jax(self):
        result = self.run_shell(
            "arm64",
            'unset XLA_FLAGS SIMA_MLA_COMPILE_USE_JAX; '
            "activate-model-compiler; "
            "activate-model-compiler --no-jax; "
            'printf "active:%s:%s:%s\\n" "${XLA_FLAGS+x}" '
            '"$SIMA_MLA_COMPILE_USE_JAX" '
            '"${XLA_FLAGS:-}"; '
            "deactivate-model-compiler; "
            'printf "set:%s:%s\\n" "${XLA_FLAGS+x}" '
            '"${SIMA_MLA_COMPILE_USE_JAX+x}"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("active::0:", result.stdout)
        self.assertIn("set::", result.stdout)

    def test_amd64_activation_does_not_change_environment(self):
        result = self.run_shell(
            "x86_64",
            'export XLA_FLAGS="--x86-flag"; '
            'export SIMA_MLA_COMPILE_USE_JAX="x86-value"; '
            "activate-model-compiler; "
            'printf "%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--x86-flag:x86-value", result.stdout)

    def test_amd64_no_jax_disables_jax_and_restores_environment(self):
        result = self.run_shell(
            "x86_64",
            'export XLA_FLAGS="--x86-flag --xla_cpu_max_isa=NEON"; '
            'export SIMA_MLA_COMPILE_USE_JAX="x86-value"; '
            "activate-model-compiler --no-jax; "
            'printf "active:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"; '
            "deactivate-model-compiler; "
            'printf "restored:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("active:--x86-flag:0", result.stdout)
        self.assertIn(
            "restored:--x86-flag --xla_cpu_max_isa=NEON:x86-value",
            result.stdout,
        )

    def test_amd64_default_reactivation_restores_environment_after_no_jax(self):
        result = self.run_shell(
            "x86_64",
            'export XLA_FLAGS="--x86-flag --xla_cpu_max_isa=NEON"; '
            'export SIMA_MLA_COMPILE_USE_JAX="x86-value"; '
            "activate-model-compiler --no-jax; "
            "activate-model-compiler; "
            'printf "restored:%s:%s\\n" "$XLA_FLAGS" "$SIMA_MLA_COMPILE_USE_JAX"; '
            'printf "managed:%s\\n" "${_MODEL_COMPILER_COMPILE_ENV_ACTIVE+x}"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "restored:--x86-flag --xla_cpu_max_isa=NEON:x86-value",
            result.stdout,
        )
        self.assertIn("managed:", result.stdout)

    def test_amd64_default_reactivation_unsets_environment_after_no_jax(self):
        result = self.run_shell(
            "x86_64",
            "unset XLA_FLAGS SIMA_MLA_COMPILE_USE_JAX; "
            "activate-model-compiler --no-jax; "
            "activate-model-compiler; "
            'printf "set:%s:%s\\n" "${XLA_FLAGS+x}" '
            '"${SIMA_MLA_COMPILE_USE_JAX+x}"',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("set::", result.stdout)

    def test_unknown_activation_option_fails_without_activating(self):
        result = self.run_shell(
            "aarch64",
            'unset VIRTUAL_ENV; activate-model-compiler --unknown; '
            'status=$?; printf "status:%s:venv:%s\\n" "$status" "${VIRTUAL_ENV+x}"; '
            'exit "$status"',
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown option: --unknown", result.stderr)
        self.assertIn("Usage: activate-model-compiler [--no-jax]", result.stderr)
        self.assertIn("status:2:venv:", result.stdout)

    def test_jax_dependency_versions_are_pinned_only_for_arm64(self):
        source = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
        global_overrides = source["dependency_overrides"]
        arm64_overrides = source["aarch64"]["dependency_overrides"]
        amd64_overrides = source["x86_64"]["dependency_overrides"]

        self.assertNotIn("jax", global_overrides)
        self.assertNotIn("jaxlib", global_overrides)
        self.assertNotIn("ml-dtypes", global_overrides)
        self.assertEqual(arm64_overrides["jax"], "0.5.3")
        self.assertEqual(arm64_overrides["jaxlib"], "0.5.3")
        self.assertEqual(arm64_overrides["ml-dtypes"], "0.4.1")
        self.assertEqual(
            set(arm64_overrides),
            {"jax", "jaxlib", "ml-dtypes"},
        )
        self.assertEqual(amd64_overrides, {"ml-dtypes": "0.4.1"})


if __name__ == "__main__":
    unittest.main()

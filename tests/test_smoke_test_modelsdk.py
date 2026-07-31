import importlib.util
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_test_modelsdk.py"
SPEC = importlib.util.spec_from_file_location("smoke_test_modelsdk", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SmokeTestModelsdkTests(unittest.TestCase):
    def test_llima_qwen3_disables_unsupported_onnx_quantization(self):
        command = MODULE.llima_qwen3_compile_command(
            Path("/tmp/compile_config.py"),
            Path("/tmp/output"),
            Path("/tmp/Qwen3-0.6B"),
        )

        self.assertIn("--no-quantize_embeddings", command)
        self.assertIn("--no-quantize_kv_cache", command)
        self.assertLess(
            command.index("/tmp/Qwen3-0.6B"),
            command.index("--no-quantize_embeddings"),
        )

    def test_python_environment_checks_pip_and_pinned_versions(self):
        with (
            mock.patch.dict(MODULE.os.environ, {"MODELSDK_SMOKE_ARCH": "arm64"}),
            mock.patch.object(MODULE, "run") as run,
            mock.patch.object(
                MODULE.importlib.metadata,
                "version",
                side_effect=lambda name: MODULE.ARM64_REQUIRED_PACKAGE_VERSIONS[name],
            ),
        ):
            MODULE.smoke_python_environment()

        run.assert_called_once_with(
            [MODULE.sys.executable, "-m", "pip", "check"], timeout=120
        )

    def test_python_environment_rejects_wrong_pinned_version(self):
        with (
            mock.patch.dict(MODULE.os.environ, {"MODELSDK_SMOKE_ARCH": "arm64"}),
            mock.patch.object(MODULE, "run"),
            mock.patch.object(
                MODULE.importlib.metadata,
                "version",
                side_effect=lambda name: "0.0.0"
                if name == "jax"
                else MODULE.ARM64_REQUIRED_PACKAGE_VERSIONS[name],
            ),
        ):
            with self.assertRaisesRegex(MODULE.SmokeFailure, "jax: 0.0.0"):
                MODULE.smoke_python_environment()

    def test_amd64_python_environment_does_not_enforce_arm64_pins(self):
        with (
            mock.patch.dict(MODULE.os.environ, {"MODELSDK_SMOKE_ARCH": "amd64"}),
            mock.patch.object(MODULE, "run") as run,
            mock.patch.object(MODULE.importlib.metadata, "version") as version,
        ):
            MODULE.smoke_python_environment()

        run.assert_called_once_with(
            [MODULE.sys.executable, "-m", "pip", "check"], timeout=120
        )
        version.assert_not_called()

    def test_compiled_artifacts_require_sima_mpk_elf_and_precision_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            build_dir = Path(directory)
            with zipfile.ZipFile(build_dir / "resnet.sima", "w") as archive:
                archive.writestr("manifest.json", "{}")

            elf = build_dir / "model.elf"
            elf.write_bytes(b"ELF")
            with tarfile.open(build_dir / "resnet_mpk.tar.gz", "w:gz") as archive:
                archive.add(elf, arcname="model.elf")
            elf.unlink()

            (build_dir / "quantization_manifest.json").write_text(
                json.dumps(
                    {
                        "activation_precision": "bfloat16",
                        "weight_precision": "bfloat16",
                        "device": "modalix",
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(MODULE, "run"):
                metrics = MODULE.validate_and_measure_compiled_artifacts(
                    "resnet50-bfloat16", build_dir, "bfloat16"
                )

            self.assertEqual(metrics["sima_packages"], "1")
            self.assertEqual(metrics["mpk_archives"], "1")
            self.assertEqual(metrics["mla_elfs"], "1")

    def test_compiled_artifacts_reject_precision_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            build_dir = Path(directory)
            (build_dir / "quantization_manifest.json").write_text(
                json.dumps(
                    {
                        "activation_precision": "int8",
                        "weight_precision": "int8",
                        "device": "modalix",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.SmokeFailure, "does not match requested bfloat16"
            ):
                MODULE.validate_quantization_manifest(build_dir, "bfloat16")


if __name__ == "__main__":
    unittest.main()

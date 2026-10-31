import importlib.util
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_test_modelsdk.py"
SPEC = importlib.util.spec_from_file_location("smoke_test_modelsdk", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SmokeTestModelsdkTests(unittest.TestCase):
    def test_quantize_compile_command_uses_current_reference_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.onnx"
            model_path.write_bytes(b"onnx")

            with mock.patch.object(MODULE, "run") as run:
                MODULE.run_quantize_compile(
                    model_path,
                    root / "build",
                    input_shape="1,3,224,224",
                    compile_model=True,
                    dtype="int8",
                )

        command = run.call_args.args[0]
        self.assertNotIn("--input_names", command)
        self.assertNotIn("--output_names", command)
        self.assertNotIn("--device", command)
        self.assertIn("--build_dir", command)

    def test_yolo_smoke_validates_compiled_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            work_dir = Path(directory)
            model_path = work_dir / "yolov8n.onnx"
            model_path.write_bytes(b"onnx")
            args = SimpleNamespace(
                work_dir=str(work_dir),
                yolo_model=str(model_path),
                yolo_url="https://example.invalid/yolov8n.onnx",
                dtype="int8",
                strict_audit=False,
                model_to_pipeline_dir=None,
            )
            metrics = {"sima_packages": "1", "mpk_archives": "1"}

            with (
                mock.patch.object(MODULE, "run"),
                mock.patch.object(MODULE, "audit_onnx_model"),
                mock.patch.object(MODULE, "run_quantize_compile"),
                mock.patch.object(
                    MODULE,
                    "validate_and_measure_compiled_artifacts",
                    return_value=metrics,
                ) as validate,
            ):
                payload = MODULE.smoke_yolo(args)

            validate.assert_called_once_with("yolov8", payload.artifacts, "int8")
            self.assertEqual(payload.metrics, metrics)

    def test_llima_qwen3_uses_native_stages(self):
        command = MODULE.llima_qwen3_compile_command(
            Path("/tmp/compile_config.py"),
            Path("/tmp/output"),
            Path("/tmp/Qwen3-0.6B"),
        )

        self.assertNotIn("--onnx", command)
        self.assertNotIn("--quantize", command)
        self.assertNotIn("--no-quantize_embeddings", command)
        self.assertNotIn("--no-quantize_kv_cache", command)

        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(work_dir=directory)
            metrics = {
                "fp_sima_files": "1",
                "quantized_sima_files": "1",
                "mpk_archives": "1",
                "mla_elfs": "1",
            }
            huggingface_hub = SimpleNamespace(
                snapshot_download=mock.Mock(
                    return_value=str(Path(directory) / "Qwen3-0.6B")
                )
            )
            with (
                mock.patch.dict(sys.modules, {"huggingface_hub": huggingface_hub}),
                mock.patch.object(MODULE, "run") as run,
                mock.patch.object(
                    MODULE, "validate_llima_artifacts", return_value=metrics
                ) as validate,
            ):
                payload = MODULE.smoke_llima_qwen3(args)

        self.assertEqual(
            [call.args[0][-1] for call in run.call_args_list],
            ["--source_to_fp", "--fp_to_quant", "--compile"],
        )
        self.assertTrue(all(call.kwargs == {"timeout": 3600} for call in run.call_args_list))
        validate.assert_called_once_with(payload.artifacts)
        self.assertEqual(payload.metrics, metrics)

    def test_llima_artifacts_require_native_stage_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            sdk_dir = output_dir / "sima_files" / "sdk"
            mpk_dir = output_dir / "sima_files" / "mpk"
            sdk_dir.mkdir(parents=True)
            mpk_dir.mkdir(parents=True)
            fp_model = sdk_dir / "part.fp32.sima"
            quantized_model = sdk_dir / "part.sima"
            fp_model.write_bytes(b"fp")
            quantized_model.write_bytes(b"quantized")
            elf = output_dir / "part.elf"
            elf.write_bytes(b"ELF")
            with tarfile.open(mpk_dir / "part_mpk.tar.gz", "w:gz") as archive:
                archive.add(elf, arcname="part.elf")

            metrics = MODULE.validate_llima_artifacts(output_dir)
            self.assertEqual(metrics["fp_sima_files"], "1")
            self.assertEqual(metrics["quantized_sima_files"], "1")
            self.assertEqual(metrics["mpk_archives"], "1")
            self.assertEqual(metrics["mla_elfs"], "1")

            fp_model.unlink()
            with self.assertRaisesRegex(MODULE.SmokeFailure, "no floating-point"):
                MODULE.validate_llima_artifacts(output_dir)

    def test_llima_artifacts_require_regular_nonempty_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            sdk_dir = output_dir / "sima_files" / "sdk"
            mpk_dir = output_dir / "sima_files" / "mpk"
            sdk_dir.mkdir(parents=True)
            mpk_dir.mkdir(parents=True)
            (sdk_dir / "part.fp32.sima").write_bytes(b"fp")
            (sdk_dir / "part.sima").write_bytes(b"quantized")
            with tarfile.open(mpk_dir / "part_mpk.tar.gz", "w:gz") as archive:
                empty = tarfile.TarInfo("part.elf")
                empty.size = 0
                archive.addfile(empty)

            with self.assertRaisesRegex(MODULE.SmokeFailure, "contains no MLA ELF"):
                MODULE.validate_llima_artifacts(output_dir)

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

    def test_amd64_python_environment_enforces_only_compatible_ml_dtypes(self):
        with (
            mock.patch.dict(MODULE.os.environ, {"MODELSDK_SMOKE_ARCH": "amd64"}),
            mock.patch.object(MODULE, "run") as run,
            mock.patch.object(
                MODULE.importlib.metadata,
                "version",
                side_effect=lambda name: MODULE.X86_64_REQUIRED_PACKAGE_VERSIONS[name],
            ) as version,
        ):
            MODULE.smoke_python_environment()

        run.assert_called_once_with(
            [MODULE.sys.executable, "-m", "pip", "check"], timeout=120
        )
        version.assert_called_once_with("ml-dtypes")

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

#!/usr/bin/env python3
"""Post-install smoke tests for the Model Compiler extension."""

from __future__ import annotations

import argparse
import getpass
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
# Snapshot-backed installations can take longer on first access while EBS loads
# lazily restored blocks. Keep the ordinary smoke-test default short, but let
# snapshot validation extend it without changing the test itself.
DEFAULT_TOOL_TIMEOUT = int(os.environ.get("MODELSDK_SMOKE_TOOL_TIMEOUT_SECONDS", "30"))
DEFAULT_YOLO_URL = "https://huggingface.co/webml/yolov8n/resolve/main/onnx/yolov8n.onnx"
DEFAULT_WORK_ROOT = Path.home() / "tmp"
QWEN3_REPO_ID = "Qwen/Qwen3-0.6B"
QWEN3_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
QWEN3_QUANTIZED_OUTPUT_TOLERANCE = 0.20
QWEN3_COMPILE_CONFIGURATION = """\
def get_layer_configuration(model_properties, layer):
    if layer["is_group"] or layer["index"] != 0:
        return {"compile": False}
    return {"precision": "A_BF16_W_INT4"}
"""

REQUIRED_TOOLS = [
    "mla-nm",
    "mla-size",
    "mla-readelf",
    "mla-dasm",
    "mla-strip",
    "mla-isim",
    "afe-replay-compile",
    "onnxsim",
    "llima-compile",
]

REQUIRED_MODULES = [
    "afe",
    "onnx",
    "onnxruntime",
    "torch",
    "torchvision",
    "sima_lmm",
    "gguf",
    "huggingface_hub",
    "llama_cpp",
    "safetensors",
]

ARM64_REQUIRED_PACKAGE_VERSIONS = {
    "jax": "0.5.3",
    "jaxlib": "0.5.3",
    "ml-dtypes": "0.4.1",
}

VERBOSE = False


class SmokeFailure(RuntimeError):
    pass


@dataclass
class SmokeCaseResult:
    name: str
    status: str
    duration_s: float
    artifacts: Path | None = None
    error: str | None = None
    metrics: dict[str, str] = field(default_factory=dict)


@dataclass
class SmokeCasePayload:
    artifacts: Path | None = None
    metrics: dict[str, str] = field(default_factory=dict)


def log(message: str) -> None:
    print(f"[modelsdk-smoke] {message}", flush=True)


def format_cmd(cmd: list[str]) -> str:
    if "-c" in cmd:
        idx = cmd.index("-c")
        return " ".join(cmd[: idx + 1] + ["<python-code>"] + cmd[idx + 2 :])
    return " ".join(cmd)


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TOOL_TIMEOUT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log("$ " + format_cmd(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if proc.stdout and (VERBOSE or proc.returncode != 0):
        print(proc.stdout.rstrip())
    elif proc.stdout:
        first_line = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        if first_line:
            log(first_line)
    if check and proc.returncode != 0:
        raise SmokeFailure(f"command failed with exit code {proc.returncode}: {format_cmd(cmd)}")
    return proc


def ensure_writable_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".modelsdk-smoke-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise SmokeFailure(
            f"work directory is not writable: {path}. "
            "Choose a fresh --work-dir or remove the stale directory first."
        ) from exc
    return path


def prepare_output_file(path: Path) -> None:
    ensure_writable_dir(path.parent)
    if not path.exists():
        return
    try:
        path.unlink()
    except OSError as exc:
        raise SmokeFailure(
            f"cannot overwrite existing output file: {path}. "
            "Choose a fresh --work-dir or remove the stale file first."
        ) from exc


def make_run_dir(work_dir: Path, tier: str) -> Path:
    ensure_writable_dir(work_dir)
    return Path(tempfile.mkdtemp(prefix=f"{tier}-", dir=str(work_dir)))


def work_dir_from_arg(value: str | None, prefix: str) -> Path:
    if not value:
        ensure_writable_dir(DEFAULT_WORK_ROOT)
        return Path(tempfile.mkdtemp(prefix=prefix, dir=str(DEFAULT_WORK_ROOT)))

    requested = Path(value)
    try:
        return ensure_writable_dir(requested)
    except SmokeFailure:
        fallback = DEFAULT_WORK_ROOT / f"{requested.name}-{getpass.getuser()}"
        log(f"{requested} is not writable; using {fallback}")
        return ensure_writable_dir(fallback)


def require_active_modelsdk() -> None:
    prefix = Path(sys.prefix)
    bin_dir = prefix / "bin"
    if not (bin_dir / "activate").exists():
        raise SmokeFailure(
            f"{sys.executable} does not look like the Model Compiler venv Python. "
            "Activate the extension first, for example: source ~/sdk-extensions/model-sdk/bin/activate"
        )
    if str(bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
        raise SmokeFailure(f"{bin_dir} is not on PATH")
    log(f"using Python: {sys.executable}")


def smoke_preflight() -> SmokeCasePayload:
    require_active_modelsdk()
    smoke_python_environment()
    smoke_tools()
    smoke_python_modules()
    return SmokeCasePayload()


def required_package_versions() -> dict[str, str]:
    target_arch = os.environ.get("MODELSDK_SMOKE_ARCH", platform.machine()).lower()
    if target_arch in {"aarch64", "arm64"}:
        return ARM64_REQUIRED_PACKAGE_VERSIONS
    return {}


def smoke_python_environment() -> None:
    run([sys.executable, "-m", "pip", "check"], timeout=120)
    required_versions = required_package_versions()
    mismatches = []
    for package, expected in required_versions.items():
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(f"{package}: missing (expected {expected})")
            continue
        if installed != expected:
            mismatches.append(f"{package}: {installed} (expected {expected})")
    if mismatches:
        raise SmokeFailure("unexpected Python package versions: " + "; ".join(mismatches))
    if required_versions:
        log(
            "verified Python packages: "
            + ", ".join(
                f"{package}=={version}"
                for package, version in required_versions.items()
            )
        )


def smoke_tools() -> None:
    for tool in REQUIRED_TOOLS:
        path = shutil.which(tool)
        if not path:
            raise SmokeFailure(f"{tool} was not found on PATH")
        log(f"found {tool}: {path}")
        run([tool, "--help"], timeout=DEFAULT_TOOL_TIMEOUT, check=False)


def smoke_python_modules() -> None:
    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        raise SmokeFailure("missing Python modules: " + ", ".join(missing))
    log("required Python modules are importable")
    run(
        [
            sys.executable,
            "-c",
            "from gguf import GGUFReader; from llama_cpp import Llama; import safetensors.numpy; print('lmm deps ok')",
        ],
        timeout=DEFAULT_TOOL_TIMEOUT,
    )


def write_resnet50_onnx(output: Path) -> None:
    prepare_output_file(output)
    code = f"""
from pathlib import Path
import torch
from torchvision.models import resnet50

torch.manual_seed(0)
model = resnet50(weights=None).eval()
dummy = torch.randn(1, 3, 224, 224)
Path({str(output.parent)!r}).mkdir(parents=True, exist_ok=True)
torch.onnx.export(
    model,
    dummy,
    {str(output)!r},
    input_names=["input"],
    output_names=["output"],
    opset_version=17,
    do_constant_folding=True,
)
print({str(output)!r})
"""
    run([sys.executable, "-c", code], timeout=180)


def audit_onnx_model(model_path: Path, dtype: str, *, strict: bool) -> None:
    guard = REPO_ROOT / "skills" / "model_surgery" / "scripts" / "model_surgery_guard.py"
    proc = run(
        [
            sys.executable,
            str(guard),
            "audit-model",
            "--model",
            str(model_path),
            "--dtype",
            dtype,
        ],
        cwd=REPO_ROOT,
        timeout=120,
        check=False,
    )
    if proc.returncode == 0:
        return
    if strict:
        raise SmokeFailure(f"operator audit failed for {model_path}")
    log(f"operator audit returned {proc.returncode}; continuing because --strict-audit was not set")


def onnx_io_names(model_path: Path) -> tuple[list[str], list[str]]:
    import onnx

    model = onnx.load(str(model_path))
    initializer_names = {initializer.name for initializer in model.graph.initializer}
    input_names = [value.name for value in model.graph.input if value.name not in initializer_names]
    output_names = [value.name for value in model.graph.output]
    if not input_names:
        raise SmokeFailure(f"could not determine model inputs: {model_path}")
    if not output_names:
        raise SmokeFailure(f"could not determine model outputs: {model_path}")
    return input_names, output_names


def run_quantize_compile(
    model_path: Path,
    build_dir: Path,
    *,
    input_shape: str,
    compile_model: bool,
    dtype: str,
) -> None:
    helper = REPO_ROOT / "skills" / "quantize_compile" / "scripts" / "quantize_compile.py"
    prepared_path = model_path.with_name(f"{model_path.stem}_prepared.onnx")
    prepare_output_file(prepared_path)
    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
        except OSError as exc:
            raise SmokeFailure(
                f"cannot remove existing build directory: {build_dir}. "
                "Choose a fresh --work-dir or remove the stale directory first."
            ) from exc
    input_names, output_names = onnx_io_names(model_path)
    cmd = [
        sys.executable,
        str(helper),
        "--model_path",
        str(model_path),
        "--model_format",
        "onnx",
        "--model_layout",
        "NCHW",
        "--input_names",
        *input_names,
        "--input_shapes",
        input_shape,
        "--output_names",
        *output_names,
        "--device",
        "modalix",
        "--build_dir",
        str(build_dir),
    ]
    if dtype == "bfloat16":
        cmd.extend(["--bf16-activations", "--bf16-weights"])
    if not compile_model:
        cmd.append("--no-compile")
    run(cmd, cwd=REPO_ROOT, timeout=3600)


def validate_quantization_manifest(build_dir: Path, dtype: str) -> None:
    manifests = sorted(build_dir.rglob("quantization_manifest.json"))
    if len(manifests) != 1:
        raise SmokeFailure(
            f"expected one quantization manifest under {build_dir}, found {len(manifests)}"
        )
    try:
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeFailure(f"cannot read quantization manifest: {manifests[0]}") from exc

    expected = {
        "activation_precision": dtype,
        "weight_precision": dtype,
        "device": "modalix",
    }
    if manifest != expected:
        raise SmokeFailure(
            f"quantization manifest does not match requested {dtype} configuration: "
            f"expected {expected}, got {manifest}"
        )


def validate_and_measure_compiled_artifacts(
    label: str, build_dir: Path, dtype: str
) -> dict[str, str]:
    sima_files = sorted(build_dir.rglob("*.sima"))
    mpk_files = sorted(build_dir.rglob("*_mpk.tar.gz"))
    json_files = sorted(build_dir.rglob("*.json"))

    if not sima_files:
        raise SmokeFailure(f"no .sima package found under {build_dir}")
    if not mpk_files:
        raise SmokeFailure(f"no MPK archive found under {build_dir}")
    for path in [*sima_files, *mpk_files]:
        if path.stat().st_size == 0:
            raise SmokeFailure(f"compiled artifact is empty: {path}")

    metrics = {
        "sima_packages": str(len(sima_files)),
        "sima_bytes": str(sum(path.stat().st_size for path in sima_files)),
        "json_files": str(len(json_files)),
        "mpk_archives": str(len(mpk_files)),
    }

    for path in sima_files[:3]:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.namelist()
        except zipfile.BadZipFile as exc:
            raise SmokeFailure(f"invalid .sima package: {path}") from exc
        if not entries:
            raise SmokeFailure(f".sima package contains no entries: {path}")
        metrics[f"{path.name}:entries"] = str(len(entries))

    elf_paths: list[Path] = []
    extract_dir = build_dir / "_metrics_extract"
    if mpk_files:
        ensure_writable_dir(extract_dir)
    for archive_path in mpk_files:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.endswith(".elf"):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise SmokeFailure(f"cannot read MLA ELF from {archive_path}")
                elf_path = extract_dir / Path(member.name).name
                elf_path.write_bytes(extracted.read())
                elf_paths.append(elf_path)

    metrics["mla_elfs"] = str(len(elf_paths))
    if not elf_paths:
        raise SmokeFailure(f"MPK archives contain no MLA ELF under {build_dir}")
    if any(path.stat().st_size == 0 for path in elf_paths):
        raise SmokeFailure(f"MPK archive contains an empty MLA ELF under {build_dir}")
    run(["mla-size", *[str(path) for path in elf_paths]], timeout=120)
    run(["mla-readelf", "-h", str(elf_paths[0])], timeout=60)

    validate_quantization_manifest(build_dir, dtype)
    log(f"{label} metrics: " + ", ".join(f"{key}={value}" for key, value in metrics.items()))
    return metrics


def smoke_resnet(
    args: argparse.Namespace,
    *,
    compile_model: bool,
    dtype: str | None = None,
) -> SmokeCasePayload:
    dtype = dtype or args.dtype
    work_dir = work_dir_from_arg(args.work_dir, "modelsdk-smoke-")
    run_dir = make_run_dir(work_dir, f"resnet50-{dtype}")
    model_path = Path(args.resnet_model) if args.resnet_model else work_dir / "resnet50.onnx"
    action = "compile" if compile_model else "quantize"
    build_dir = run_dir / f"resnet50_{dtype}_{action}"
    if not model_path.exists():
        write_resnet50_onnx(model_path)
    sim_model_path = run_dir / "resnet50.sim.onnx"
    prepare_output_file(sim_model_path)
    run(["onnxsim", str(model_path), str(sim_model_path)], timeout=300)
    audit_onnx_model(sim_model_path, dtype, strict=args.strict_audit)
    run_quantize_compile(
        sim_model_path,
        build_dir,
        input_shape="1,3,224,224",
        compile_model=compile_model,
        dtype=dtype,
    )
    log(f"ResNet50 {dtype} smoke artifacts: {build_dir}")
    metrics: dict[str, str] = {}
    if compile_model:
        metrics = validate_and_measure_compiled_artifacts(
            f"resnet50-{dtype}", build_dir, dtype
        )
    return SmokeCasePayload(artifacts=build_dir, metrics=metrics)


def validate_llima_artifacts(output_dir: Path) -> None:
    mpk_dir = output_dir / "sima_files" / "mpk"
    archives = sorted(mpk_dir.glob("*.tar.gz"))
    if not archives:
        raise SmokeFailure(f"no compiled MPK archives found in {mpk_dir}")

    for archive in archives:
        if archive.stat().st_size == 0:
            raise SmokeFailure(f"compiled MPK is empty: {archive}")
        with tarfile.open(archive, "r:gz") as mpk:
            if not any(member.name.endswith(".elf") for member in mpk.getmembers()):
                raise SmokeFailure(f"compiled MPK contains no MLA ELF: {archive}")


def llima_sdk_inputs_from_onnx(onnx_path: Path) -> list[object]:
    import numpy as np
    import onnx

    onnx_model = onnx.load(str(onnx_path), load_external_data=False)
    rng = np.random.default_rng(1)
    inputs = []
    for value in onnx_model.graph.input:
        onnx_shape = tuple(
            dimension.dim_value for dimension in value.type.tensor_type.shape.dim
        )
        if len(onnx_shape) != 4 or any(dimension <= 0 for dimension in onnx_shape):
            raise SmokeFailure(
                f"expected static four-dimensional input for {value.name}, got {onnx_shape}"
            )

        dtype = onnx.helper.tensor_dtype_to_np_dtype(value.type.tensor_type.elem_type)
        sdk_shape = (onnx_shape[0], onnx_shape[2], onnx_shape[3], onnx_shape[1])
        if np.issubdtype(dtype, np.floating):
            inputs.append(rng.uniform(-1.0, 1.0, sdk_shape).astype(dtype))
        else:
            inputs.append(np.zeros(sdk_shape, dtype=dtype))
    return inputs


def assert_llima_quantized_outputs_close(reference: list[object], actual: list[object]) -> None:
    import numpy as np

    if len(reference) != len(actual):
        raise SmokeFailure(
            f"LLiMa output count differs: reference={len(reference)}, actual={len(actual)}"
        )

    for index, (reference_output, actual_output) in enumerate(zip(reference, actual, strict=True)):
        if reference_output.shape != actual_output.shape:
            raise SmokeFailure(
                f"LLiMa output {index} shape differs: "
                f"reference={reference_output.shape}, actual={actual_output.shape}"
            )
        absolute_tolerance = QWEN3_QUANTIZED_OUTPUT_TOLERANCE * float(
            np.max(np.abs(reference_output))
        )
        if not np.allclose(actual_output, reference_output, rtol=0.0, atol=absolute_tolerance):
            max_difference = float(np.max(np.abs(actual_output - reference_output)))
            raise SmokeFailure(
                f"LLiMa quantized output {index} differs from ONNX: "
                f"max_abs_diff={max_difference}, atol={absolute_tolerance}"
            )


def execute_llima_qwen3_quantized_parts(model_path: Path, output_dir: Path) -> None:
    from sima_lmm.model import EvalMode, VisionLanguageModel
    from sima_lmm.model.language_post_model import LanguagePostModel
    from sima_lmm.model.language_pre_model import LanguagePreModel

    vlm_model = VisionLanguageModel.from_hf_cache(
        hf_cache_path=model_path,
        model_name=model_path.name,
        onnx_path=output_dir / "onnx_files",
        sima_path=output_dir / "sima_files",
        max_num_tokens=1024,
        system_prompt=None,
    )
    components = [
        LanguagePreModel(
            vlm_model.cfg,
            f"{vlm_model.model_name}_language_n1_pre_layer0",
            onnx_path=vlm_model.onnx_path,
            sima_path=vlm_model.sima_path,
            hf_model=vlm_model.hf_model,
            num_tokens=1,
            layer_idx=0,
        ),
        LanguagePostModel(
            vlm_model.cfg,
            f"{vlm_model.model_name}_language_n1_post_layer0",
            onnx_path=vlm_model.onnx_path,
            sima_path=vlm_model.sima_path,
            hf_model=vlm_model.hf_model,
            num_tokens=1,
            layer_idx=0,
            final_softcapping=None,
        ),
    ]

    for component in components:
        inputs = llima_sdk_inputs_from_onnx(component.onnx_file_name)
        log(f"executing LLiMa quantized part with JAX: {component.model_name}")
        onnx_outputs = component.run_model(EvalMode.ONNX, inputs)
        quantized_outputs = component.run_model(EvalMode.SDK, inputs)
        assert_llima_quantized_outputs_close(onnx_outputs, quantized_outputs)


def llima_qwen3_compile_command(
    config_path: Path, output_dir: Path, model_path: Path
) -> list[str]:
    return [
        "llima-compile",
        "-c",
        str(config_path),
        "-j",
        "4",
        "-o",
        str(output_dir),
        str(model_path),
        "--no-quantize_embeddings",
        "--no-quantize_kv_cache",
    ]


def smoke_llima_qwen3(args: argparse.Namespace) -> SmokeCasePayload:
    from huggingface_hub import snapshot_download

    work_dir = work_dir_from_arg(args.work_dir, "modelsdk-smoke-")
    run_dir = make_run_dir(work_dir, "llima-qwen3")
    model_dir = run_dir / "Qwen3-0.6B"
    output_dir = run_dir / "output"
    config_path = run_dir / "compile_config.py"

    log(f"downloading {QWEN3_REPO_ID} at revision {QWEN3_REVISION}")
    model_path = Path(
        snapshot_download(
            repo_id=QWEN3_REPO_ID,
            revision=QWEN3_REVISION,
            local_dir=str(model_dir),
        )
    )
    config_path.write_text(QWEN3_COMPILE_CONFIGURATION, encoding="utf-8")

    command = llima_qwen3_compile_command(config_path, output_dir, model_path)
    for stage in ("--onnx", "--quantize", "--compile"):
        log(f"running LLiMa Qwen3 smoke stage: {stage}")
        run(command + [stage], timeout=3600)

    validate_llima_artifacts(output_dir)
    execute_llima_qwen3_quantized_parts(model_path, output_dir)
    log(f"LLiMa Qwen3 smoke artifacts: {output_dir}")
    return SmokeCasePayload(artifacts=output_dir)


def download_file(url: str, output: Path) -> None:
    ensure_writable_dir(output.parent)
    if output.exists() and output.stat().st_size > 0:
        log(f"using cached download: {output}")
        return
    log(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response:
        with output.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    if output.stat().st_size == 0:
        raise SmokeFailure(f"downloaded empty file: {output}")
    log(f"downloaded {output} ({output.stat().st_size} bytes)")


def smoke_yolo(args: argparse.Namespace) -> SmokeCasePayload:
    work_dir = work_dir_from_arg(args.work_dir, "modelsdk-yolo-")
    run_dir = make_run_dir(work_dir, "yolov8n")
    model_path = Path(args.yolo_model) if args.yolo_model else work_dir / "yolov8n.onnx"
    if not model_path.exists():
        download_file(args.yolo_url, model_path)

    sim_model_path = run_dir / "yolov8n.sim.onnx"
    build_dir = run_dir / "yolov8n_compile"
    prepare_output_file(sim_model_path)
    run(
        [
            "onnxsim",
            str(model_path),
            str(sim_model_path),
            "--overwrite-input-shape",
            "1,3,640,640",
        ],
        timeout=300,
    )
    audit_onnx_model(sim_model_path, args.dtype, strict=args.strict_audit)

    pipeline_dir = Path(args.model_to_pipeline_dir) if args.model_to_pipeline_dir else None
    if pipeline_dir:
        if not pipeline_dir.exists():
            raise SmokeFailure(f"model-to-pipeline directory does not exist: {pipeline_dir}")
        yolo_refs = list(pipeline_dir.rglob("*yolo*"))
        if not yolo_refs:
            raise SmokeFailure(f"no YOLO-related files found under {pipeline_dir}")
        log(f"found {len(yolo_refs)} YOLO-related model-to-pipeline files")

    run_quantize_compile(
        sim_model_path,
        build_dir,
        input_shape="1,3,640,640",
        compile_model=True,
        dtype=args.dtype,
    )
    log(f"YOLOv8 smoke artifacts: {build_dir}")
    metrics = measure_compiled_artifacts("yolov8", build_dir)
    return SmokeCasePayload(artifacts=build_dir, metrics=metrics)


def run_case(name: str, fn) -> SmokeCaseResult:
    start = time.monotonic()
    try:
        payload = fn()
        duration = time.monotonic() - start
        if isinstance(payload, SmokeCasePayload):
            return SmokeCaseResult(
                name=name,
                status="PASS",
                duration_s=duration,
                artifacts=payload.artifacts,
                metrics=payload.metrics,
            )
        return SmokeCaseResult(name=name, status="PASS", duration_s=duration, artifacts=payload)
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        return SmokeCaseResult(name=name, status="TIMEOUT", duration_s=duration, error=" ".join(exc.cmd))
    except Exception as exc:
        duration = time.monotonic() - start
        return SmokeCaseResult(name=name, status="FAIL", duration_s=duration, error=str(exc))


def print_summary(results: list[SmokeCaseResult]) -> None:
    print()
    log("Summary")
    name_w = max([len("case"), *[len(result.name) for result in results]])
    status_w = max([len("status"), *[len(result.status) for result in results]])
    print(f"{'case':<{name_w}}  {'status':<{status_w}}  {'seconds':>8}  artifacts")
    print(f"{'-' * name_w}  {'-' * status_w}  {'-' * 8}  {'-' * 9}")
    for result in results:
        artifacts = str(result.artifacts) if result.artifacts else "-"
        print(f"{result.name:<{name_w}}  {result.status:<{status_w}}  {result.duration_s:8.1f}  {artifacts}")
        if result.error:
            print(f"{'':<{name_w}}  {'':<{status_w}}  {'':>8}  error: {result.error}")
        if result.metrics:
            metrics = ", ".join(f"{key}={value}" for key, value in result.metrics.items())
            print(f"{'':<{name_w}}  {'':<{status_w}}  {'':>8}  metrics: {metrics}")


def smoke_all(args: argparse.Namespace) -> int:
    results = [
        run_case("preflight", smoke_preflight),
        run_case("resnet50-compile", lambda: smoke_resnet(args, compile_model=True)),
        run_case("yolov8-compile", lambda: smoke_yolo(args)),
    ]
    print_summary(results)
    return 0 if all(result.status == "PASS" for result in results) else 1


def smoke_resnet_precisions(args: argparse.Namespace) -> int:
    work_dir = work_dir_from_arg(args.work_dir, "modelsdk-resnet-precisions-")
    args.work_dir = str(work_dir)
    results = [
        run_case("preflight", smoke_preflight),
        run_case(
            "resnet50-int8-compile",
            lambda: smoke_resnet(args, compile_model=True, dtype="int8"),
        ),
        run_case(
            "resnet50-bfloat16-compile",
            lambda: smoke_resnet(args, compile_model=True, dtype="bfloat16"),
        ),
    ]
    print_summary(results)
    return 0 if all(result.status == "PASS" for result in results) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a Model Compiler extension installation")
    parser.add_argument(
        "--tier",
        choices=[
            "basic",
            "resnet-export",
            "resnet-quantize",
            "resnet-compile",
            "resnet-compile-precisions",
            "llima-qwen3-compile",
            "yolo",
            "all",
        ],
        default=os.environ.get("MODELSDK_SMOKE_TIER", "basic"),
        help="Smoke-test depth. Default: %(default)s",
    )
    parser.add_argument("--work-dir", help="Directory for generated smoke artifacts")
    parser.add_argument("--resnet-model", help="Existing ResNet50 ONNX model to use")
    parser.add_argument("--yolo-model", help="Existing YOLO ONNX model for the yolo tier")
    parser.add_argument(
        "--yolo-url",
        default=os.environ.get("MODELSDK_SMOKE_YOLO_URL", DEFAULT_YOLO_URL),
        help="YOLO ONNX URL to download when --yolo-model is absent",
    )
    parser.add_argument("--model-to-pipeline-dir", help="Optional model-to-pipeline checkout/reference directory")
    parser.add_argument("--dtype", default="int8", choices=["int8", "bfloat16"], help="Audit dtype")
    parser.add_argument("--strict-audit", action="store_true", help="Fail when the ONNX operator support audit reports unknown or unsupported ops")
    parser.add_argument("--verbose", action="store_true", help="Print full command output")
    return parser.parse_args()


def main() -> int:
    global VERBOSE
    args = parse_args()
    VERBOSE = args.verbose
    try:
        if args.tier == "all":
            return smoke_all(args)
        if args.tier == "resnet-compile-precisions":
            return smoke_resnet_precisions(args)

        smoke_preflight()

        if args.tier == "resnet-export":
            work_dir = work_dir_from_arg(args.work_dir, "modelsdk-smoke-")
            write_resnet50_onnx(Path(args.resnet_model) if args.resnet_model else work_dir / "resnet50.onnx")
        elif args.tier == "resnet-quantize":
            smoke_resnet(args, compile_model=False)
        elif args.tier == "resnet-compile":
            smoke_resnet(args, compile_model=True)
        elif args.tier == "llima-qwen3-compile":
            smoke_llima_qwen3(args)
        elif args.tier == "yolo":
            smoke_yolo(args)

        log(f"PASS: {args.tier}")
        return 0
    except subprocess.TimeoutExpired as exc:
        print(f"[modelsdk-smoke] TIMEOUT: {' '.join(exc.cmd)}", file=sys.stderr)
        return 124
    except SmokeFailure as exc:
        print(f"[modelsdk-smoke] FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

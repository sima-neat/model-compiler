#!/usr/bin/env python3
"""Post-install smoke tests for the Model Compiler extension."""

from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
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
DEFAULT_TOOL_TIMEOUT = 30
DEFAULT_YOLO_URL = "https://huggingface.co/webml/yolov8n/resolve/main/onnx/yolov8n.onnx"
DEFAULT_WORK_ROOT = Path.home() / "tmp"

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
    "llama_cpp",
    "safetensors",
]

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
    smoke_tools()
    smoke_python_modules()
    return SmokeCasePayload()


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
    if not compile_model:
        cmd.append("--no-compile")
    run(cmd, cwd=REPO_ROOT, timeout=3600)


def measure_compiled_artifacts(label: str, build_dir: Path) -> dict[str, str]:
    sima_files = sorted(build_dir.rglob("*.sima"))
    mpk_files = sorted(build_dir.rglob("*_mpk.tar.gz"))
    json_files = sorted(build_dir.rglob("*.json"))

    metrics = {
        "sima_packages": str(len(sima_files)),
        "sima_bytes": str(sum(path.stat().st_size for path in sima_files)),
        "json_files": str(len(json_files)),
        "mpk_archives": str(len(mpk_files)),
    }

    for path in sima_files[:3]:
        with zipfile.ZipFile(path) as archive:
            metrics[f"{path.name}:entries"] = str(len(archive.namelist()))

    elf_paths: list[Path] = []
    extract_dir = build_dir / "_metrics_extract"
    if mpk_files:
        ensure_writable_dir(extract_dir)
    for archive_path in mpk_files:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.endswith(".elf"):
                    continue
                member.name = Path(member.name).name
                archive.extract(member, extract_dir)
                elf_paths.append(extract_dir / member.name)

    metrics["mla_elfs"] = str(len(elf_paths))
    if elf_paths:
        run(["mla-size", *[str(path) for path in elf_paths]], timeout=120)
        run(["mla-readelf", "-h", str(elf_paths[0])], timeout=60)

    log(f"{label} metrics: " + ", ".join(f"{key}={value}" for key, value in metrics.items()))
    return metrics


def smoke_resnet(args: argparse.Namespace, *, compile_model: bool) -> SmokeCasePayload:
    work_dir = work_dir_from_arg(args.work_dir, "modelsdk-smoke-")
    run_dir = make_run_dir(work_dir, "resnet50")
    model_path = Path(args.resnet_model) if args.resnet_model else work_dir / "resnet50.onnx"
    build_dir = run_dir / ("resnet50_compile" if compile_model else "resnet50_quantize")
    if not model_path.exists():
        write_resnet50_onnx(model_path)
    sim_model_path = run_dir / "resnet50.sim.onnx"
    prepare_output_file(sim_model_path)
    run(["onnxsim", str(model_path), str(sim_model_path)], timeout=300)
    audit_onnx_model(sim_model_path, args.dtype, strict=args.strict_audit)
    run_quantize_compile(
        sim_model_path,
        build_dir,
        input_shape="1,3,224,224",
        compile_model=compile_model,
    )
    log(f"ResNet50 smoke artifacts: {build_dir}")
    metrics: dict[str, str] = {}
    if compile_model:
        metrics = measure_compiled_artifacts("resnet50", build_dir)
    return SmokeCasePayload(artifacts=build_dir, metrics=metrics)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a Model Compiler extension installation")
    parser.add_argument(
        "--tier",
        choices=["basic", "resnet-export", "resnet-quantize", "resnet-compile", "yolo", "all"],
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

        smoke_preflight()

        if args.tier == "resnet-export":
            work_dir = work_dir_from_arg(args.work_dir, "modelsdk-smoke-")
            write_resnet50_onnx(Path(args.resnet_model) if args.resnet_model else work_dir / "resnet50.onnx")
        elif args.tier == "resnet-quantize":
            smoke_resnet(args, compile_model=False)
        elif args.tier == "resnet-compile":
            smoke_resnet(args, compile_model=True)
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

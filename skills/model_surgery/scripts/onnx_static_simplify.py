#!/usr/bin/env python3
"""Freeze symbolic ONNX dimensions, optionally simplify, and print I/O shapes."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import onnx


def parse_replacement(item: str) -> tuple[str, int]:
    if "=" not in item:
        raise ValueError(f"Invalid replacement '{item}', expected key=value")
    key, value = item.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"Invalid replacement '{item}', key is empty")
    try:
        v = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid replacement '{item}', value must be integer") from exc
    if v < 1:
        raise ValueError(f"Invalid replacement '{item}', value must be >= 1")
    return key, v


def freeze_symbolic_dims(model: onnx.ModelProto, dim_map: dict[str, int]) -> int:
    value_infos = list(model.graph.input) + list(model.graph.output) + list(model.graph.value_info)
    changed = 0
    for value_info in value_infos:
        tensor_type = value_info.type.tensor_type
        if not tensor_type.HasField("shape"):
            continue
        for dim in tensor_type.shape.dim:
            key = dim.dim_param
            if key in dim_map:
                dim.ClearField("dim_param")
                dim.dim_value = int(dim_map[key])
                changed += 1
    return changed


def run_onnxsim(input_path: Path, output_path: Path) -> None:
    onnxsim_bin = shutil.which("onnxsim")
    if not onnxsim_bin:
        raise RuntimeError("onnxsim not found in PATH. Install with `pip install onnxsim`.")
    subprocess.run([onnxsim_bin, input_path.as_posix(), output_path.as_posix()], check=True)


def describe_io_shapes(model_path: Path) -> str:
    model = onnx.load(model_path.as_posix())
    lines: list[str] = []
    for section_name, values in (("inputs", model.graph.input), ("outputs", model.graph.output)):
        lines.append(f"{section_name}:")
        for value in values:
            dims = []
            for dim in value.type.tensor_type.shape.dim:
                if dim.HasField("dim_value"):
                    dims.append(str(dim.dim_value))
                else:
                    dims.append(dim.dim_param or "?")
            lines.append(f"  {value.name}: {dims}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze symbolic dims in ONNX and simplify with onnxsim."
    )
    parser.add_argument("--input", type=Path, required=True, help="Input ONNX path")
    parser.add_argument("--output", type=Path, required=True, help="Output ONNX path")
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        help="Symbolic dim replacement in key=value format. Repeatable.",
    )
    parser.add_argument(
        "--skip-simplify",
        action="store_true",
        help="Skip onnxsim and write staticized graph directly to --output.",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="Keep intermediate '.static.onnx' next to --output when simplify is enabled.",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"Input model not found: {input_path}", file=sys.stderr)
        return 1

    dim_map: dict[str, int] = {}
    try:
        for item in args.replace:
            k, v = parse_replacement(item)
            dim_map[k] = v
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    model = onnx.load(input_path.as_posix())
    changed = freeze_symbolic_dims(model, dim_map)

    if args.skip_simplify:
        onnx.save(model, output_path.as_posix())
        print(f"Wrote static model to: {output_path}")
        print(f"Frozen dimensions: {changed}")
        print(describe_io_shapes(output_path))
        return 0

    intermediate_path = output_path.with_suffix(".static.onnx")
    onnx.save(model, intermediate_path.as_posix())

    try:
        run_onnxsim(intermediate_path, output_path)
    except Exception as exc:
        if intermediate_path.exists() and not args.keep_intermediate:
            intermediate_path.unlink()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if intermediate_path.exists() and not args.keep_intermediate:
        intermediate_path.unlink()

    print(f"Wrote simplified static model to: {output_path}")
    print(f"Frozen dimensions: {changed}")
    print(describe_io_shapes(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

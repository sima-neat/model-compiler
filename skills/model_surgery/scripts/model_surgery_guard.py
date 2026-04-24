#!/usr/bin/env python3
"""ONNX graph surgery guardrails for SiMa MLA operator support."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _default_support_json() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "supported_operators.json"


def _load_support_db(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Support JSON not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if "operators" not in data or not isinstance(data["operators"], dict):
        raise ValueError("Invalid support JSON: expected top-level 'operators' object")

    return data


def _load_model_ops(model_path: Path) -> Counter:
    try:
        import onnx  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("onnx package is required: pip install onnx") from exc

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    model = onnx.load(str(model_path))
    counts: Counter = Counter()
    for node in model.graph.node:
        counts[node.op_type] += 1
    return counts


def _is_supported(entry: dict[str, Any] | None, dtype: str) -> bool:
    if entry is None:
        return False
    if dtype == "any":
        int8_ok = isinstance(entry.get("int8"), str) and entry["int8"].strip().upper() == "Y"
        bf16_ok = isinstance(entry.get("bfloat16"), str) and entry["bfloat16"].strip().upper() == "Y"
        return int8_ok or bf16_ok

    v = entry.get(dtype)
    return isinstance(v, str) and v.strip().upper() == "Y"


def _build_audit_report(
    support_db: dict[str, Any],
    op_counts: Counter,
    dtype: str,
) -> dict[str, Any]:
    operators = support_db["operators"]

    supported = []
    unsupported = []
    unknown = []

    for op_type, count in sorted(op_counts.items()):
        entry = operators.get(op_type)
        record = {
            "operator": op_type,
            "count": count,
            "onnx-opset-version": None if entry is None else entry.get("onnx-opset-version"),
            "int8": None if entry is None else entry.get("int8"),
            "bfloat16": None if entry is None else entry.get("bfloat16"),
            "sima_hw_sw_constraints": None if entry is None else entry.get("sima_hw_sw_constraints"),
            "notes": None if entry is None else entry.get("notes"),
        }

        if entry is None:
            unknown.append(record)
        elif _is_supported(entry, dtype):
            supported.append(record)
        else:
            unsupported.append(record)

    return {
        "release": support_db.get("release"),
        "dtype": dtype,
        "model_operator_total": sum(op_counts.values()),
        "unique_operator_total": len(op_counts),
        "supported_count": len(supported),
        "unsupported_count": len(unsupported),
        "unknown_count": len(unknown),
        "supported": supported,
        "unsupported": unsupported,
        "unknown": unknown,
    }


def _print_audit_human(report: dict[str, Any]) -> None:
    print(f"Release: {report['release']}")
    print(f"DType policy: {report['dtype']}")
    print(f"Operators in graph: {report['model_operator_total']} ({report['unique_operator_total']} unique)")
    print(
        "Support summary: "
        f"supported={report['supported_count']}, "
        f"unsupported={report['unsupported_count']}, "
        f"unknown={report['unknown_count']}"
    )

    if report["unsupported"]:
        print("\nUnsupported operators:")
        for item in report["unsupported"]:
            print(
                f"- {item['operator']} (count={item['count']}, "
                f"int8={item['int8']}, bfloat16={item['bfloat16']})"
            )
            if item["sima_hw_sw_constraints"]:
                print(f"  constraints: {item['sima_hw_sw_constraints']}")
            if item["notes"]:
                print(f"  notes: {item['notes']}")

    if report["unknown"]:
        print("\nUnknown operators (not present in support JSON):")
        for item in report["unknown"]:
            print(f"- {item['operator']} (count={item['count']})")


def cmd_query_op(args: argparse.Namespace) -> int:
    db = _load_support_db(Path(args.supported_ops_json))
    op = args.op
    entry = db["operators"].get(op)
    if entry is None:
        print(f"Operator '{op}' not found in support DB for release {db.get('release')}")
        return 1

    out = {"release": db.get("release"), "operator": op, **entry}
    print(json.dumps(out, indent=2, ensure_ascii=True))
    return 0


def cmd_list_supported(args: argparse.Namespace) -> int:
    db = _load_support_db(Path(args.supported_ops_json))
    dtype = args.dtype

    ops = []
    for op_name, entry in db["operators"].items():
        if _is_supported(entry, dtype):
            ops.append(op_name)

    for op in sorted(ops):
        print(op)
    return 0


def cmd_audit_model(args: argparse.Namespace) -> int:
    db = _load_support_db(Path(args.supported_ops_json))
    counts = _load_model_ops(Path(args.model))
    report = _build_audit_report(db, counts, args.dtype)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        _print_audit_human(report)

    # Non-zero exit if model contains unsupported/unknown ops for quick CI use.
    if report["unsupported_count"] > 0 or report["unknown_count"] > 0:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SiMa MLA ONNX surgery guard")
    p.add_argument(
        "--supported-ops-json",
        default=str(_default_support_json()),
        help="Path to supported_operators.json",
    )

    sp = p.add_subparsers(dest="cmd", required=True)

    q = sp.add_parser("query-op", help="Show support metadata for one operator")
    q.add_argument("--op", required=True, help="Operator name, e.g. Gather")
    q.set_defaults(func=cmd_query_op)

    ls = sp.add_parser("list-supported", help="List supported operators by dtype")
    ls.add_argument("--dtype", choices=["int8", "bfloat16", "any"], default="any")
    ls.set_defaults(func=cmd_list_supported)

    audit = sp.add_parser("audit-model", help="Audit ONNX model operators")
    audit.add_argument("--model", required=True, help="Path to ONNX model")
    audit.add_argument("--dtype", choices=["int8", "bfloat16", "any"], default="int8")
    audit.add_argument("--json", action="store_true", help="Emit JSON report")
    audit.set_defaults(func=cmd_audit_model)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

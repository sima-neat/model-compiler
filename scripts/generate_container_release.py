#!/usr/bin/env python3
"""Generate human-readable Model Compiler container release metadata."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
from pathlib import Path
from typing import Any, Mapping


def normalize_arch(raw: str) -> str:
    value = raw.strip().lower()
    if value in {"amd64", "x86_64"}:
        return "x86_64"
    if value in {"arm64", "aarch64"}:
        return "aarch64"
    return value


def package_name(raw: str) -> str:
    """Strip extras and use the normalized display form used by Python metadata."""
    base = raw.split("[", 1)[0].strip()
    return re.sub(r"[-_.]+", "-", base).lower()


def selected_list(source: Mapping[str, Any], arch: str, key: str) -> list[Any]:
    arch_doc = source.get(arch)
    if isinstance(arch_doc, dict) and key in arch_doc:
        value = arch_doc[key]
    else:
        value = source.get(key, [])
    return value if isinstance(value, list) else []


def component_versions(
    source: Mapping[str, Any],
    target_arch: str,
    installed_versions: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return declared components, preferring their installed package versions."""
    arch = normalize_arch(target_arch)
    declared: dict[str, str] = {}

    overrides = source.get("dependency_overrides", {})
    if isinstance(overrides, dict):
        declared.update(
            (package_name(str(name)), str(version))
            for name, version in overrides.items()
            if str(name).strip() and str(version).strip()
        )
    arch_doc = source.get(arch)
    if isinstance(arch_doc, dict):
        arch_overrides = arch_doc.get("dependency_overrides", {})
        if isinstance(arch_overrides, dict):
            declared.update(
                (package_name(str(name)), str(version))
                for name, version in arch_overrides.items()
                if str(name).strip() and str(version).strip()
            )

    for key in ("preload-packages", "source-packages", "python-packages"):
        for item in selected_list(source, arch, key):
            if not isinstance(item, dict) or not str(item.get("name", "")).strip():
                continue
            name = package_name(str(item["name"]))
            version = str(item.get("version", "")).strip()
            vulcan = item.get("vulcan")
            if not version and isinstance(vulcan, dict):
                version = str(vulcan.get("ref") or vulcan.get("policy") or "").strip()
            if version:
                declared[name] = version

    resolved = {package_name(name): version for name, version in (installed_versions or {}).items()}
    for name in list(declared):
        if name in resolved:
            declared[name] = resolved[name]
            continue
        if installed_versions is None:
            try:
                declared[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass

    for item in selected_list(source, arch, "binary-packages"):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        version = str(item.get("version", "")).strip()
        if name and version:
            declared[name] = version

    return dict(sorted(declared.items()))


def render_release(
    source: Mapping[str, Any],
    *,
    model_compiler_version: str,
    git_branch: str,
    git_commit: str,
    build_time: str,
    target_arch: str,
    installed_versions: Mapping[str, str] | None = None,
) -> str:
    lines = [
        f"Model Compiler Version = {model_compiler_version}",
        f"SDK Version = {source.get('sdk_version', 'unknown')}",
        f"Python Version = {source.get('python_version', platform.python_version())}",
        f"Target Architecture = {normalize_arch(target_arch)}",
        f"Git Branch = {git_branch}",
        f"Git Commit = {git_commit}",
        f"Build Time (UTC) = {build_time}",
        "",
        "Component Versions:",
    ]
    lines.extend(
        f"  {name} = {version}"
        for name, version in component_versions(
            source, target_arch, installed_versions=installed_versions
        ).items()
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-compiler-version", required=True)
    parser.add_argument("--git-branch", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--build-time", required=True)
    parser.add_argument("--target-arch", required=True)
    args = parser.parse_args()

    source = json.loads(args.source_json.read_text(encoding="utf-8"))
    args.output.write_text(
        render_release(
            source,
            model_compiler_version=args.model_compiler_version,
            git_branch=args.git_branch,
            git_commit=args.git_commit,
            build_time=args.build_time,
            target_arch=args.target_arch,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

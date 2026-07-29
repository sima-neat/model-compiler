#!/usr/bin/env python3
"""Resolve and apply newer component builds within source.json version families."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INDEX_URL = (
    "https://artifacts.eng.sima.ai/artifactory/api/pypi/"
    "sima-pypi-group/simple"
)
DEFAULT_ARTIFACTORY_URL = "https://artifacts.eng.sima.ai/artifactory"
SUPPORTED_ARCHES = ("x86_64", "aarch64")
PLATFORM_ARGS = {
    "x86_64": (
        "manylinux_2_28_x86_64",
        "manylinux_2_27_x86_64",
        "manylinux2014_x86_64",
        "linux_x86_64",
    ),
    "aarch64": (
        "manylinux_2_28_aarch64",
        "manylinux_2_27_aarch64",
        "manylinux2014_aarch64",
        "linux_aarch64",
    ),
}
MLA_ARCH_SUFFIX = {"x86_64": "x86", "aarch64": "aarch64"}

PYTHON_VERSION_RE = re.compile(
    r"^(?P<base>\d+\.\d+\.\d+)\.dev(?P<dev>\d+)"
    r"\+(?P<channel>[A-Za-z0-9_-]+)\.(?P<build>\d+)$"
)
BINARY_VERSION_RE = re.compile(
    r"^(?P<base>v\d+\.\d+\.\d+)-"
    r"(?P<channel>[A-Za-z0-9_-]+)\.(?P<build>\d+)$"
)


class UpdateError(RuntimeError):
    """Raised when component resolution cannot be completed safely."""


@dataclass(frozen=True)
class VersionFamily:
    prefix: str
    build: int
    pattern: re.Pattern[str]

    def parse_candidate(self, value: str) -> int | None:
        match = self.pattern.fullmatch(value)
        return int(match.group("build")) if match else None


@dataclass(frozen=True)
class Component:
    component_id: str
    kind: str
    name: str
    current: str


def normalize_package_name(name: str) -> str:
    name = name.split("[", 1)[0]
    return re.sub(r"[-_.]+", "-", name).lower()


def python_family(version: str) -> VersionFamily | None:
    match = PYTHON_VERSION_RE.fullmatch(version)
    if not match:
        return None
    prefix = (
        f"{match.group('base')}.dev{match.group('dev')}"
        f"+{match.group('channel')}."
    )
    return VersionFamily(
        prefix=prefix,
        build=int(match.group("build")),
        pattern=re.compile(rf"^{re.escape(prefix)}(?P<build>\d+)$"),
    )


def binary_family(version: str) -> VersionFamily | None:
    match = BINARY_VERSION_RE.fullmatch(version)
    if not match:
        return None
    prefix = f"{match.group('base')}-{match.group('channel')}."
    return VersionFamily(
        prefix=prefix,
        build=int(match.group("build")),
        pattern=re.compile(rf"^{re.escape(prefix)}(?P<build>\d+)$"),
    )


def effective_doc(doc: dict[str, Any], target_arch: str) -> dict[str, Any]:
    arch_doc = doc.get(target_arch)
    return arch_doc if isinstance(arch_doc, dict) else doc


def collect_components(doc: dict[str, Any], target_arch: str) -> list[Component]:
    selected = effective_doc(doc, target_arch)
    components: dict[str, Component] = {}

    overrides = selected.get("dependency_overrides", doc.get("dependency_overrides", {}))
    if isinstance(overrides, dict):
        for name, version in overrides.items():
            if not isinstance(version, str) or python_family(version) is None:
                continue
            normalized = normalize_package_name(str(name))
            component = Component(
                component_id=f"python:{normalized}:{version}",
                kind="python",
                name=normalized,
                current=version,
            )
            components[component.component_id] = component

    packages = selected.get("python-packages", doc.get("python-packages", []))
    if isinstance(packages, list):
        for item in packages:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            version = item.get("version")
            if (
                not isinstance(name, str)
                or not isinstance(version, str)
                or isinstance(item.get("url"), str)
                or isinstance(item.get("file"), str)
                or python_family(version) is None
            ):
                continue
            normalized = normalize_package_name(name)
            component = Component(
                component_id=f"python:{normalized}:{version}",
                kind="python",
                name=normalized,
                current=version,
            )
            components[component.component_id] = component

    binaries = selected.get("binary-packages", doc.get("binary-packages", []))
    if isinstance(binaries, list):
        for item in binaries:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            version = item.get("version")
            if (
                not isinstance(name, str)
                or not isinstance(version, str)
                or binary_family(version) is None
            ):
                continue
            clean_name = name.strip().strip("/")
            component = Component(
                component_id=f"binary:{clean_name}:{version}",
                kind="binary",
                name=clean_name,
                current=version,
            )
            components[component.component_id] = component

    return sorted(components.values(), key=lambda item: item.component_id)


def curl_text(url: str, *, head: bool = False) -> str:
    command = ["curl", "-fsSL", "--netrc-optional"]
    if head:
        command.extend(["--head", "--output", "/dev/null"])
    command.append(url)
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or f"curl exited with {result.returncode}"
        raise UpdateError(f"failed to query {url}: {detail}")
    return result.stdout


def python_index_versions(
    package: str,
    current: str,
    index_url: str,
) -> list[str]:
    family = python_family(current)
    if family is None:
        return []
    package_url = f"{index_url.rstrip('/')}/{normalize_package_name(package)}/"
    page = urllib.parse.unquote(html.unescape(curl_text(package_url)))
    page_pattern = re.compile(
        rf"{re.escape(family.prefix)}(?P<build>\d+)"
    )
    matches = {
        match.group(0)
        for match in page_pattern.finditer(page)
        if int(match.group("build")) > family.build
    }
    return sorted(
        matches,
        key=lambda value: family.parse_candidate(value) or -1,
        reverse=True,
    )


def wheel_is_available(
    package: str,
    version: str,
    *,
    target_arch: str,
    python_version: str,
    index_url: str,
) -> bool:
    with tempfile.TemporaryDirectory(prefix="component-wheel-check-") as output_dir:
        command = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--no-input",
            "--no-deps",
            "--only-binary=:all:",
            "--index-url",
            index_url,
            "--dest",
            output_dir,
        ]
        for platform in PLATFORM_ARGS[target_arch]:
            command.extend(["--platform", platform])
        command.extend(
            [
                "--implementation",
                "cp",
                "--abi",
                f"cp{python_version}",
                "--python-version",
                python_version,
                f"{package}=={version}",
            ]
        )
        result = subprocess.run(command, text=True, capture_output=True)
        return result.returncode == 0


def binary_index_versions(
    component: Component,
    *,
    target_arch: str,
    artifactory_url: str,
) -> list[str]:
    family = binary_family(component.current)
    if family is None:
        return []
    parent, _, leaf = component.name.rpartition("/")
    if not parent:
        raise UpdateError(
            f"binary package {component.name!r} must include its Artifactory path"
        )
    if leaf != "mla-toolchain":
        raise UpdateError(
            f"automatic binary resolution is not implemented for {component.name!r}"
        )
    query = (
        f"{artifactory_url.rstrip('/')}/api/storage/{parent}"
        "?list&deep=0&listFolders=0"
    )
    try:
        listing = json.loads(curl_text(query))
    except json.JSONDecodeError as exc:
        raise UpdateError(f"Artifactory returned invalid JSON for {component.name}") from exc

    archive_suffix = MLA_ARCH_SUFFIX[target_arch]
    filename_re = re.compile(
        rf"^/?{re.escape(leaf)}-(?P<version>{re.escape(family.prefix)}\d+)"
        rf"-{re.escape(archive_suffix)}-ubuntu\.(?:zip)$"
    )
    versions = set()
    for item in listing.get("files", []):
        uri = item.get("uri") if isinstance(item, dict) else None
        if not isinstance(uri, str):
            continue
        match = filename_re.fullmatch(uri)
        if not match:
            continue
        version = match.group("version")
        build = family.parse_candidate(version)
        if build is not None and build > family.build:
            versions.add(version)
    return sorted(
        versions,
        key=lambda value: family.parse_candidate(value) or -1,
        reverse=True,
    )


def scan(
    source_json: Path,
    *,
    target_arch: str,
    output: Path,
    index_url: str,
    artifactory_url: str,
    max_candidates: int,
) -> None:
    doc = json.loads(source_json.read_text(encoding="utf-8"))
    python_version = re.sub(
        r"^(\d+)\.(\d+)(?:\.\d+)?$", r"\1\2", str(doc.get("python_version", "3.12"))
    )
    report: dict[str, Any] = {
        "target_arch": target_arch,
        "source_json": str(source_json),
        "source_sha256": hashlib.sha256(source_json.read_bytes()).hexdigest(),
        "components": {},
    }

    for component in collect_components(doc, target_arch):
        if component.kind == "python":
            candidates = python_index_versions(
                component.name, component.current, index_url
            )
            if max_candidates > 0:
                candidates = candidates[:max_candidates]
            available = [
                version
                for version in candidates
                if wheel_is_available(
                    component.name,
                    version,
                    target_arch=target_arch,
                    python_version=python_version,
                    index_url=index_url,
                )
            ]
        else:
            available = binary_index_versions(
                component,
                target_arch=target_arch,
                artifactory_url=artifactory_url,
            )
            if max_candidates > 0:
                available = available[:max_candidates]
        report["components"][component.component_id] = {
            "kind": component.kind,
            "name": component.name,
            "current": component.current,
            "available": available,
        }
        newest = available[0] if available else "none"
        print(
            f"[{target_arch}] {component.name}: current={component.current}, "
            f"newest-compatible={newest}",
            flush=True,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def iter_manifest_version_values(doc: Any) -> Iterable[str]:
    if isinstance(doc, dict):
        for value in doc.values():
            yield from iter_manifest_version_values(value)
    elif isinstance(doc, list):
        for value in doc:
            yield from iter_manifest_version_values(value)
    elif isinstance(doc, str):
        yield doc


def iter_component_version_values(doc: dict[str, Any]) -> Iterable[str]:
    for section in (doc, *(value for value in doc.values() if isinstance(value, dict))):
        overrides = section.get("dependency_overrides", {})
        if isinstance(overrides, dict):
            for value in overrides.values():
                if isinstance(value, str):
                    yield value
        for key in ("python-packages", "binary-packages"):
            packages = section.get(key, [])
            if not isinstance(packages, list):
                continue
            for item in packages:
                if isinstance(item, dict) and isinstance(item.get("version"), str):
                    yield item["version"]


def select_updates(
    source_doc: dict[str, Any],
    reports: list[dict[str, Any]],
) -> dict[str, str]:
    if not reports:
        raise UpdateError("at least one architecture scan report is required")
    report_by_arch: dict[str, dict[str, Any]] = {}
    for report in reports:
        arch = str(report.get("target_arch"))
        if arch not in SUPPORTED_ARCHES:
            raise UpdateError(f"unsupported scan report architecture: {arch!r}")
        if arch in report_by_arch:
            raise UpdateError(f"duplicate scan report for architecture: {arch}")
        report_by_arch[arch] = report

    components_by_arch = {
        arch: {
            component.component_id: component
            for component in collect_components(source_doc, arch)
        }
        for arch in report_by_arch
    }
    source_components = {
        component_id: component
        for arch_components in components_by_arch.values()
        for component_id, component in arch_components.items()
    }
    updates: dict[str, str] = {}
    for component_id, component in sorted(source_components.items()):
        required_arches = [
            arch
            for arch, arch_components in components_by_arch.items()
            if component_id in arch_components
        ]
        entries = [
            report_by_arch[arch].get("components", {}).get(component_id)
            for arch in required_arches
        ]
        if any(not isinstance(entry, dict) for entry in entries):
            raise UpdateError(f"scan report is missing component {component_id}")
        common = set(entries[0].get("available", []))
        for entry in entries[1:]:
            common.intersection_update(entry.get("available", []))
        family = (
            python_family(component.current)
            if component.kind == "python"
            else binary_family(component.current)
        )
        if family is None:
            continue
        eligible = [
            value
            for value in common
            if family.parse_candidate(value) is not None
            and (family.parse_candidate(value) or -1) > family.build
        ]
        if eligible:
            updates[component_id] = max(
                eligible, key=lambda value: family.parse_candidate(value) or -1
            )
    return updates


def apply_updates_preserving_format(
    source_text: str,
    source_doc: dict[str, Any],
    components: dict[str, Component],
    updates: dict[str, str],
) -> str:
    replacements: dict[str, str] = {}
    for component_id, new_version in updates.items():
        old_version = components[component_id].current
        previous = replacements.setdefault(old_version, new_version)
        if previous != new_version:
            raise UpdateError(
                f"ambiguous updates for shared version {old_version}: "
                f"{previous} and {new_version}"
            )

    all_values = list(iter_manifest_version_values(source_doc))
    component_values = list(iter_component_version_values(source_doc))
    managed_values = {
        component.current for component in components.values() if component.component_id in updates
    }
    for old_version, new_version in replacements.items():
        if old_version not in managed_values:
            raise UpdateError(f"refusing unmanaged replacement of {old_version}")
        old_literal = json.dumps(old_version)
        occurrences = source_text.count(old_literal)
        expected = all_values.count(old_version)
        component_occurrences = component_values.count(old_version)
        if expected != component_occurrences:
            raise UpdateError(
                f"version {old_version} is also used outside managed component fields"
            )
        if occurrences != expected or occurrences == 0:
            raise UpdateError(
                f"cannot safely replace {old_version}: "
                f"text occurrences={occurrences}, JSON values={expected}"
            )
        source_text = source_text.replace(old_literal, json.dumps(new_version))

    json.loads(source_text)
    return source_text


def merge(
    source_json: Path,
    report_paths: list[Path],
    *,
    output: Path,
    summary: Path,
) -> bool:
    source_text = source_json.read_text(encoding="utf-8")
    source_doc = json.loads(source_text)
    reports = [
        json.loads(report_path.read_text(encoding="utf-8"))
        for report_path in report_paths
    ]
    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    mismatched_reports = [
        str(report_paths[index])
        for index, report in enumerate(reports)
        if report.get("source_sha256") != source_sha256
    ]
    if mismatched_reports:
        raise UpdateError(
            "scan reports were generated from a different source.json: "
            + ", ".join(mismatched_reports)
        )
    components = {
        component.component_id: component
        for arch in SUPPORTED_ARCHES
        for component in collect_components(source_doc, arch)
    }
    updates = select_updates(source_doc, reports)
    updated_text = apply_updates_preserving_format(
        source_text, source_doc, components, updates
    )
    output.write_text(updated_text, encoding="utf-8")

    lines = ["## Component version updates", ""]
    if updates:
        lines.extend(
            [
                "| Component | Previous | Updated |",
                "|---|---:|---:|",
            ]
        )
        for component_id, new_version in sorted(updates.items()):
            component = components[component_id]
            lines.append(
                f"| `{component.name}` | `{component.current}` | `{new_version}` |"
            )
    else:
        lines.append("No newer builds were available in the currently pinned version families.")
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bool(updates)


def summarize(base: Path, updated: Path, output: Path) -> None:
    base_doc = json.loads(base.read_text(encoding="utf-8"))
    updated_doc = json.loads(updated.read_text(encoding="utf-8"))
    base_components = {
        (component.kind, component.name): component.current
        for arch in SUPPORTED_ARCHES
        for component in collect_components(base_doc, arch)
    }
    updated_components = {
        (component.kind, component.name): component.current
        for arch in SUPPORTED_ARCHES
        for component in collect_components(updated_doc, arch)
    }
    lines = [
        "## Component version updates",
        "",
        "| Component | Previous | Updated |",
        "|---|---:|---:|",
    ]
    changes = 0
    for key, old_version in sorted(base_components.items()):
        new_version = updated_components.get(key)
        if new_version and new_version != old_version:
            lines.append(f"| `{key[1]}` | `{old_version}` | `{new_version}` |")
            changes += 1
    if not changes:
        raise UpdateError("automation branch contains no managed component updates")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--source-json", type=Path, required=True)
    scan_parser.add_argument("--target-arch", choices=SUPPORTED_ARCHES, required=True)
    scan_parser.add_argument("--output", type=Path, required=True)
    scan_parser.add_argument(
        "--index-url",
        default=os.environ.get("MODELSDK_PYPI_INDEX_URL", DEFAULT_INDEX_URL),
    )
    scan_parser.add_argument(
        "--artifactory-url",
        default=os.environ.get("ARTIFACTORY_BASE_URL", DEFAULT_ARTIFACTORY_URL),
    )
    scan_parser.add_argument(
        "--max-candidates",
        type=int,
        default=0,
        help="Maximum newer builds to validate per component; 0 checks all",
    )

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--source-json", type=Path, required=True)
    merge_parser.add_argument("--report", type=Path, action="append", required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.add_argument("--summary", type=Path, required=True)
    merge_parser.add_argument("--github-output", type=Path)

    summary_parser = subparsers.add_parser("summarize")
    summary_parser.add_argument("--base", type=Path, required=True)
    summary_parser.add_argument("--updated", type=Path, required=True)
    summary_parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "scan":
            scan(
                args.source_json,
                target_arch=args.target_arch,
                output=args.output,
                index_url=args.index_url,
                artifactory_url=args.artifactory_url,
                max_candidates=args.max_candidates,
            )
        elif args.command == "merge":
            changed = merge(
                args.source_json,
                args.report,
                output=args.output,
                summary=args.summary,
            )
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as handle:
                    handle.write(f"changed={'true' if changed else 'false'}\n")
        elif args.command == "summarize":
            summarize(args.base, args.updated, args.output)
    except (OSError, ValueError, UpdateError) as exc:
        print(f"component update failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

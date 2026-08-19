#!/usr/bin/env python3
"""Pin a resolved LLiMa release artifact in a Model Compiler source manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
PACKAGE_NAME_RE = re.compile(r'"name"\s*:\s*"sima_lmm\[sdk\]"')


def _llima_packages(source: dict) -> list[dict]:
    package_lists: list[list] = []
    top_level = source.get("python-packages")
    if not isinstance(top_level, list):
        raise ValueError("source manifest must contain a python-packages list")
    package_lists.append(top_level)

    for value in source.values():
        if not isinstance(value, dict) or "python-packages" not in value:
            continue
        packages = value["python-packages"]
        if not isinstance(packages, list):
            raise ValueError("architecture python-packages must be a list")
        package_lists.append(packages)

    matches: list[dict] = []
    for packages in package_lists:
        package_matches = [
            item
            for item in packages
            if isinstance(item, dict) and item.get("name") == "sima_lmm[sdk]"
        ]
        if len(package_matches) > 1:
            raise ValueError(
                "each python-packages list may contain at most one sima_lmm[sdk] package"
            )
        matches.extend(package_matches)
    return matches


def _vulcan_object_spans(source_text: str) -> list[tuple[int, int, str]]:
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int, str]] = []
    for marker in PACKAGE_NAME_RE.finditer(source_text):
        object_offset = source_text.rfind("{", 0, marker.start())
        while object_offset >= 0:
            try:
                package, object_length = decoder.raw_decode(source_text[object_offset:])
            except json.JSONDecodeError:
                package = None
                object_length = 0
            object_end = object_offset + object_length
            if (
                isinstance(package, dict)
                and package.get("name") == "sima_lmm[sdk]"
                and object_end > marker.end()
            ):
                break
            object_offset = source_text.rfind("{", 0, object_offset)
        else:
            raise ValueError("could not locate a sima_lmm[sdk] package object")

        vulcan_offset = source_text.find('"vulcan"', marker.end(), object_end)
        if vulcan_offset < 0:
            raise ValueError("sima_lmm[sdk] package is missing its Vulcan entry")
        vulcan_object_offset = source_text.find("{", vulcan_offset, object_end)
        if vulcan_object_offset < 0:
            raise ValueError("could not locate the sima_lmm[sdk] Vulcan object")
        _, vulcan_object_length = decoder.raw_decode(source_text[vulcan_object_offset:])
        line_offset = source_text.rfind("\n", 0, vulcan_offset) + 1
        indentation = source_text[line_offset:vulcan_offset]
        if indentation.strip():
            raise ValueError("the sima_lmm[sdk] Vulcan entry must begin on its own line")
        spans.append(
            (
                vulcan_object_offset,
                vulcan_object_offset + vulcan_object_length,
                indentation,
            )
        )
    return spans


def pin_release(
    source_path: Path,
    provenance_path: Path,
    llima_version: str,
) -> str:
    if not VERSION_RE.fullmatch(llima_version):
        raise ValueError(
            f"LLiMa version must look like 0.4.0, got: {llima_version!r}"
        )

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    resolved = provenance.get("sima_lmm")
    if not isinstance(resolved, dict):
        raise ValueError("LLiMa provenance is missing sima_lmm")

    wheel_version = str(resolved.get("version", "")).strip()
    if wheel_version != llima_version:
        raise ValueError(
            f"Resolved LLiMa wheel version {wheel_version!r} does not match "
            f"requested release {llima_version!r}"
        )
    commit = str(resolved.get("resolved-commit", "")).strip()
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError(f"Resolved LLiMa commit is invalid: {commit!r}")
    expected_ref = f"v{llima_version}:{commit}"
    requested_ref = str(resolved.get("requested-ref", "")).strip()
    if requested_ref != expected_ref:
        raise ValueError(
            f"Resolved LLiMa requested ref {requested_ref!r} does not match "
            f"expected immutable ref {expected_ref!r}"
        )

    source_text = source_path.read_text(encoding="utf-8")
    source = json.loads(source_text)
    matches = _llima_packages(source)
    if not matches:
        raise ValueError("source manifest must contain a sima_lmm[sdk] package")
    for package in matches:
        vulcan = package.get("vulcan")
        if not isinstance(vulcan, dict):
            raise ValueError("each sima_lmm[sdk] package requires a Vulcan object")

    pinned_ref = f"v{llima_version}:{commit}"
    spans = _vulcan_object_spans(source_text)
    if len(spans) != len(matches):
        raise ValueError("could not map every sima_lmm[sdk] package to source text")
    updated = source_text
    for start, end, indentation in reversed(spans):
        replacement = (
            "{\n"
            f'{indentation}  "ref": {json.dumps(pinned_ref)}\n'
            f"{indentation}}}"
        )
        updated = updated[:start] + replacement + updated[end:]
    source_path.write_text(updated, encoding="utf-8")
    return pinned_ref


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", type=Path, required=True)
    parser.add_argument("--resolved-package-json", type=Path, required=True)
    parser.add_argument("--llima-version", required=True)
    args = parser.parse_args()

    try:
        pinned_ref = pin_release(
            args.source_json,
            args.resolved_package_json,
            args.llima_version,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    print(pinned_ref)


if __name__ == "__main__":
    main()

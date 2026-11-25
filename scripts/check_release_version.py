#!/usr/bin/env python3
"""Check that a Model Compiler release tag matches the manifest SDK version.

Vulcan promotes a tagged SquashFS only when the tag's first three numbers
equal the pack SDK version, which comes from sdk_version in source.json.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SDK_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
# Prerelease suffixes (v3.0.1.0-rc1) build and publish but never promote.
TAG_RE = re.compile(r"^v?([0-9]+\.[0-9]+\.[0-9]+)(?:\.[0-9]+)?(?:[-+][0-9A-Za-z.+-]+)?$")


def check_release_version(source_path: Path, tag: str) -> str:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    sdk_version = str(source.get("sdk_version", "")).strip()
    if not SDK_VERSION_RE.fullmatch(sdk_version):
        raise ValueError(
            f"sdk_version in {source_path} must look like 3.0.1, got: {sdk_version!r}"
        )

    match = TAG_RE.fullmatch(tag.strip())
    if match is None:
        raise ValueError(
            f"release tag must look like 3.0.1 or 3.0.1.0, got: {tag!r}"
        )
    if match.group(1) != sdk_version:
        raise ValueError(
            f"release tag {tag} does not match sdk_version {sdk_version}; "
            f"bump sdk_version on develop and promote it to the release branch first"
        )
    return sdk_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    try:
        sdk_version = check_release_version(args.source_json, args.tag)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    print(sdk_version)


if __name__ == "__main__":
    main()

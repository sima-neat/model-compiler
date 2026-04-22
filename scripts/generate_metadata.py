#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def human_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate metadata.json for sima-cli distribution from wheel artifacts."
    )
    p.add_argument("--artifacts-dir", required=True, help="Directory containing wheel files.")
    p.add_argument("--output", required=True, help="Path for generated metadata.json.")
    p.add_argument("--name", default="sima-neat-model-sdk")
    p.add_argument("--version", required=True)
    p.add_argument("--release", default="stable")
    p.add_argument(
        "--description",
        default="SiMa.ai NEAT Model SDK",
    )
    p.add_argument(
        "--host-os",
        default="linux",
        help="Host OS value for metadata platforms host entry (default: linux).",
    )
    p.add_argument(
        "--installer-script",
        default="install_modelsdk_wheels.sh",
        help="Installer script filename included in resources.",
    )
    p.add_argument(
        "--source-manifest",
        default="source.json",
        help="Source manifest filename included in resources when present.",
    )
    args = p.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        raise SystemExit(f"artifacts-dir does not exist: {artifacts_dir}")

    wheels = sorted([p for p in artifacts_dir.iterdir() if p.is_file() and p.suffix == ".whl"])
    if not wheels:
        raise SystemExit(f"No wheel files found in {artifacts_dir}")

    installer = artifacts_dir / args.installer_script
    if not installer.is_file():
        raise SystemExit(
            f"Installer script not found: {installer}. "
            f"Put it in artifacts-dir or override --installer-script."
        )

    resources = [w.name for w in wheels] + [installer.name]
    manifest = artifacts_dir / args.source_manifest
    if manifest.is_file():
        resources.append(manifest.name)
    checksums = {}
    total_download_bytes = 0
    for name in resources:
        f = artifacts_dir / name
        checksums[name] = sha256_file(f)
        total_download_bytes += f.stat().st_size

    metadata = {
        "name": args.name,
        "version": args.version,
        "release": args.release,
        "description": args.description,
        "platforms": [
            {
                "type": "host",
                "os": [args.host_os],
            },
            {"type": "palette"},
        ],
        "resources": resources,
        "resources-checksum": checksums,
        "size": {
            "download": human_mb(total_download_bytes),
            "install": human_mb(total_download_bytes),
        },
        "installation": {
            "script": f"bash ./{installer.name}",
            "post-message": "Successfully installed ModelSDK wheel bundle.",
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

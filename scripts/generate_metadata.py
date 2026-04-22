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
        description="Generate metadata.json for sima-cli distribution from bundle artifacts."
    )
    p.add_argument("--artifacts-dir", required=True, help="Directory containing bundle artifacts.")
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

    artifacts = sorted(
        [p for p in artifacts_dir.iterdir() if p.is_file() and p.suffix in {".whl", ".zip"}]
    )
    if not artifacts:
        raise SystemExit(f"No wheel or binary artifacts found in {artifacts_dir}")

    installer = artifacts_dir / args.installer_script
    if not installer.is_file():
        raise SystemExit(
            f"Installer script not found: {installer}. "
            f"Put it in artifacts-dir or override --installer-script."
        )

    resources = [a.name for a in artifacts] + [installer.name]
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
            "post-message": (
                "[bold green]Successfully installed ModelSDK.[/bold green]\n\n"
                "[bold]Virtual environment location:[/bold]\n"
                "The installer creates the venv at "
                "[green]/sdk-extensions/model-sdk/venv[/green] when writable, "
                "otherwise it falls back to [green]/sdk-add-on/model-sdk/venv[/green], "
                "or [green]~/sdk-extensions/model-sdk/venv[/green].\n\n"
                "[bold]Reload your shell environment:[/bold]\n"
                "The installer updates [green]~/.bashrc[/green] when it exists, "
                "otherwise [green]~/.bash_profile[/green]. Run "
                "[green]source ~/.bashrc[/green] or [green]source ~/.bash_profile[/green], "
                "or log out and log back in."
            ),
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

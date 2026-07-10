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
    p.add_argument("--name", default="sima-neat-model-compiler")
    p.add_argument("--version", required=True)
    p.add_argument("--release", default="stable")
    p.add_argument(
        "--description",
        default="SiMa.ai NEAT Model Compiler",
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
    p.add_argument(
        "--wheel-manifest",
        default="manifest.txt",
        help="Wheel manifest filename generated and included in resources.",
    )
    p.add_argument(
        "--offline-package",
        action="store_true",
        help="Generate metadata for an offline download package. The install script only prints instructions.",
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

    wheel_artifacts = [a for a in artifacts if a.suffix == ".whl"]
    if not wheel_artifacts:
        raise SystemExit(f"No wheel artifacts found in {artifacts_dir}")

    installer = artifacts_dir / args.installer_script
    if not installer.is_file():
        raise SystemExit(
            f"Installer script not found: {installer}. "
            f"Put it in artifacts-dir or override --installer-script."
        )

    wheel_manifest = artifacts_dir / args.wheel_manifest
    wheel_manifest.write_text(
        "".join(f"{a.name}\n" for a in wheel_artifacts),
        encoding="utf-8",
    )

    resources = [a.name for a in artifacts] + [wheel_manifest.name, installer.name]
    source_manifest = artifacts_dir / args.source_manifest
    if source_manifest.is_file():
        resources.append(source_manifest.name)
    checksums = {}
    total_download_bytes = 0
    for name in resources:
        f = artifacts_dir / name
        checksums[name] = sha256_file(f)
        total_download_bytes += f.stat().st_size

    install_script = f"bash ./{installer.name}"
    post_message = (
        "[bold green]Successfully installed Model Compiler.[/bold green]\n\n"
        "[bold]Virtual environment location:[/bold]\n"
        "The installer creates the venv at "
        "[green]/sdk-extensions/model-compiler[/green] when writable, "
        "otherwise it falls back to [green]/sdk-add-on/model-compiler[/green], "
        "or [green]~/sdk-extensions/model-compiler[/green].\n\n"
        "[bold]Reload your shell environment:[/bold]\n"
        "The installer updates [green]~/.bashrc[/green] when it exists, "
        "otherwise [green]~/.bash_profile[/green]. Run "
        "[green]source ~/.bashrc[/green] or [green]source ~/.bash_profile[/green], "
        "or log out and log back in. Then run [green]activate-model-compiler[/green] "
        "to activate the environment and [green]deactivate-model-compiler[/green] to leave it."
    )
    if args.offline_package:
        install_script = (
            "echo 'Model Compiler offline package downloaded. "
            "Copy the downloaded files to the target SDK workspace, then run: "
            "bash ./install_modelsdk_wheels.sh'"
        )
        post_message = (
            "[bold green]Successfully downloaded Model Compiler offline package.[/bold green]\n\n"
            "[bold]Install Model Compiler in an offline SDK:[/bold]\n"
            "Copy the downloaded files to the host workspace folder that is mounted into "
            "the SDK container as [green]/workspace[/green]. Open a terminal in the SDK "
            "container, change to that copied folder, then run "
            "[green]bash ./install_modelsdk_wheels.sh[/green].\n\n"
            "[bold]Virtual environment location:[/bold]\n"
            "The installer creates the venv at "
            "[green]/sdk-extensions/model-compiler[/green] when writable, "
            "otherwise it falls back to [green]/sdk-add-on/model-compiler[/green], "
            "or [green]~/sdk-extensions/model-compiler[/green].\n\n"
            "[bold]Reload your shell environment:[/bold]\n"
            "The installer updates [green]~/.bashrc[/green] when it exists, "
            "otherwise [green]~/.bash_profile[/green]. Run "
            "[green]source ~/.bashrc[/green] or [green]source ~/.bash_profile[/green], "
            "or log out and log back in. Then run [green]activate-model-compiler[/green] "
            "to activate the environment and [green]deactivate-model-compiler[/green] to leave it."
        )

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
            "install": "9 GB",
        },
        "installation": {
            "script": install_script,
            "post-message": post_message,
        },
    }
    if args.offline_package:
        metadata["offline"] = {
            "install-script": installer.name,
            "wheel-manifest": wheel_manifest.name,
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

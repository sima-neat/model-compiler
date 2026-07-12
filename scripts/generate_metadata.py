#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def human_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def binary_archive_names(source_manifest: Path) -> set[str]:
    if not source_manifest.is_file():
        return set()
    doc = json.loads(source_manifest.read_text(encoding="utf-8"))

    def names_from_items(items: object) -> set[str]:
        names = set()
        if not isinstance(items, list):
            return names
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip().strip("/")
            version = str(item.get("version", "")).strip()
            extension = str(item.get("extension", "")).strip()
            archive_type = str(item.get("archive-type", "zip")).strip() or "zip"
            if extension:
                archive_type = extension[1:] if extension.startswith(".") else extension
            if name and version:
                names.add(f"{name.rsplit('/', 1)[-1]}-{version}.{archive_type}")
        return names

    names = names_from_items(doc.get("binary-packages", []))
    for value in doc.values():
        if isinstance(value, dict):
            names.update(names_from_items(value.get("binary-packages", [])))
    return names


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
    p.add_argument(
        "--offline-archive-name",
        default="model-compiler-offline-package.zip",
        help="Archive filename to create for --offline-package.",
    )
    args = p.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_dir():
        raise SystemExit(f"artifacts-dir does not exist: {artifacts_dir}")

    archive_name = ""
    if args.offline_package:
        archive_name = args.offline_archive_name.strip()
        if not archive_name or "/" in archive_name or archive_name.startswith("."):
            raise SystemExit(f"Invalid offline archive name: {args.offline_archive_name!r}")
        if not archive_name.endswith(".zip"):
            raise SystemExit("offline archive name must end with .zip")

    source_manifest = artifacts_dir / args.source_manifest
    binary_names = binary_archive_names(source_manifest)

    artifacts = sorted(
        [
            p
            for p in artifacts_dir.iterdir()
            if p.is_file()
            and (p.suffix in {".whl", ".zip"} or p.name.endswith(".tar.gz"))
            and p.name != archive_name
        ]
    )
    if not artifacts:
        raise SystemExit(f"No wheel or binary artifacts found in {artifacts_dir}")

    package_artifacts = [
        a
        for a in artifacts
        if a.suffix == ".whl"
        or a.name.endswith(".tar.gz")
        or (a.suffix == ".zip" and a.name not in binary_names)
    ]
    if not package_artifacts:
        raise SystemExit(f"No wheel or source package artifacts found in {artifacts_dir}")

    installer = artifacts_dir / args.installer_script
    if not installer.is_file():
        raise SystemExit(
            f"Installer script not found: {installer}. "
            f"Put it in artifacts-dir or override --installer-script."
        )

    wheel_manifest = artifacts_dir / args.wheel_manifest
    wheel_manifest.write_text(
        "".join(f"{a.name}\n" for a in package_artifacts),
        encoding="utf-8",
    )

    resources = [a.name for a in artifacts] + [wheel_manifest.name, installer.name]
    if source_manifest.is_file():
        resources.append(source_manifest.name)

    archived_resources = []
    if args.offline_package:
        archive_path = artifacts_dir / archive_name
        archived_resources = resources[:]
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name in archived_resources:
                zf.write(artifacts_dir / name, arcname=name)
        for name in archived_resources:
            path = artifacts_dir / name
            if path.exists():
                path.unlink()
        resources = [archive_name]

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
            "Copy the downloaded zip to the target SDK workspace, unzip it, then run: "
            "bash ./install_modelsdk_wheels.sh --offline-package'"
        )
        post_message = (
            "[bold green]Successfully downloaded Model Compiler offline package.[/bold green]\n\n"
            "[bold]Install Model Compiler in an offline SDK:[/bold]\n"
            "Copy the downloaded zip file to the host workspace folder that is mounted into "
            "the SDK container as [green]/workspace[/green]. Unzip it, open a terminal in "
            "the SDK container, change to the extracted folder, then run "
            "[green]bash ./install_modelsdk_wheels.sh --offline-package[/green].\n\n"
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
            "archive": archive_name,
            "archive-contents": archived_resources,
        }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

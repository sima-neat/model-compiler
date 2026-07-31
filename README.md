# Model Compiler Bundle Builder

This repository builds a distributable Model Compiler bundle for `sima-cli`.

The bundle contains:
- curated Python wheels for the Model Compiler package set
- direct internal wheel dependencies required by those packages
- binary package artifacts such as the MLA toolchain
- an installer script for the target host
- generated `metadata.json` for `sima-cli`

Use this repository to build a repeatable Model Compiler installation for the
Neat SDK or an Ubuntu host, with a predictable package set and a self-contained
extension layout.

## Installation

Install and authenticate `sima-cli` first. See the
[sima-cli documentation](https://github.com/sima-neat/sima-cli) for setup
instructions.

Then install Model Compiler inside the Neat SDK or on an Ubuntu 22.04/24.04
host:

```bash
# amd64 host
sima-cli install -v 2.0.0 tools/model-compiler/amd64
# arm64 host
sima-cli install -v 2.1.2 tools/model-compiler/arm64
```

## Repository Layout

- [scripts/source.json](scripts/source.json): bundle manifest
- [scripts/build_modelsdk_bundle.sh](scripts/build_modelsdk_bundle.sh): end-to-end bundle builder
- [scripts/download_modelsdk_wheels.sh](scripts/download_modelsdk_wheels.sh): downloads Python and binary artifacts
- [scripts/install_modelsdk_wheels.sh](scripts/install_modelsdk_wheels.sh): installs the bundle on a target host
- [scripts/generate_metadata.py](scripts/generate_metadata.py): generates `metadata.json`
- [docs/generated/index.md](docs/generated/index.md): generated Model Compiler API reference entrypoint
- `dist/`: default output directory for built bundles

## API Reference

Generated API reference docs live under [docs/generated](docs/generated). Start
with [docs/generated/index.md](docs/generated/index.md), which links to the
generated AFE API pages.

## Manifest Format

[scripts/source.json](scripts/source.json) defines the bundle contents.

Example:

```json
{
  "sdk_version": "2.0.0",
  "python_version": "3.10",
  "system_dependencies": {
    "ubuntu": [
      "build-essential",
      "curl",
      "libllvm18",
      "libopenblas0-pthread"
    ]
  },
  "dependency_overrides": {
    "onnx": "1.17.0",
    "onnxruntime": "1.21.1",
    "protobuf": "4.25.7"
  },
  "python-packages": [
    { "name": "sima-frontend", "version": "2.0.0.dev0+master.371" }
  ],
  "binary-packages": [
    {
      "name": "mla/toolchain/mla-toolchain",
      "version": "v2.1.3560-develop.409",
      "extension": ".zip"
    }
  ]
}
```

Fields:
- `sdk_version`: used when constructing the bundle version string
- `python_version`: target interpreter version for the installed virtual environment
- `system_dependencies.ubuntu`: apt packages installed on the target host before Python and virtual environment setup
- `dependency_overrides`: exact versions to rewrite into downloaded wheel metadata when needed
- `python-packages`: top-level Python packages to include in the bundle; entries may include `file` to download a wheel from `sima-pypi/<package-name>/`, or `url` for a full direct wheel URL, when the wheel is not exposed by the configured Python index
- `binary-packages`: non-wheel artifacts fetched from Artifactory and installed into the Model Compiler virtual environment; the MLA toolchain derives its `x86` or `aarch64` archive suffix from the build target
- `aarch64`: optional architecture-specific overrides for fields that genuinely differ on ARM64; `dependency_overrides` entries are merged over the global map, so list only packages whose ARM64 pins differ

Native source builds triggered during installation, such as
`llama_cpp_python`, use the build backend's default parallelism. Set
`MODELSDK_BUILD_PARALLEL_LEVEL` to limit or override build parallelism on
resource-constrained machines.

### Automated component updates

The `Daily Component Update` workflow checks `scripts/source.json` every
day at 00:00 UTC. The current version is the update policy: for example,
`2.1.3.dev0+master.390` can advance only within
`2.1.3.dev0+master.*`, and `v2.1.3560-develop.409` can advance only within
`v2.1.3560-develop.*`. Changing a base version or channel remains a manual
manifest change.

The private macOS/ARM64 runner validates available artifacts and acts as the
authoritative scanner because Artifactory publishes matching component
versions for ARM64 and amd64. Changed manifests refresh the stable
`automation/component-updates` branch from the tested `develop` commit. The
ordinary Build workflow still packages and tests both architectures. A
successful Build run for that exact branch commit creates or updates one pull
request back to `develop`.

Manual dry runs are available through `workflow_dispatch`. Branch pushes use
the `NEAT_RELEASES_APP_ID` and `NEAT_RELEASES_APP_PRIVATE_KEY` secrets so the
push triggers the Build workflow. GitHub executes scheduled and
`workflow_run` workflows from the repository default branch, so both
automation workflow files must be present on `main` before unattended runs
and automatic PR creation become active.

## Building a Bundle

Before you build, configure `~/.netrc` with credentials for
`artifacts.eng.sima.ai`. The build downloads wheels and binary artifacts from
Artifactory, so it requires valid access tokens.

Example:

```netrc
machine artifacts.eng.sima.ai
  login <your-username-or-token-name>
  password <your-artifactory-access-token>
```

Restrict the file permissions when needed:

```bash
chmod 600 ~/.netrc
```

Default build:

```bash
./scripts/build_modelsdk_bundle.sh
```

Typical explicit build:

```bash
./scripts/build_modelsdk_bundle.sh \
  --source-json ./scripts/source.json \
  --output-dir ./dist \
  --index-url https://artifacts.eng.sima.ai/artifactory/api/pypi/sima-pypi-group/simple \
  --extra-index-url https://pypi.org/simple
```

Build a bundle for a specific architecture:

```bash
./scripts/build_modelsdk_bundle.sh --target-arch aarch64
```

By default, the metadata version comes from the exact git checkout. If `HEAD`
has a release tag such as `v1.0.0`, the generated `metadata.json` uses
`1.0.0`. Otherwise, it falls back to
`sdk_version.neat+branch.git-short-hash`. Pass `--bundle-version` to override
this behavior.

The LLiMa Vulcan entry uses the floating `develop` ref for development builds.
For a reproducible release bundle, set `ref` to an immutable value such as
`release-0.4:<commit>`. Generated metadata records the requested ref, resolved
commit, wheel version, and wheel filename.

The build creates a self-contained archive by default and performs these steps:
1. Read the package manifest from `source.json`.
2. Download every wheel in the target architecture's dependency closure.
3. Download binary package archives such as the MLA toolchain.
4. Copy the installer and source manifest into the output directory.
5. Generate `manifest.txt` with the bundled wheel filenames.
6. Generate the ZIP archive plus `metadata.json` and `metadata-offline.json`.

The release workflow builds the full dependency closure into one archive.
`metadata.json` downloads that archive, extracts it into a temporary directory,
runs the installer locally, and removes the extracted directory afterward.
`metadata-offline.json` references the same archive but provides manual
distribution instructions for transferring the ZIP to another environment and
running its included installer there. It is available from Linux, macOS, and
Windows hosts so the archive can be downloaded before transfer; the installer
inside the archive remains Linux-only.

Output files in `dist/` typically include:

- `model-compiler-<arch>.zip`
- `metadata.json`
- `metadata-offline.json`

## Testing a Local Bundle

Test a freshly built bundle from your local machine before you publish it.

From this repository:

```bash
cd dist
python3 -m http.server
```

Then install the bundle from an Ubuntu host or a Neat SDK environment:

```bash
sima-cli install -m http://<ip>:8000/metadata.json
```

Replace `<ip>` with the IP address of the machine that serves the `dist/`
directory.

This validates the Model Compiler bundle against a local metadata source.

## Authentication and Package Sources

The scripts download internal Python packages and binary artifacts from SiMa
Artifactory.

Python wheels:
- primary index: Artifactory
- fallback index: public PyPI via `--extra-index-url`

Binary packages:
- fetched from `https://artifacts.eng.sima.ai/artifactory/...`

If your environment requires authentication, configure Artifactory credentials
with `.netrc` or your shell environment before you run the scripts.

## Installing a Built Bundle

After you build the bundle, copy the architecture-specific ZIP to the target
Linux machine, extract it, and run the included installer. For example, for an
ARM64 target:

```bash
unzip -q model-compiler-arm64.zip -d model-compiler-arm64
cd model-compiler-arm64
bash ./install_modelsdk_wheels.sh
```

Use `model-compiler-amd64.zip` for an amd64 target. Alternatively, install
through `metadata.json` with `sima-cli`, which extracts the same archive into a
temporary directory and runs this installer automatically.

The installer performs these steps:
1. Read `source.json`.
2. Install required Ubuntu system packages from `system_dependencies.ubuntu`.
3. Find or install the required Python version, using `pyenv` when needed.
4. Read `manifest.txt` to identify the bundled Model Compiler wheels.
5. Create a Model Compiler virtual environment.
6. Install bundled binary packages into that virtual environment.
7. Install top-level package specs from `python-packages`, including extras such
   as `sima_lmm[sdk]`. It uses manifest-listed wheels as local `--find-links`
   inputs with `--no-index`.
8. Update shell startup files with the Model Compiler virtual environment
   `PATH`.
9. Leave the extracted archive available for reuse; remove it manually if it is
   no longer needed.

## Install Location

The installer creates the Model Compiler virtual environment in one of these
locations:

- `/sdk-extensions/model-compiler` if `/sdk-extensions` exists and is writable
- `/sdk-add-on/model-compiler` as a backward-compatible fallback
- `~/sdk-extensions/model-compiler` otherwise

Binary package contents, such as the MLA toolchain, are installed into the same
virtual environment under:
- `bin/`
- `include/`
- `lib/`

The downloaded MLA toolchain zip is sanitized during bundle creation so only
its `bin/` payload is preserved.

The installer also restores executable permissions for binaries copied into `model-compiler/bin`.

## Shell Environment Updates

The installer adds Model Compiler environment setup to one of these files:
- `~/.bashrc` when it exists, otherwise
- `~/.bash_profile`

It appends an idempotent block that exports:

```bash
PATH=<venv>/bin:$PATH
```

After installation, reload your shell:

```bash
source ~/.bashrc
```

or:

```bash
source ~/.bash_profile
```

You can also log out and back in.

## Post-Install Smoke Tests

After installing and activating the Model Compiler extension, run the fast smoke test:

```bash
activate-model-compiler
python /path/to/model-sdk/scripts/smoke_test_modelsdk.py --tier basic
```

The `basic` tier is intended for every CI/CD extension-install job. It checks:
- the active Python is the Model Compiler venv
- Model Compiler `bin/` is on `PATH`
- core MLA tools such as `mla-nm`, `mla-size`, `mla-readelf`, and `mla-isim` are runnable
- `afe-replay-compile`, `onnxsim`, and `llima-compile` entry points are runnable
- required Python modules including `afe`, `onnx`, `torch`, `sima_lmm`, `gguf`, `llama_cpp`, and `safetensors` are importable

Heavier tiers are available for scheduled or pre-release jobs:

```bash
# Export a synthetic ResNet50 ONNX model with torchvision.
python scripts/smoke_test_modelsdk.py --tier resnet-export

# Export or reuse ResNet50, audit it, simplify it, and run quantize-only.
python scripts/smoke_test_modelsdk.py --tier resnet-quantize

# Same as resnet-quantize, but also runs the compile step.
python scripts/smoke_test_modelsdk.py --tier resnet-compile

# Download YOLOv8n ONNX, simplify/audit it, and run quantize+compile.
python scripts/smoke_test_modelsdk.py --tier yolo

# Run all long-form smoke cases and print a final result summary.
python scripts/smoke_test_modelsdk.py --tier all

# Reuse a cached YOLO ONNX model and optionally verify model-to-pipeline references.
python scripts/smoke_test_modelsdk.py \
  --tier yolo \
  --yolo-model /path/to/yolo.onnx \
  --model-to-pipeline-dir /path/to/tool-model-to-pipeline
```

The ONNX operator audit is informational by default. Add `--strict-audit` when
you want the smoke test to fail on unknown or unsupported operators in the
bundled support database.

When `--work-dir` is omitted, model tiers create temporary work directories
under `~/tmp`. If `--work-dir` is supplied, model tiers create a fresh per-run
subdirectory under that path for intermediate and compiled artifacts. This
avoids collisions with stale files from previous smoke-test runs.
If an explicit `--work-dir` exists but is not writable, the runner falls back
to a per-user sibling such as `~/tmp/modelsdk-smoke-$USER`.

The `all`, `resnet-compile`, and `yolo` tiers also collect lightweight
compiled-artifact metrics. They report package counts/sizes and run MLA
toolchain checks such as `mla-size` and `mla-readelf` on ELF files packaged in
the generated MPK archive when those files are present.

Use `activate-model-compiler` to enter the installed environment and
`deactivate-model-compiler` to leave it.

On ARM systems, activation enables the JAX compilation path with the NEON CPU
ISA by default. Use `--no-jax` as a compatibility or debugging fallback:

```bash
activate-model-compiler --no-jax
```

This explicitly disables the JAX compilation path for the activation while
preserving unrelated `XLA_FLAGS`. Deactivation restores the environment values
that were present before activation.

## Cleanup Behavior

After a successful install, the installer removes downloaded bundle resources
from the bundle directory, including:
- manifest-listed wheel files
- binary package archives such as the MLA toolchain zip
- extracted binary package directories if present

It keeps installer and metadata files such as:
- `install_modelsdk_wheels.sh`
- `source.json`
- `manifest.txt`
- `metadata.json`

## Notes and Troubleshooting

- If a sample or test script fails with missing Python modules, confirm that it
  uses the installed Model Compiler virtual environment and not a separate local
  `.env`.
- If a compiled package fails at runtime with missing shared libraries, check that:
  - the required Ubuntu packages from `system_dependencies.ubuntu` were installed
- If GitHub push fails from an automated environment, verify that the git remote has usable credentials.
- If a wheel is missing from Artifactory, provide `--extra-index-url` so the
  build can fall back to public PyPI for Python packages.

## Regenerating a Package

The archive contains the installer and every dependency, so regenerate it and
its matching metadata together with `build_modelsdk_bundle.sh` rather than
editing metadata independently.

## Status

This repository currently focuses on:
- curated host-side Model Compiler installation
- binary package inclusion for the MLA toolchain
- `sima-cli`-style bundle metadata generation

If you add more extensions later, use the existing extension-style install root
under `sdk-extensions/`.

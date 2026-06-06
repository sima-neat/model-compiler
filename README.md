# ModelSDK Bundle Builder

This repository builds a distributable ModelSDK bundle for `sima-cli`.

The bundle contains:
- curated Python wheels for the ModelSDK package set
- direct internal wheel dependencies needed by those packages
- binary package artifacts such as the MLA toolchain
- an installer script for the target host
- generated `metadata.json` for `sima-cli`

The main goal is to reproduce a working ModelSDK installation outside the container with a predictable package set and a self-contained extension layout.

## Installation

First install and authenticate `sima-cli`. See the
[sima-cli documentation](https://docs.sima.ai/pages/sima_cli/main.html) for setup instructions.

Then install ModelSDK inside the Neat SDK or on an Ubuntu 22.04/24.04 host with:

```bash
sima-cli install -v 2.0.0 sdk-extensions/model
```

## Repository Layout

- [scripts/source.json](scripts/source.json): bundle manifest
- [scripts/build_modelsdk_bundle.sh](scripts/build_modelsdk_bundle.sh): end-to-end bundle builder
- [scripts/download_modelsdk_wheels.sh](scripts/download_modelsdk_wheels.sh): downloads Python and binary artifacts
- [scripts/install_modelsdk_wheels.sh](scripts/install_modelsdk_wheels.sh): installs the bundle on a target host
- [scripts/generate_metadata.py](scripts/generate_metadata.py): generates `metadata.json`
- [docs/generated/index.md](docs/generated/index.md): generated ModelSDK API reference entrypoint
- `dist/`: default output directory for built bundles

## API Reference

Generated API reference docs are available under [docs/generated](docs/generated).
Start with [docs/generated/index.md](docs/generated/index.md), which links to the generated AFE API pages.

## Manifest Format

The bundle is driven by [scripts/source.json](scripts/source.json).

Example:

```json
{
  "sdk_version": "2.0.0",
  "python_version": "3.10",
  "system_dependencies": {
    "ubuntu": [
      "build-essential",
      "curl",
      "libllvm14",
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
      "name": "toolchain/mla/mla-toolchain",
      "version": "v2.1.3158-Edgematic-release-2.0.0.2-ubuntu",
      "extension": ".zip"
    }
  ]
}
```

Fields:
- `sdk_version`: used when constructing the bundle version string
- `python_version`: target interpreter version for the installed venv
- `system_dependencies.ubuntu`: apt packages installed on the target host before Python/venv setup
- `dependency_overrides`: exact versions to rewrite into downloaded wheel metadata when needed
- `python-packages`: top-level Python packages to include in the bundle
- `binary-packages`: non-wheel artifacts fetched from Artifactory and installed into the ModelSDK venv

## Building a Bundle

Before building, configure `~/.netrc` with credentials for `artifacts.eng.sima.ai`. The bundle build downloads internal wheels and binary artifacts from Artifactory, so valid access tokens are required.

Example:

```netrc
machine artifacts.eng.sima.ai
  login <your-username-or-token-name>
  password <your-artifactory-access-token>
```

Restrict the file permissions if needed:

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

By default, the metadata version is derived from the exact git checkout. If `HEAD` has a release tag like `v1.0.0`, the generated `metadata.json` uses `1.0.0`; otherwise it falls back to `sdk_version.neat+branch.git-short-hash`. Passing `--bundle-version` overrides this behavior.

What the build does:
1. Reads the package manifest from `source.json`
2. Downloads one wheel per requested Python package
3. Downloads direct internal wheel dependencies referenced by those wheels
4. Downloads binary package archives such as the MLA toolchain
5. Copies the installer and source manifest into the output directory
6. Generates `manifest.txt` with the bundled wheel filenames
7. Generates `metadata.json`

Output files in `dist/` typically include:
- `*.whl`
- `*.zip`
- `manifest.txt`
- `install_modelsdk_wheels.sh`
- `source.json`
- `metadata.json`

## Testing a Local Bundle

You can test a freshly built bundle directly from your local machine without publishing it anywhere first.

From this repository:

```bash
cd dist
python3 -m http.server
```

Then, from either an Ubuntu host or an eLxr SDK environment, install the bundle with `sima-cli`:

```bash
sima-cli install -m http://<ip>:8000/metadata.json
```

Replace `<ip>` with the IP address of the machine serving the `dist/` directory.

This lets you validate local ModelSDK bundle changes end-to-end using a local metadata source.

## Authentication and Package Sources

The scripts expect internal Python packages and binary artifacts to come from SiMa Artifactory.

Python wheels:
- primary index: Artifactory
- fallback index: public PyPI via `--extra-index-url`

Binary packages:
- fetched from `https://artifacts.eng.sima.ai/artifactory/...`

If your environment requires authentication, make sure your Artifactory credentials are already configured, typically via `.netrc` or your shell environment.

## Installing a Built Bundle

After the bundle has been produced, copy the contents of `dist/` to the target machine and run:

```bash
bash ./install_modelsdk_wheels.sh
```

The installer will:
1. Read `source.json`
2. Install required Ubuntu system packages from `system_dependencies.ubuntu`
3. Find or install the required Python version, using `pyenv` if necessary
4. Read `manifest.txt` to identify the bundled ModelSDK wheels
5. Create a ModelSDK virtual environment
6. Install bundled binary packages into that venv
7. Install top-level package specs from `python-packages` (including extras like `sima_lmm[sdk]`), using only manifest-listed wheels as local `--find-links` inputs and PyPI as fallback when needed
8. Update shell startup files with the ModelSDK venv `PATH`
9. Remove downloaded bundle payloads after successful installation

## Install Location

The installer creates the ModelSDK venv in one of these locations:

- `/sdk-extensions/model-sdk` if `/sdk-extensions` exists and is writable
- `/sdk-add-on/model-sdk` as a backward-compatible fallback
- `~/sdk-extensions/model-sdk` otherwise

Binary package contents such as the MLA toolchain are installed into that same venv under:
- `bin/`
- `include/`
- `lib/`

The installer also restores executable permissions for binaries copied into `model-sdk/bin`.

## Shell Environment Updates

The installer adds ModelSDK environment setup to:
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

Logging out and back in works too.

## Cleanup Behavior

On successful install, the installer removes downloaded bundle resources from the bundle directory, including:
- manifest-listed wheel files
- binary package archives such as the MLA toolchain zip
- extracted binary package directories if present

It keeps the installer and metadata files such as:
- `install_modelsdk_wheels.sh`
- `source.json`
- `manifest.txt`
- `metadata.json`

## Notes and Troubleshooting

- If a sample or test script fails with missing Python modules, first confirm it is using the installed ModelSDK venv and not a separate local `.env`.
- If a compiled package fails at runtime with missing shared libraries, check that:
  - the required Ubuntu packages from `system_dependencies.ubuntu` were installed
- If GitHub push fails from an automated environment, verify that the git remote has usable credentials.
- If a wheel is missing from Artifactory, the build flow can fall back to public PyPI for Python packages when `--extra-index-url` is provided.

## Regenerating Metadata Only

If you already have a populated bundle directory and only want to regenerate `metadata.json`:

```bash
python3 ./scripts/generate_metadata.py \
  --artifacts-dir ./dist \
  --output ./dist/metadata.json \
  --version 2.0.0.neat+local
```

## Status

This repository currently focuses on:
- curated host-side ModelSDK installation
- binary package inclusion for the MLA toolchain
- `sima-cli`-style bundle metadata generation

If you extend the repo with more add-ons later, the current layout is already set up to support an extension-style install root under `sdk-extensions/`.

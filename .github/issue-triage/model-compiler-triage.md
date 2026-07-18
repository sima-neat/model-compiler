# Model Compiler Issue Triage

Use this guidance when triaging issues in `sima-neat/model-compiler`.

## Areas

- `install`: Model Compiler package installation, virtual environment activation, `activate-model-compiler`, or missing Python modules.
- `package-bundle`: Package archive generation, download, zip extraction, local wheel resolution, or restricted-network installation.
- `build-ci`: GitHub Actions build, package publication, runner architecture, Artifactory download, or Vulcan/S3 publication failures.
- `dependencies`: pip resolver failures, package pin conflicts, missing wheels for Ubuntu 24.04, amd64, or arm64.
- `smoke-test`: `scripts/smoke_test_modelsdk.py`, post-install validation, environment sourcing, or basic import/CLI checks.
- `model-surgery`: ONNX graph edits, unsupported operators, shape/staticification, or compatibility checks before compile.
- `quantize-compile`: quantization, calibration, compile, AFE/frontend, target device selection, or generated artifacts.
- `documentation`: install docs, package docs, examples, or missing instructions.
- `unknown`: not enough evidence to route.

## Required Triage Behavior

- Keep comments concise and customer-facing.
- Do not claim a root cause unless the issue includes strong evidence.
- Ask only for missing details that would unblock investigation.
- Prefer `needs_human_review: true` for reports involving proprietary models, credentials, private artifacts, or security-sensitive deployment details.
- Use labels only from `config.json`.

## Installation Issues

For install or activation failures, ask for:

- Host OS and version.
- CPU architecture, from `uname -m`.
- Whether installation is running on the host or inside the SDK container.
- Exact package target, for example `model-compiler/amd64` or `model-compiler/arm64`.
- Full install command and the first failing error block.
- Python version and virtual environment path, if visible.

Likely cross-reference repositories:

- `sima-neat/sima-cli` when `sima-cli neat install` behavior, package download, or metadata execution is involved.
- `sima-neat/sdk` when installation depends on SDK container layout or `/sdk-extensions`.

## Package Bundle Issues

For package bundle reports, determine whether the issue is about package creation, package download, or installation.

Ask for:

- Package target and branch/tag used with `sima-cli neat install`.
- Whether the generated ZIP was downloaded and extracted locally.
- The exact `install_modelsdk_wheels.sh` command.
- Any pip output showing unexpected network access during installation.
- A directory listing of the package contents when local wheel resolution fails.

Treat unexpected network resolution during installation as actionable when the report includes the command and pip output.

## Build and CI Issues

For CI failures, ask for or cite:

- GitHub Actions run URL and failed job name.
- Branch/tag being built.
- Runner architecture (`amd64` or `arm64`) and OS when visible.
- Whether the failure happened during bundle build, dependency closure, metadata generation, package test, or publish.

Request extended analysis only when the issue includes a concrete workflow URL or log excerpt.

## Dependency Resolver Issues

For pip conflicts, ask for:

- Conflicting packages and versions from the resolver output.
- Whether the conflict happened during installation or wheel download.
- Platform and Python version.

Common actionable cases:

- Missing public wheels for Ubuntu 24.04, amd64, or arm64.
- Internal package pins that conflict with public dependency pins.
- Source-only dependencies that need to be prebuilt into the package archive.

## Model Surgery and Compile Issues

For model conversion, quantization, or compile failures, ask for:

- Model format and source, or a minimal reproducible model if the model cannot be shared.
- Target device, for example `modalix` or `davinci`.
- Input names, shapes, output names, dtype/calibration settings, and exact command.
- Relevant compiler, AFE, or quantization logs.
- Whether the model was audited with `skills/model_surgery/scripts/model_surgery_guard.py`.

Use the repository skills as context:

- `skills/model_surgery/SKILL.md` for unsupported operators, graph rewrites, and ONNX compatibility.
- `skills/quantize_compile/SKILL.md` for standard quantize and compile workflow issues.

## Suggested Public Comment Shape

Use 2-4 short paragraphs:

1. Acknowledge what appears to be failing and the likely area.
2. State whether the report is actionable or what evidence is missing.
3. Ask for the smallest useful set of additional details.
4. Mention if the issue appears to need human review because it involves private models, credentials, or environment-specific infrastructure.

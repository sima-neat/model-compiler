---
name: sima-model-compiler-issue-triage
description: Use when triaging model-compiler GitHub issues, including install failures, offline package reports, CI/package publishing failures, dependency conflicts, smoke test failures, model surgery reports, and quantize/compile problems.
---

# Model Compiler Issue Triage

## Purpose

Use this skill to classify model-compiler issues, identify the minimum missing evidence, and route reports to the right investigation path without over-claiming a root cause.

## Use When

- A GitHub issue or support report concerns model-compiler installation or activation.
- Offline packages fail to build, download, extract, or install without network access.
- GitHub Actions packaging, smoke tests, or publication fail.
- pip dependency resolution fails for the model compiler package.
- Quantization, model surgery, or compile reports need first-pass triage.

## Workflow

1. Identify the area: install, offline-package, build-ci, dependencies, smoke-test, model-surgery, quantize-compile, documentation, or unknown.
2. Extract hard evidence from the report: commands, package target, architecture, Python version, logs, workflow links, and whether the run is online or offline.
3. Determine whether the report is actionable:
   - Actionable: includes exact command and failing error block.
   - Needs repro details: missing command, environment, package target, or logs.
   - Needs human review: includes private model details, credentials, proprietary artifacts, or infrastructure-specific access.
4. Ask only for missing information that materially unblocks investigation.
5. Do not state a root cause unless the logs directly support it.

## Required Evidence by Area

### Install

Ask for:
- Host OS and version.
- `uname -m`.
- Whether the install ran on the host or inside the SDK container.
- Exact `sima-cli neat install` target.
- Full failing error block.

### Offline Package

Ask for:
- Offline package target and branch/tag.
- Whether the offline zip was downloaded and extracted.
- Exact `install_modelsdk_wheels.sh` command.
- Whether `--offline-package` was used.
- pip output if network access happened during an offline install.

### Build or Publish CI

Ask for:
- GitHub Actions run URL.
- Failed job name.
- Branch/tag.
- Architecture.
- Step where the failure occurred: online build, offline closure, metadata, package test, or publish.

### Dependency Conflict

Ask for:
- Conflicting package/version lines from pip.
- Python version.
- Platform and architecture.
- Online vs offline install path.

### Model Surgery or Compile

Ask for:
- Model format and a shareable repro model or minimal repro.
- Target device.
- Input/output names and shapes.
- Quantization/calibration settings.
- Exact command and compiler or AFE logs.

## Related Skills

- Use `skills/model_surgery/SKILL.md` when the issue involves unsupported ONNX operators, graph rewrites, or model compatibility.
- Use `skills/quantize_compile/SKILL.md` when the issue involves standard quantize/compile commands or generated artifacts.

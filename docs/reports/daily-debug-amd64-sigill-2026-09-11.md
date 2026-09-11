# amd64 BF16 diagnosis: unsupported instruction in ML kernels

The `daily-debug` branch starts at failed daily commit
`f1a9e27dbaf8d8cbbd329ba5bdc44a9a9a89f6a4`. It reuses the exact amd64 package
artifact from run 34627171277 rather than rebuilding or resolving dependencies.
Normal package/example publication is excluded for this diagnostic branch.

## Confirmed on ll2

An isolated Ubuntu 24.04 container on ll2 (Intel Core i9-13900HK, no AVX-512
CPU flags) ran one INT8 control and three BF16 attempts with one exported and
simplified ONNX file. INT8 passed in 84.6 seconds. BF16 failed in 125.5,
127.1, and 93.6 seconds. The repeated child process failures were SIGILL
(return code -4), reported by AFE as failure creating `ofm_chk.mlc`.

Package ZIP SHA-256:
`791f6907a0d40b348713b9c27b87425b0ef207647c0cb355b21471015b4e1bff`.

Versions: AFE develop.2270, MLC develop.1102, ML kernels develop.261,
MLA toolchain v3.0.0-3609-develop.453. Full freeze and model checksums are in
`debug-evidence/ll2/`. The container was limited to four CPUs and 16 GB RAM.
GDB was installed in the disposable container after the initial reproduction;
the first failures preceded that installation.

## Exact fault

Captured the check-file generator command and its inputs, then replayed it
under GDB. The fault is in the helper distributed by `sima-ml-kernels`:

```text
ml_kernels/np_operators_helpers.cpython-312-x86_64-linux-gnu.so
calculate_zpp(scale=992, ...) at src/ml_kernels/np_operators_helpers.cpp:103
zpp_multiply_add(...) at src/ml_kernels/np_operators_helpers.cpp:276
=> vcvttsd2usi %xmm0,%rcx
```

`VCVTTSD2USI` requires AVX-512F in this EVEX instruction form; ll2 does not
advertise that CPU feature. References: Intel's instruction-set manual,
https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-2c-manual.pdf,
and LLVM's instruction definitions,
https://llvm.googlesource.com/llvm-project/+/refs/heads/main/llvm/lib/Target/X86/X86InstrAVX512.td.

## Minimal reproducer

In the installed package environment on ll2:

```sh
python -c 'from ml_kernels.np_operators_helpers import zpp_multiply_add; zpp_multiply_add(1.0, 1.0, 1.0)'
```

This exits with status 132 (SIGILL) without a model, AFE compilation, or an MLA
device. GDB on this minimal call confirms the identical faulting instruction
at `calculate_zpp(scale=1, ...)`, source line 103. See
`debug-evidence/ll2/minimal-gdb.log` and `ofm-gdb.log`.

This establishes a CPU compatibility defect in the shipped helper on ll2.
The previous GitHub pass/fail alternation may depend on runner CPU features;
those old jobs did not capture sufficient CPU evidence to prove that yet.
The diagnostic GitHub run is https://github.com/sima-neat/model-compiler/actions/runs/34630580011.

## Suggested upstream fix and validation

Inspect the helper's build flags and generated code. Ship a build compatible
with the supported x86 baseline, or use runtime CPU dispatch with a portable
fallback before entering an AVX-512 implementation. Do not mask SIGILL with
retries or treat the generic AFE error as an NFS/artifact-path problem.

Validate the minimal call and full BF16 compile on a non-AVX-512 host as well
as an AVX-512-capable host; retain INT8 and ARM64 coverage. Improve AFE's error
reporting to include the failed child command and signal.

The full temporary generator inputs remain on ll2 under
`/home/jim/model-compiler-daily-debug/ll2-results/bf16-3-subprocesses-inputs`.
They are generated test intermediates, not customer models. The isolated
installed environment is retained as local image
`model-compiler:daily-debug-installed`. No runtime fix has been applied.

## Older-helper control on the same ll2 CPU

The pre-existing `model-compiler:local` image reports
`sima-ml-kernels 2.1.3.dev0+develop.246`. The identical minimal call above
returns `2.0` and exits zero in that image on ll2. The new installed image
with `3.0.0.dev0+develop.261` exits 132. This is a useful same-hardware
compatibility control, not a claim that the old image is the exact main-branch
2.1.3 package from the earlier CI run.

## GitHub fixed-artifact results

Run 34630580011 completed: INT8 passed (177.5 s); all three BF16 attempts
failed (197.7, 198.8, 197.4 s). All three check-file subprocesses exited -4
(SIGILL). The VM reports AMD EPYC 9V74 but does **not** expose `avx512f` in
its CPU flags. Capability must be checked from the flags, not the CPU name.

The ZIP SHA-256 matches ll2 exactly. Both raw and simplified ONNX files also
match across hosts:

- resnet50.onnx: `ab576a5df81842f864f4a29adb47a1f07111e2e49912f16fc02665c26c5d5c6a`
- resnet50.sim.onnx: `292d10f97472efc4a830c060c3a44f772b4753ce3e5f4258c8c62f63c93b3a72`

See `debug-evidence/github/` for host flags, frozen packages, subprocess
records and results. Full GitHub diagnostic artifact:
https://github.com/sima-neat/model-compiler/actions/runs/34630580011/artifacts/10276791348.

Across these two controlled hosts: INT8 passed on both; BF16 failed 6/6.
The precise GDB instruction/source attribution was obtained on ll2. The
GitHub run independently confirms the same generator SIGILL, absent CPU
feature, package bytes and model bytes. Earlier passing GitHub runner CPU
flags remain unknown, so CPU variation as the explanation for those older
passes is strongly supported but not directly verified.

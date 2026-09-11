#!/usr/bin/env python3
"""Repeat compiles using one fixed ONNX file and retain diagnostic evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--attempts', type=int, default=3)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)

def run(command, name, env=None):
    start = time.monotonic()
    with (out / (name + '.log')).open('w') as log:
        result = subprocess.run(command, cwd=root, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=1800)
    record = {'case': name, 'returncode': result.returncode,
              'seconds': round(time.monotonic() - start, 1)}
    with (out / 'results.jsonl').open('a') as output:
        output.write(json.dumps(record) + '\n')
    print(json.dumps(record), flush=True)
    return result.returncode

run([sys.executable, '-m', 'pip', 'freeze'], 'packages')
run(['bash', '-c', 'uname -a; lscpu; free -h; df -h; ulimit -a'], 'host')
with (out / 'selected-environment.json').open('w') as output:
    json.dump({k: os.environ.get(k) for k in ['PATH', 'VIRTUAL_ENV', 'XLA_FLAGS',
        'SIMA_MLA_COMPILE_USE_JAX', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS']}, output, indent=2)
# Use the production model generator without importing its main entry point.
sys.path.insert(0, str(root / 'scripts'))
import smoke_test_modelsdk as smoke
model = out / 'resnet50.onnx'
smoke.write_resnet50_onnx(model)
fixed = out / 'resnet50.sim.onnx'
if run(['onnxsim', str(model), str(fixed)], 'simplify'):
    raise SystemExit('ONNX simplification failed')
(out / 'model-sha256.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (model, fixed)}, indent=2))
env = dict(os.environ)
env['PYTHONPATH'] = str(Path(__file__).parent) + os.pathsep + env.get('PYTHONPATH', '')
failed = False
for case in ['int8-control'] + [f'bf16-{i}' for i in range(1, args.attempts + 1)]:
    env['MODELSDK_DEBUG_SUBPROCESSES'] = str(out / (case + '-subprocesses.jsonl'))
    command = [sys.executable, str(root / 'skills/quantize_compile/scripts/quantize_compile.py'),
        '--model_path', str(fixed), '--model_format', 'onnx', '--model_layout', 'NCHW',
        '--input_names', 'input', '--input_shapes', '1,3,224,224', '--output_names', 'output',
        '--device', 'modalix', '--build_dir', str(out / case)]
    if case.startswith('bf16'):
        command += ['--bf16-activations', '--bf16-weights']
    failed |= bool(run(command, case, env))
raise SystemExit(1 if failed else 0)

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/download_modelsdk_wheels.sh'


class DocoptResolverWheelTests(unittest.TestCase):
    def run_build(self, filenames, exit_code=0):
        source = SCRIPT.read_text()
        functions = []
        for name in ('collect_wheels', 'build_docopt_resolver_wheel'):
            start = source.index(name + '() {\n')
            end = source.index('\n}\n', start) + 3
            functions.append(source[start:end])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'output'
            output.mkdir()
            fake = root / 'python3'
            fake.write_text('''#!/bin/bash
while [[ $# -gt 0 ]]; do
  if [[ "$1" == --wheel-dir ]]; then dest="$2"; shift; fi
  shift
done
for name in $FAKE_WHEELS; do touch "$dest/$name"; done
exit "$FAKE_EXIT"
''')
            fake.chmod(0o755)
            env = dict(os.environ, TMPDIR=str(root), PATH=f'{root}:{os.environ["PATH"]}',
                       FAKE_WHEELS=' '.join(filenames), FAKE_EXIT=str(exit_code))
            harness = '\n'.join(functions) + '''
set -eu
register_temp_dir() { :; }
OUTPUT_DIR="$1"
PIP_INDEX_ARGS=(--index-url https://example.invalid/simple)
build_docopt_resolver_wheel
'''
            result = subprocess.run(['bash', '-c', harness, 'test', str(output)],
                                    env=env, capture_output=True, text=True)
            return result, [p.name for p in output.iterdir()]

    def test_portable_wheel_is_staged(self):
        for tag in ('py3', 'py2.py3'):
            with self.subTest(tag=tag):
                name = f'docopt-0.6.2-{tag}-none-any.whl'
                result, staged = self.run_build([name])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(staged, [name])

    def test_invalid_outputs_are_not_staged(self):
        for names in ([], ['docopt-0.6.2-cp312-cp312-macosx_11_0_arm64.whl'],
                      ['docopt-0.6.3-py3-none-any.whl'],
                      ['docopt-0.6.2-py3-none-any.whl', 'extra-1-py3-none-any.whl']):
            with self.subTest(names=names):
                result, staged = self.run_build(names)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(staged, [])

    def test_failed_build_is_not_staged(self):
        result, staged = self.run_build(['docopt-0.6.2-py3-none-any.whl'], exit_code=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(staged, [])

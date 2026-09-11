"""Opt-in subprocess diagnostics for the daily-debug branch only."""
import json
import os
import subprocess
import shutil
from pathlib import Path
import time

_original = subprocess.Popen.communicate


def communicate(self, *args, **kwargs):
    result = _original(self, *args, **kwargs)
    path = os.environ.get('MODELSDK_DEBUG_SUBPROCESSES')
    if path:
        def decode(value):
            if isinstance(value, bytes):
                value = value.decode('utf-8', errors='replace')
            return value[-200000:] if isinstance(value, str) else value
        record = {'time': time.time(), 'pid': self.pid, 'args': self.args,
                  'returncode': self.returncode, 'stdout': decode(result[0]),
                  'stderr': decode(result[1])}
        if self.returncode and isinstance(self.args, list) and '--in_config_path' in self.args:
            source = Path(self.args[self.args.index('--in_config_path') + 1]).parent.parent
            destination = Path(path).with_suffix('').with_name(Path(path).stem + '-inputs')
            shutil.copytree(source, destination, dirs_exist_ok=True)
            if os.environ.get('MODELSDK_DEBUG_GDB') == '1' and shutil.which('gdb'):
                command = ['gdb', '--batch', '-ex', 'set pagination off', '-ex', 'run',
                           '-ex', 'bt', '-ex', 'x/12i $pc-16', '-ex', 'info registers',
                           '-ex', 'info sharedlibrary', '--args'] + self.args
                with open(path + '.gdb.log', 'w') as output:
                    subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=300)
        try:
            with open(path, 'a') as output:
                output.write(json.dumps(record, default=str) + '\n')
        except OSError:
            pass
    return result

subprocess.Popen.communicate = communicate

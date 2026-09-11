"""Opt-in subprocess diagnostics for the daily-debug branch only."""
import json
import os
import subprocess
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
        try:
            with open(path, 'a') as output:
                output.write(json.dumps(record, default=str) + '\n')
        except OSError:
            pass
    return result

subprocess.Popen.communicate = communicate

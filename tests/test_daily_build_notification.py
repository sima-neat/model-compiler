import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


N = load('daily_build_notification')


class NotificationTests(unittest.TestCase):
    def run_data(self, conclusion):
        return {'head_branch': 'daily', 'status': 'completed', 'repository': {'full_name': 'sima-neat/model-compiler'},
                'id': 123, 'run_number': 4, 'head_sha': 'a'*40, 'run_attempt': 2, 'conclusion': conclusion}

    def test_success_contains_build_summary_link(self):
        payload = N.compose(self.run_data('success'), [], 'C123')
        self.assertEqual(payload['channel'], 'C123')
        self.assertIn('succeeded', payload['text'])
        self.assertIn('123#summary', json.dumps(payload))

    def test_failure_and_cancellation_report_jobs_without_mentions(self):
        for conclusion in ('failure', 'cancelled', 'timed_out'):
            payload = N.compose(self.run_data(conclusion), [
                {'name': 'compile <!channel>', 'conclusion': conclusion},
                {'name': 'good', 'conclusion': 'success'},
            ], 'C123')
            encoded = json.dumps(payload)
            self.assertIn('&lt;!channel&gt;', encoded)
            self.assertNotIn('<!channel>', encoded)
            self.assertIn(conclusion, payload['text'])

    def test_non_daily_running_or_missing_channel_rejected(self):
        for change, channel in [({'head_branch': 'develop'}, 'C123'), ({'status': 'in_progress'}, 'C123'), ({}, '')]:
            with self.assertRaises(ValueError):
                N.compose({**self.run_data('success'), **change}, [], channel)

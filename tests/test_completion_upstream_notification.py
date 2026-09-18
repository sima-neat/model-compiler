import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import notify_completed_build as N
from upstream_changes import digest


class CompletionTests(unittest.TestCase):
    def run_data(self, conclusion):
        return {'head_branch': 'daily', 'status': 'completed', 'repository': {'full_name': 'sima-neat/model-compiler'},
                'id': 123, 'run_number': 186, 'head_sha': 'b'*40, 'run_attempt': 1, 'conclusion': conclusion}

    def report(self):
        return {'schema_version': 1, 'baseline_sha': 'a'*40, 'components': [{
            'name': 'AFE', 'previous': '1', 'updated': '2', 'warnings': [],
            'commits': [{'subject': 'Fix <!channel>', 'sha': 'c'*40, 'url': 'https://example.invalid/commit'}]}]}

    def test_success_and_failure_use_one_top_level_message_with_thread_attachment(self):
        for conclusion in ['success', 'failure', 'cancelled']:
            with self.subTest(conclusion=conclusion), tempfile.TemporaryDirectory() as temp:
                api = Mock(return_value={'ok': True, 'ts': '123.456'})
                attach = Mock()
                N.notify(self.run_data(conclusion), [], 'C123', 'token', Path(temp), self.report(), api, attach)
                api.assert_called_once()
                self.assertEqual(api.call_args.args[0], 'chat.postMessage')
                payload = api.call_args.args[1]
                self.assertIn('Build #186', payload['text'])
                self.assertIn('&lt;!channel&gt;', json.dumps(payload))
                self.assertIn('AFE', payload['blocks'][-1]['text']['text'])
                self.assertEqual(attach.call_args.kwargs['thread_ts'], '123.456')
                self.assertTrue((Path(temp)/'upstream-changes.md').exists())

    def test_file_completion_targets_existing_message_thread(self):
        from send_upstream_changes import send
        api = Mock(side_effect=[{'upload_url': 'https://upload.invalid', 'file_id': 'F123'}, {'ok': True}])
        with tempfile.TemporaryDirectory() as temp:
            attachment = Path(temp)/'report.md'
            attachment.write_text('fixture report')
            send(self.report(), attachment, 'C123', 'token', 'https://example.invalid/run',
                 api=api, upload=Mock(), thread_ts='123.456')
        self.assertEqual(api.call_args.args[1]['thread_ts'], '123.456')
        self.assertEqual(api.call_args.args[1]['channel_id'], 'C123')
        self.assertNotIn('Candidate resolution', api.call_args.args[1]['initial_comment'])

    def test_missing_history_still_posts_result_without_false_no_changes(self):
        api, attach = Mock(return_value={'ts': '1'}), Mock()
        with tempfile.TemporaryDirectory() as temp:
            N.notify(self.run_data('failure'), [], 'C123', 'token', Path(temp), None, api, attach)
        self.assertIn('unavailable', api.call_args.args[1]['blocks'][-1]['text']['text'])
        attach.assert_not_called()

    def test_attachment_failure_updates_existing_message(self):
        api = Mock(return_value={'ts': '1'})
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(RuntimeError):
            N.notify(self.run_data('success'), [], 'C123', 'token', Path(temp), self.report(), api,
                     Mock(side_effect=RuntimeError('upload unavailable')))
        self.assertEqual([c.args[0] for c in api.call_args_list], ['chat.postMessage', 'chat.update'])
        self.assertIn('could not be uploaded', api.call_args.args[1]['blocks'][-1]['text']['text'])

    def test_safe_slack_attachment_failure_preserves_operation(self):
        api = Mock(return_value={'ts': '1'})
        error = N.SlackOperationError(
            'files.getUploadURLExternal: missing_scope (needed: files:write)')
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(
                N.SlackOperationError, 'attachment upload: files[.]getUploadURLExternal'):
            N.notify(self.run_data('success'), [], 'C123', 'token', Path(temp), self.report(), api,
                     Mock(side_effect=error))
        self.assertEqual([c.args[0] for c in api.call_args_list], ['chat.postMessage', 'chat.update'])

    def test_exact_commit_parent_and_manifest_select_private_record(self):
        updated, base = {'version': 2}, {'version': 1}
        report = {**self.report(), 'resolved_digest': digest(updated), 'baseline_digest': digest(base)}
        def github(endpoint):
            if '/commits/' in endpoint:
                return {'parents': [{'sha': 'a'*40}]}
            doc = updated if endpoint.endswith('b'*40) else base
            return {'content': base64.b64encode(json.dumps(doc).encode()).decode()}
        def execute(command, **kwargs):
            self.assertIn('model-compiler/build-records/comparisons/'+'a'*40+'/'+digest(updated)+'.json', command)
            Path(command[-1]).write_text(json.dumps(report))
            return subprocess.CompletedProcess(command, 0)
        with tempfile.TemporaryDirectory() as temp:
            actual = N.load_changes(self.run_data('success'), 'private', Path(temp), github, execute)
        self.assertEqual(actual, report)

    def test_merge_commit_cannot_guess_a_baseline(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            N.load_changes(self.run_data('success'), 'private', Path(temp),
                           lambda _: {'parents': [{'sha': 'a'*40}, {'sha': 'c'*40}]}, Mock())

    def test_wrong_manifest_report_is_rejected(self):
        def github(endpoint):
            return {'parents': [{'sha': 'a'*40}]} if '/commits/' in endpoint else {'content': base64.b64encode(b'{}').decode()}
        def execute(command, **kwargs):
            Path(command[-1]).write_text(json.dumps({**self.report(), 'resolved_digest': 'wrong'}))
            return subprocess.CompletedProcess(command, 0)
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            N.load_changes(self.run_data('success'), 'private', Path(temp), github, execute)

    def test_workflows_do_not_publish_engineering_details_to_github(self):
        worker=(ROOT/'.github/workflows/daily-build-notify-worker.yml').read_text()
        self.assertNotIn('upload-artifact', worker)
        self.assertNotIn('GITHUB_STEP_SUMMARY', worker)
        self.assertIn('ref: develop', worker)
        self.assertIn('Remove private notification files', worker)
        scanner=(ROOT/'.github/workflows/update-components-worker.yml').read_text()
        self.assertNotIn('SLACK_BOT_TOKEN', scanner)


if __name__ == '__main__':
    unittest.main()

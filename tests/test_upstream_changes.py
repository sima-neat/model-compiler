import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import upstream_changes as U
import send_upstream_changes as S


class ChangesTests(unittest.TestCase):
    def source(self, build):
        return {'dependency_overrides': {'sima-frontend': f'3.0.0.dev0+develop.{build}'},
                'component-updates': {'python-packages': {'sima-frontend': {
                    'version-prefix': '3.0.0.dev0+develop.', 'upstream': {
                        'jenkins-job': ['sima-ai', 'awesome-front-end'],
                        'bitbucket-repository': 'sima-ai/awesome-front-end'}}}}}

    def record(self, number, sha, commits=(), building=False):
        return {'number': number, 'building': building, 'result': 'SUCCESS',
                'artifacts': [{'fileName': f'sima_frontend-3.0.0.dev0+develop.{number}-py3-none-any.whl'}],
                'actions': [{'remoteUrls': ['git@bitbucket.org:sima-ai/awesome-front-end.git'],
                             'lastBuiltRevision': {'SHA1': sha}},
                            {'remoteUrls': ['https://bitbucket.org/sima-ai/sima-jenkins-lib.git'],
                             'lastBuiltRevision': {'SHA1': 'f'*40}}],
                'changeSets': [{'items': [{'commitId': c, 'msg': 'Private fix <!channel>',
                                           'author': {'fullName': 'Engineer'}} for c in commits]}]}

    def client(self, records):
        def get(url, tree):
            if 'builds[' in tree:
                return {'builds': records}
            raise ValueError('Jenkins HTTP 404')
        return Mock(get=Mock(side_effect=get))

    def test_toolchain_build_suffix_not_internal_revision(self):
        self.assertEqual(U.version_build('v3.0.0-3614-develop.458'), ('develop', 458))
        self.assertEqual(U.version_build('3.0.0.dev0+develop.2274'), ('develop', 2274))
        with self.assertRaises(ValueError):
            U.version_build('3.0.0')

    def test_deduplication_and_shared_library_attribution(self):
        records = [self.record(100, 'a'*40), self.record(101, 'b'*40, ['b'*40, 'f'*40]),
                   self.record(102, 'b'*40, ['b'*40])]
        with tempfile.TemporaryDirectory() as temp:
            report = U.collect(self.source(100), self.source(102), 'c'*40, Path(temp), self.client(records))
        row = report['components'][0]
        self.assertEqual(len(report['components']), 1)
        self.assertEqual(row['architectures'], ['aarch64', 'x86_64'])
        self.assertEqual([c['sha'] for c in row['commits']], ['b'*40])
        self.assertEqual(row['status'], 'partial')
        self.assertEqual(row['previous_revision'], 'a'*40)
        self.assertEqual(row['updated_revision'], 'b'*40)
        self.assertIn('unverified', U.markdown(report))

    def test_cache_survives_jenkins_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            U.collect(self.source(100), self.source(101), 'c'*40, cache,
                      self.client([self.record(100, 'a'*40), self.record(101, 'b'*40, ['b'*40])]))
            report = U.collect(self.source(100), self.source(102), 'c'*40, cache,
                               self.client([self.record(102, 'd'*40, ['d'*40])]))
            self.assertEqual(report['components'][0]['status'], 'complete')
            self.assertEqual(len(report['components'][0]['commits']), 2)

    def test_missing_builds_and_running_builds_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            report = U.collect(self.source(100), self.source(102), 'c'*40, Path(temp),
                               self.client([self.record(100, 'a'*40), self.record(102, 'b'*40, building=True)]))
        self.assertEqual(report['components'][0]['missing_builds'], [101, 102])
        self.assertEqual(report['components'][0]['status'], 'partial')

    def test_baseline_binding_and_stable_digest(self):
        doc = self.source(102)
        self.assertEqual(U.digest(doc), U.digest(dict(reversed(list(doc.items())))))
        report = {'schema_version': 1, 'baseline_sha': 'a'*40, 'resolved_digest': U.digest(doc)}
        U.validate(report, 'a'*40, doc)
        with self.assertRaises(ValueError):
            U.validate(report, 'b'*40, doc)
        with self.assertRaises(ValueError):
            U.validate(report, 'a'*40, self.source(103))

    def test_unavailable_credentials_do_not_echo_secret(self):
        with patch.dict('os.environ', {}, clear=True), tempfile.TemporaryDirectory() as temp:
            report = U.collect(self.source(100), self.source(101), 'c'*40, Path(temp), U.Jenkins())
        self.assertIn('Jenkins credentials unavailable', report['components'][0]['warnings'])

    def test_cross_branch_not_treated_as_numeric_build_range(self):
        before = self.source(100)
        before['dependency_overrides']['sima-frontend'] = '3.0.0.dev0+master.100'
        before['component-updates']['python-packages']['sima-frontend']['version-prefix'] = '3.0.0.dev0+master.'
        with tempfile.TemporaryDirectory() as temp:
            client = self.client([])
            report = U.collect(before, self.source(101), 'c'*40, Path(temp), client)
            client.get.assert_not_called()
        self.assertEqual(report['components'][0]['status'], 'unavailable')

    def test_all_current_components_have_valid_mapping(self):
        doc = json.loads((ROOT/'scripts/source.json').read_text())
        self.assertEqual(sum(len(g) for g in doc['component-updates'].values()), 11)
        for group in doc['component-updates'].values():
            for policy in group.values():
                self.assertTrue(U.job_url(policy['upstream'], 'develop').startswith(U.JENKINS))
        self.assertEqual(doc['component-updates']['python-packages']['mpk-parser']['upstream']['jenkins-job'], ['vdp', 'vdp-mpktool'])

    def test_slack_upload_attaches_report_and_escapes_mentions(self):
        report = {'baseline_sha': 'a'*40, 'components': [{'name': 'AFE', 'previous': '1', 'updated': '2',
                  'commits': [{'subject': '<!channel> ' + 'x'*300}] * 20, 'warnings': []}] * 30}
        self.assertLessEqual(len(S.snippet(report)), 1600)
        self.assertNotIn('<!channel>', S.snippet(report))
        with tempfile.TemporaryDirectory() as temp:
            attachment = Path(temp)/'report.md'; attachment.write_text('private details')
            api = Mock(side_effect=[{'upload_url': 'https://upload.invalid', 'file_id': 'F123'}, {'ok': True}])
            upload = Mock()
            S.send(report, attachment, 'C123', 'secret', 'https://github.com/example/run', api, upload)
            upload.assert_called_once_with('https://upload.invalid', b'private details')
            self.assertEqual(api.call_args.args[1]['files'][0]['id'], 'F123')
            self.assertEqual(api.call_args.args[1]['channel_id'], 'C123')

    def test_slack_snippet_formats_and_separates_components(self):
        report = {'baseline_sha': 'a'*40, 'components': [
            {'name': 'sima-frontend', 'previous': 'develop.2273', 'updated': 'develop.2276',
             'commits': [], 'warnings': []},
            {'name': 'sima-mlc', 'previous': 'develop.1102', 'updated': 'develop.1109',
             'commits': [{'subject': 'Add packed inverse'}], 'warnings': []},
        ]}

        text = S.snippet(report)

        self.assertIn('• `sima-frontend`: develop.2273 → *develop.2276*', text)
        self.assertIn(
            '• `sima-frontend`: develop.2273 → *develop.2276*\n\n'
            '• `sima-mlc`: develop.1102 → *develop.1109*', text)
        self.assertIn('\n  Add packed inverse', text)

    def test_workflow_does_not_publish_private_report(self):
        workflow = (ROOT/'.github/workflows/update-components-worker.yml').read_text()
        self.assertNotIn('Send private changeset attachment to Slack', workflow)
        self.assertIn('Remove private upstream files', workflow)
        self.assertNotIn('path: upstream', workflow)
        self.assertNotIn('upstream-changes.md" >>', workflow)
        self.assertNotIn('artifact_folder: upstream', workflow)


class PrivateCacheTests(unittest.TestCase):
    def checks(self, bucket, conditional=False):
        from subprocess import CompletedProcess
        block = {k: True for k in ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')}
        statement = {'Effect': 'Deny', 'Principal': {'Service': 'cloudfront.amazonaws.com'},
                     'Action': 's3:GetObject', 'Resource': f'arn:aws:s3:::{bucket}/model-compiler/build-records/*'}
        if conditional:
            statement['Condition'] = {'ArnEquals': {'AWS:SourceArn': 'some-distribution'}}
        return [CompletedProcess([], 0, json.dumps({'PublicAccessBlockConfiguration': block})),
                CompletedProcess([], 0, json.dumps({'Policy': json.dumps({'Statement': [statement]})})),
                CompletedProcess([], 0)]

    def test_shared_public_bucket_requires_unconditional_private_prefix_deny(self):
        import private_changelog_cache as C
        with patch.object(C.subprocess, 'run', side_effect=self.checks('bucket', True)) as run:
            with self.assertRaises(RuntimeError):
                C.sync('upload', 'bucket', Path('/tmp/test-history'), 'kms-key')
            self.assertEqual(run.call_count, 2)

    def test_private_prefix_upload_is_kms_encrypted_without_public_index(self):
        import private_changelog_cache as C
        with patch.object(C.subprocess, 'run', side_effect=self.checks('bucket')) as run:
            C.sync('upload', 'bucket', Path('/tmp/test-history'), 'kms-key')
            command = run.call_args.args[0]
            self.assertIn('s3://bucket/model-compiler/build-records/', command)
            self.assertIn('--sse-kms-key-id', command)
            self.assertIn('kms-key', command)
            self.assertNotIn('--delete', command)


if __name__ == "__main__":
    unittest.main()

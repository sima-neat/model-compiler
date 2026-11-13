"""Exercise the promotion gate against a real local Git repository."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/open-component-update-pr-worker.yml'


class PromotionGateTests(unittest.TestCase):
    def test_candidate_guards(self):
        text = WORKFLOW.read_text()
        block = text.split('      - name: Verify successful run is still current', 1)[1]
        block = block.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in block.splitlines())
        for case in ('valid', 'stale_tip', 'stale_base', 'empty', 'extra_file', 'wrong_channel'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                repo = root / 'repo'
                remote = root / 'remote.git'
                def git(*args):
                    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()
                subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
                repo.mkdir()
                git('init', '-b', 'develop')
                git('config', 'user.name', 'neat-releases[bot]')
                git('config', 'user.email', 'neat-releases[bot]@users.noreply.github.com')
                (repo / 'scripts').mkdir()
                manifest = repo / 'scripts/source.json'
                manifest.write_text('{}\n')
                git('add', '.')
                git('commit', '-m', 'base')
                git('remote', 'add', 'origin', str(remote))
                git('push', '-u', 'origin', 'develop')
                git('switch', '-c', 'daily-master')
                if case != 'empty':
                    manifest.write_text('{"updated": true}\n')
                if case == 'extra_file':
                    (repo / 'unexpected').write_text('code change')
                git('add', '.')
                channel = 'daily' if case == 'wrong_channel' else 'daily-master'
                git('commit', '--allow-empty', '-m', 'Update', '-m', f'Component-Updater: {channel}')
                sha = git('rev-parse', 'HEAD')
                git('push', 'origin', 'daily-master')
                if case == 'stale_base':
                    git('switch', 'develop')
                    git('commit', '--allow-empty', '-m', 'advance')
                    git('push', 'origin', 'develop')
                bin_dir = root / 'bin'
                bin_dir.mkdir()
                gh = bin_dir / 'gh'
                gh.write_text('#!/bin/sh\nprintf "%s\\n" "$MOCK_TIP"\n')
                gh.chmod(0o755)
                output = root / 'output'
                env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}',
                           TESTED_SHA=sha, MOCK_TIP='0'*40 if case == 'stale_tip' else sha,
                           GITHUB_OUTPUT=str(output), GITHUB_REPOSITORY='test/repo')
                result = subprocess.run(['bash', '-c', script], cwd=repo, env=env, capture_output=True, text=True)
                if case in ('extra_file', 'wrong_channel'):
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output.read_text().strip(), f'current={str(case == "valid").lower()}')


class PromotionHeadTests(unittest.TestCase):
    def test_pr_head_moves_only_when_a_tested_sha_is_promoted(self):
        block = WORKFLOW.read_text().split('      - name: Create or update pull request', 1)[1]
        script = '\n'.join(line[10:] for line in block.split('        run: |\n', 1)[1].splitlines())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            repo.mkdir()
            remote = root / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.DEVNULL).strip()
            git('init', '-b', 'develop')
            git('config', 'user.name', 'test')
            git('config', 'user.email', 'test@example.invalid')
            git('commit', '--allow-empty', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            git('remote', 'add', 'origin', str(remote))
            git('switch', '-c', 'daily-master')
            git('commit', '--allow-empty', '-m', 'tested candidate')
            tested = git('rev-parse', 'HEAD')
            git('push', 'origin', 'daily-master')
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            gh = bin_dir / 'gh'
            gh.write_text('#!/bin/sh\nprintf "%s\n" "$*" >> "$GH_CALLS"\n'
                          'if [ "$2" = list ]; then printf "%s" "$EXISTING_PR"; fi\n')
            gh.chmod(0o755)
            calls = root / 'gh-calls'
            env = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}',
                       GITHUB_REPOSITORY='test/repo', RUNNER_TEMP=str(root),
                       GH_CALLS=str(calls), EXISTING_PR='')
            def promote(sha):
                result = subprocess.run(['bash', '-c', script], cwd=repo,
                                        env=dict(env, TESTED_SHA=sha), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            def head():
                return git('ls-remote', 'origin', 'refs/heads/automation/promote-daily-master').split()[0]
            promote(tested)
            self.assertEqual(head(), tested)
            self.assertIn('pr create --repo test/repo --base develop --head automation/promote-daily-master', calls.read_text())
            # The scanner replaces its candidate while the next Build is pending
            # or failed. The open PR must still point to the previous tested SHA.
            git('reset', '--hard', base)
            git('commit', '--allow-empty', '-m', 'next candidate')
            candidate = git('rev-parse', 'HEAD')
            git('push', '--force', 'origin', 'daily-master')
            self.assertEqual(head(), tested)
            # Reprocessing the old successful SHA cannot accidentally push HEAD.
            env['EXISTING_PR'] = '123'
            promote(tested)
            self.assertEqual(head(), tested)
            # Once the next SHA succeeds, refresh the existing promotion PR.
            promote(candidate)
            self.assertEqual(head(), candidate)
            self.assertIn('pr edit 123 ', calls.read_text())


if __name__ == '__main__':
    unittest.main()

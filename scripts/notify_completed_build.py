#!/usr/bin/env python3
"""Post one build-completion message with private upstream changes in its thread."""
import argparse
import base64
import json
import os
import re
import subprocess
from pathlib import Path

from daily_build_notification import compose
from send_upstream_changes import SlackOperationError, send, slack_api, snippet
from upstream_changes import comparison_key, markdown, validate


def github_json(endpoint):
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Build metadata unavailable')
    return json.loads(result.stdout)


def load_changes(run, bucket, directory, github=github_json, execute=subprocess.run):
    """Use the immutable daily candidate's parent, never today's develop head."""
    sha = run['head_sha']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid build commit')
    repo = run['repository']['full_name']
    commit = github(f'repos/{repo}/commits/{sha}')
    parents = commit.get('parents', [])
    if len(parents) != 1:
        raise ValueError('No unique captured baseline for this build')
    baseline = parents[0]['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', baseline):
        raise ValueError('Invalid baseline commit')

    def manifest(ref):
        item = github(f'repos/{repo}/contents/scripts/source.json?ref={ref}')
        return json.loads(base64.b64decode(item['content']))

    updated, base = manifest(sha), manifest(baseline)
    path = directory / 'upstream-changes.json'
    key = 'model-compiler/build-records/' + comparison_key(baseline, updated)
    result = execute(['aws', 's3api', 'get-object', '--bucket', bucket, '--key', key, str(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise ValueError('Private changeset unavailable')
    report = json.loads(path.read_text())
    validate(report, baseline, updated, base)
    return report


def notify(run, jobs, channel, token, directory, report=None, api=slack_api, attach=send):
    changes = snippet(report) if report is not None else None
    if report is not None and report['components']:
        changes += '\nFull report attached in this message’s thread.'
    payload = compose(run, jobs, channel, changes)
    posted = api('chat.postMessage', payload, token)
    if report is not None and report['components']:
        attachment = directory / 'upstream-changes.md'
        attachment.write_text(markdown(report))
        url = f'https://github.com/{run["repository"]["full_name"]}/actions/runs/{run["id"]}'
        try:
            attach(report, attachment, channel, token, url, thread_ts=posted['ts'])
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            # Keep the build result and excerpt, and make attachment failure visible.
            payload['blocks'][-1]['text']['text'] = changes.replace(
                'Full report attached in this message’s thread.', 'Full report attachment could not be uploaded.')
            api('chat.update', {**payload, 'ts': posted['ts']}, token)
            if isinstance(exc, SlackOperationError):
                raise SlackOperationError(f'attachment upload: {exc}') from None
            raise RuntimeError('Build notification posted, but private attachment failed') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--jobs', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    run = json.loads(args.event.read_text())['workflow_run']
    if run['repository']['full_name'] != os.environ['GITHUB_REPOSITORY']:
        raise SystemExit('Unexpected build repository')
    jobs = [job for page in json.loads(args.jobs.read_text()) for job in page['jobs']]
    report = None
    if os.environ.get('HISTORY_BUCKET'):
        try:
            report = load_changes(run, os.environ['HISTORY_BUCKET'], args.directory)
        except (ValueError, KeyError, OSError, TypeError):
            # Build-result notifications must survive absent history and early failures.
            pass
    try:
        notify(run, jobs, os.environ['SLACK_CHANNEL_ID'], os.environ['SLACK_BOT_TOKEN'], args.directory, report)
    except SlackOperationError as exc:
        raise SystemExit(f'Build Slack notification failed at {exc}; private response omitted.') from None
    except (ValueError, RuntimeError, KeyError, OSError):
        raise SystemExit('Build Slack notification failed; private contents omitted from logs') from None


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Send private upstream changes to Slack without emitting engineering data to CI logs."""
import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def slack_api(method, payload, token):
    request = Request('https://slack.com/api/' + method, data=json.dumps(payload).encode(),
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (HTTPError, URLError, OSError, ValueError):
        raise RuntimeError('Slack request failed; private response omitted') from None
    if not result.get('ok'):
        raise RuntimeError('Slack API rejected the request; check bot scopes and channel membership')
    return result


def snippet(report, limit=1600):
    def escape(text):
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ').replace('\r', ' ')
    lines = ['*Resolved upstream changes versus develop*', f'Baseline: `{report["baseline_sha"][:12]}`']
    for index, row in enumerate(report['components']):
        if index:
            lines.append('')
        lines.append(
            f'• `{escape(row["name"])}`: {escape(row["previous"])} → *{escape(row["updated"])}*')
        lines.extend('  ' + escape(c['subject'])[:240] for c in row['commits'][:2])
        if row['warnings']:
            lines.append('  Incomplete evidence — see attached report.')
    if not report['components']:
        lines.append('No managed component version changes.')
    text = '\n'.join(lines)
    return text if len(text) <= limit else text[:limit - 40] + '\n… See attached report for all changes.'


def send(report, attachment, channel, token, run_url, api=slack_api, upload=None, thread_ts=None):
    if not token or not channel:
        raise ValueError('Slack token and channel must be configured')
    data = attachment.read_bytes()
    reservation = api('files.getUploadURLExternal', {'filename': 'upstream-changes.md', 'length': len(data)}, token)
    if upload is None:
        def upload(url, data):
            request = Request(url, data=data, headers={'Content-Type': 'application/octet-stream'})
            try:
                with urlopen(request, timeout=60) as response:
                    response.read()
            except (HTTPError, URLError, OSError):
                raise RuntimeError('Slack file upload failed; private response omitted') from None
    upload(reservation['upload_url'], data)
    completion = {
        'files': [{'id': reservation['file_id'], 'title': 'Model Compiler upstream changes'}],
        'channel_id': channel,
        'initial_comment': snippet(report) + f'\n<{run_url}|Component resolution workflow>\nCandidate resolution; this is not a successful build notification.',
    }
    if thread_ts:
        completion['thread_ts'] = thread_ts
        completion['initial_comment'] = 'Detailed upstream changes for this completed build.'
    api('files.completeUploadExternal', completion, token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--attachment', type=Path, required=True)
    parser.add_argument('--run-url', required=True)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text())
        if not report['components']:
            return
        send(report, args.attachment,
             os.environ.get('SLACK_CHANNEL_ID'), os.environ.get('SLACK_BOT_TOKEN'), args.run_url)
    except (RuntimeError, ValueError, OSError, KeyError):
        raise SystemExit('Private Slack notification failed; verify credentials, files:write scope, and channel access.') from None


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Send private upstream changes to Slack without emitting engineering data to CI logs."""
import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SlackOperationError(RuntimeError):
    """A safe-to-log Slack operation failure without response contents."""


def _safe_slack_value(value, fallback):
    value = str(value or '')
    return value if value and all(c.isalnum() or c in '._:-,' for c in value) else fallback


def slack_api(method, payload, token):
    if method in ('files.getUploadURLExternal', 'files.completeUploadExternal'):
        # Match Slack's SDK: file methods use form parameters, with the files
        # array serialized as JSON inside the completion form.
        fields = {key: json.dumps(value) if isinstance(value, (list, dict)) else value
                  for key, value in payload.items() if value is not None}
        data = urlencode(fields).encode()
        content_type = 'application/x-www-form-urlencoded'
    else:
        data = json.dumps(payload).encode()
        content_type = 'application/json'
    request = Request('https://slack.com/api/' + method, data=data,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': content_type})
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise SlackOperationError(f'{method}: HTTP {exc.code}') from None
    except (URLError, OSError, ValueError):
        raise SlackOperationError(f'{method}: transport or response error') from None
    if not result.get('ok'):
        error = _safe_slack_value(result.get('error'), 'unknown_error')
        detail = f'{method}: {error}'
        if error == 'missing_scope':
            needed = _safe_slack_value(result.get('needed'), 'unknown')
            detail += f' (needed: {needed})'
        raise SlackOperationError(detail)
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
            except HTTPError as exc:
                raise SlackOperationError(f'file upload: HTTP {exc.code}') from None
            except (URLError, OSError):
                raise SlackOperationError('file upload: transport error') from None
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
    except SlackOperationError as exc:
        raise SystemExit(f'Private Slack notification failed at {exc}; private response omitted.') from None
    except (RuntimeError, ValueError, OSError, KeyError):
        raise SystemExit('Private Slack notification failed; verify credentials, files:write scope, and channel access.') from None


if __name__ == '__main__':
    main()

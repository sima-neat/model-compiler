#!/usr/bin/env python3
"""Capture Jenkins evidence and compare exact, resolved component manifests."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from update_component_versions import collect_components

JENKINS = 'https://jenkins.eng.sima.ai/'
RECORD_TREE = 'number,building,result,timestamp,artifacts[fileName],actions[remoteUrls,lastBuiltRevision[SHA1]],changeSets[items[commitId,msg,author[fullName]]]'


def digest(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def comparison_key(base_sha, updated):
    if not re.fullmatch(r'[0-9a-f]{40}', base_sha):
        raise ValueError('Expected full baseline commit SHA')
    return f'comparisons/{base_sha}/{digest(updated)}.json'


def version_build(version):
    match = re.search(r'(?:\+|-)([A-Za-z][A-Za-z0-9_-]*)\.(\d+)$', version)
    if not match:
        raise ValueError('Version has no Jenkins branch/build suffix')
    return match[1], int(match[2])


def job_url(mapping, branch):
    parts = mapping['jenkins-job'] + [branch]
    if not parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) or p in ('.', '..') for p in parts):
        raise ValueError('Unsupported Jenkins job path')
    return JENKINS + ''.join(f'job/{quote(p, safe="")}/' for p in parts)


def repository(remote):
    return re.sub(r'^.*bitbucket.org[:/]', '', remote).removesuffix('.git')


class Jenkins:
    def __init__(self):
        user, token = os.environ.get('JENKINS_USERNAME'), os.environ.get('JENKINS_API_TOKEN')
        self.auth = base64.b64encode(f'{user}:{token}'.encode()).decode() if user and token else None

    def get(self, url, tree):
        if not self.auth:
            raise ValueError('Jenkins credentials unavailable')
        request = Request(url + 'api/json?' + urlencode({'tree': tree}),
                          headers={'Authorization': 'Basic ' + self.auth})
        try:
            with urlopen(request, timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            raise ValueError(f'Jenkins HTTP {error.code}') from None
        except (URLError, TimeoutError, OSError, json.JSONDecodeError):
            raise ValueError('Jenkins request failed') from None


def records_for(client, cache, mapping, branch, first, last):
    url = job_url(mapping, branch)
    directory = cache / 'records' / Path(*mapping['jenkins-job']) / branch
    directory.mkdir(parents=True, exist_ok=True)
    records = {}
    for path in directory.glob('*.json'):
        record = json.loads(path.read_text())
        if record.get('job_url') == url:
            records[record['number']] = record
    warnings = []
    try:
        recent = client.get(url, f'builds[{RECORD_TREE}]{{0,100}}')['builds']
    except ValueError as error:
        recent = []
        warnings.append(str(error))
    # Recover boundary revisions directly if they remain outside the list window.
    known = {r['number'] for r in recent} | records.keys()
    for number in {first, last} - known:
        try:
            recent.append(client.get(f'{url}{number}/', RECORD_TREE))
        except ValueError:
            pass
    for raw in recent:
        if raw.get('building', True):
            continue  # Never freeze a partial running-build changelog.
        record = {k: raw.get(k) for k in ('number', 'result', 'timestamp', 'artifacts', 'actions', 'changeSets')}
        record['job_url'] = url
        # Strip unrelated action metadata; retain every SCM so shared-library
        # commits cannot accidentally be labeled component commits.
        record['actions'] = [a for a in (record['actions'] or []) if a.get('remoteUrls')]
        path = directory / f'{record["number"]}.json'
        if not path.exists():
            path.write_text(json.dumps(record, indent=2) + '\n')
        records[record['number']] = json.loads(path.read_text())
    return records, warnings


def revision(record, repo):
    revisions = {a.get('lastBuiltRevision', {}).get('SHA1') for a in (record or {}).get('actions', [])
                 if any(repository(url) == repo for url in a.get('remoteUrls', []))}
    revisions.discard(None)
    return next(iter(revisions)) if len(revisions) == 1 else None


def components(doc):
    return {(c.kind, c.name, arch): c.current for arch in ('aarch64', 'x86_64')
            for c in collect_components(doc, arch)}


def collect(base, updated, base_sha, cache, client):
    report = {'schema_version': 1, 'baseline_sha': base_sha, 'baseline_digest': digest(base),
              'resolved_digest': digest(updated), 'components': []}
    before = components(base)
    groups = {}
    for (kind, name, arch), new in components(updated).items():
        old = before.get((kind, name, arch))
        groups.setdefault((kind, name, old, new), []).append(arch)
    for (kind, name, old, new), arches in sorted(groups.items()):
        mapping = updated.get('component-updates', {}).get(kind + '-packages', {}).get(name, {}).get('upstream')
        row = {'name': name, 'architectures': arches, 'previous': old, 'updated': new, 'commits': [], 'unattributed_commits': [], 'warnings': []}
        try:
            if not mapping:
                raise ValueError('Upstream mapping unavailable')
            branch, last = version_build(new)
            old_branch, first = version_build(old or '')
            if branch != old_branch or first > last:
                raise ValueError('Cross-branch or reverse-build comparison requires Git ancestry evidence')
            row['job_url'] = job_url(mapping, branch)
            row['repository'] = mapping['bitbucket-repository']
            records, warnings = records_for(client, cache, mapping, branch, first, last)
            row['warnings'] += warnings
            row['previous_revision'] = revision(records.get(first), row['repository'])
            row['updated_revision'] = revision(records.get(last), row['repository'])
            missing = [n for n in range(first + 1, last + 1) if n not in records]
            selected_record = records.get(last)
            artifact_name = name.rsplit('/', 1)[-1].replace('-', '_') if kind == 'python' else name.rsplit('/', 1)[-1]
            if selected_record and not any(a.get('fileName', '').startswith(f'{artifact_name}-{new}-')
                                           for a in selected_record.get('artifacts') or []):
                row['warnings'].append('Selected artifact not verified in Jenkins archived artifacts')
            row['missing_builds'] = missing
            if missing:
                row['warnings'].append(f'History incomplete: {len(missing)} build records unavailable')
            if not row['previous_revision'] or not row['updated_revision']:
                row['warnings'].append('Boundary source revision unavailable')
            # Jenkins changeSets do not label their SCM. Only include entries
            # when all commit IDs can be attributed to the component checkout:
            # singleton entries matching a component revision are unambiguous.
            component_shas = {revision(r, row['repository']) for r in records.values()}
            seen = set()
            unattributed = 0
            for number in sorted(records):
                if not first < number <= last:
                    continue
                for changes in records[number].get('changeSets') or []:
                    for item in changes.get('items', []):
                        sha = item.get('commitId', '')
                        if sha not in component_shas or not re.fullmatch(r'[0-9a-f]{40}', sha):
                            unattributed += 1
                            row['unattributed_commits'].append({'sha': sha, 'subject': item.get('msg', ''), 'build': number})
                            continue
                        if sha not in seen:
                            seen.add(sha)
                            row['commits'].append({'sha': sha, 'subject': item.get('msg', ''),
                                                   'author': item.get('author', {}).get('fullName', ''),
                                                   'build': number,
                                                   'url': f'https://bitbucket.org/{row["repository"]}/commits/{sha}'})
            if (row['previous_revision'] and row['updated_revision']
                    and row['previous_revision'] != row['updated_revision']
                    and row['updated_revision'] not in seen):
                row['warnings'].append('Source revisions differ but the target commit is absent from the verified changelog')
            if unattributed:
                row['warnings'].append(f'{unattributed} changelog entries lack verified component SCM attribution; raw records retained')
            row['status'] = 'partial' if row['warnings'] else 'complete'
        except ValueError as error:
            row['status'] = 'unavailable'
            row['warnings'].append(str(error))
        if old != new:
            report['components'].append(row)
    key = comparison_key(base_sha, updated)
    path = cache / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    return report


def markdown(report):
    def safe(text):
        return html.escape(str(text)).replace('\n', ' ').replace('\r', ' ').replace('|', '&#124;')
    lines = ['## Upstream changes versus develop', '', f'Baseline: `{report["baseline_sha"]}`', '']
    for row in report['components']:
        lines += [f'### {safe(row["name"])}: {safe(row["previous"])} → {safe(row["updated"])}', '']
        if row.get('job_url'):
            lines += [f'[Jenkins builds]({row["job_url"]})', '']
        lines += [f'- {safe(c["subject"])} ([{c["sha"][:10]}]({c["url"]}))' for c in row['commits']]
        if row.get('unattributed_commits'):
            lines += ['', 'Other Jenkins SCM entries (repository attribution unverified):', '']
            lines += [f'- {safe(c["subject"])} ({safe(c["sha"][:10])}, build {c["build"]})' for c in row['unattributed_commits']]
        lines += [f'- **{safe(w)}**' for w in row['warnings']]
        if not row['commits'] and not row['warnings']:
            lines.append('No component commits recorded in this build interval (artifact rebuild).')
        lines.append('')
    if not report['components']:
        lines.append('No managed component version changes.')
    return '\n'.join(lines) + '\n'


def validate(report, base_sha, updated, base=None):
    if (report.get('schema_version') != 1 or report.get('baseline_sha') != base_sha
            or report.get('resolved_digest') != digest(updated)
            or (base is not None and report.get('baseline_digest') != digest(base))):
        raise ValueError('Changeset does not match the baseline and resolved manifest')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--updated', type=Path, required=True)
    parser.add_argument('--base-sha', required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = collect(json.loads(args.base.read_text()), json.loads(args.updated.read_text()),
                     args.base_sha, args.cache, Jenkins())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'upstream-changes.json').write_text(json.dumps(report, indent=2) + '\n')
    (args.output / 'upstream-changes.md').write_text(markdown(report))


if __name__ == '__main__':
    main()

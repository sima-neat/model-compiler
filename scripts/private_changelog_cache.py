#!/usr/bin/env python3
"""Synchronize optional private Vulcan history, never a public artifact prefix."""
import argparse
import subprocess
from pathlib import Path


def sync(mode, bucket, directory, kms_key):
    # Fail closed if S3's account/bucket policies are not confirmed to block public access.
    # A shared artifact bucket is allowed only with an explicit edge-read deny.
    import json
    checks = subprocess.run(['aws', 's3api', 'get-public-access-block', '--bucket', bucket],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        policy = json.loads(checks.stdout)['PublicAccessBlockConfiguration']
        if not all(policy.get(k) is True for k in ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')):
            raise ValueError()
    except (ValueError, KeyError):
        raise RuntimeError('Private history bucket must enable all S3 public access blocks') from None
    raw_policy = subprocess.run(['aws', 's3api', 'get-bucket-policy', '--bucket', bucket],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        statements = json.loads(json.loads(raw_policy.stdout)['Policy'])['Statement']
        protected = any(
            s.get('Effect') == 'Deny' and not s.get('Condition')
            and s.get('Principal', {}).get('Service') in ('cloudfront.amazonaws.com', ['cloudfront.amazonaws.com'])
            and 's3:GetObject' in ([s.get('Action')] if isinstance(s.get('Action'), str) else s.get('Action', []))
            and f'arn:aws:s3:::{bucket}/model-compiler/build-records/*' in
                ([s.get('Resource')] if isinstance(s.get('Resource'), str) else s.get('Resource', []))
            for s in statements if isinstance(s.get('Principal'), dict))
        if not protected:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('Private build-records prefix must deny all CloudFront reads') from None
    remote = f's3://{bucket}/model-compiler/build-records/' 
    source, target = (remote, str(directory)) if mode == 'download' else (str(directory), remote)
    flags = ['--sse', 'aws:kms', '--sse-kms-key-id', kms_key] if mode == 'upload' else []
    result = subprocess.run(['aws', 's3', 'sync', source, target, '--exclude', '*', '--include', '*.json', '--only-show-errors', *flags],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise RuntimeError('Private history synchronization failed; storage details omitted')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['download', 'upload'])
    p.add_argument('--bucket', required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--kms-key', required=True)
    a = p.parse_args()
    try:
        sync(a.mode, a.bucket, a.directory, a.kms_key)
    except (RuntimeError, OSError) as e:
        raise SystemExit('Private history synchronization failed. Check bucket privacy, access policy and AWS CLI availability.') from None

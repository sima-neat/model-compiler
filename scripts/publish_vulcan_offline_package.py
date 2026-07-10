#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def clean_path_part(raw: str, fallback: str) -> str:
    value = raw.strip() or fallback
    value = value.replace("/", "-")
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip(".-")
    if not value:
        raise SystemExit(f"Invalid path component: {raw!r}")
    return value


def branch_key(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise SystemExit("Branch name is empty.")
    return quote(value, safe="")


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def s3_cp_args(sse_kms_key_id: str) -> list[str]:
    args = ["--sse", "aws:kms"]
    if sse_kms_key_id:
        args.extend(["--sse-kms-key-id", sse_kms_key_id])
    return args


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a Model Compiler offline package to a nested Vulcan S3 folder."
    )
    parser.add_argument("--download-path", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--target-arch", required=True, choices=["amd64", "arm64"])
    parser.add_argument("--sse-kms-key-id", default="")
    parser.add_argument("--cloudfront-distribution-id", default="")
    parser.add_argument("--github-repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--github-ref-name", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("--github-head-ref", default=os.environ.get("GITHUB_HEAD_REF", ""))
    parser.add_argument("--github-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--github-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--github-run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    args = parser.parse_args()

    required = {
        "github-repository": args.github_repository,
        "github-ref-name": args.github_ref_name,
        "github-sha": args.github_sha,
        "github-run-id": args.github_run_id,
        "github-run-attempt": args.github_run_attempt,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing required GitHub context: {', '.join(missing)}")

    _, repo_name_from_context = args.github_repository.split("/", 1)
    repo_name = clean_path_part(repo_name_from_context, "repository")
    branch_raw = args.github_head_ref or args.github_ref_name
    encoded_branch_key = branch_key(branch_raw)
    short_commit = args.github_sha[:12]
    target_arch = clean_path_part(args.target_arch, "arch")
    prefix = f"{repo_name}/{encoded_branch_key}/{short_commit}/{target_arch}/offline"

    download_path = Path(args.download_path)
    files = [p for p in sorted(download_path.glob("*")) if p.is_file()]
    if len(files) < 2:
        raise SystemExit(f"Expected at least 2 offline package files, found {len(files)}")

    manifest_entries = []
    for path in files:
        rel_key = path.name
        target = f"s3://{args.bucket}/{prefix}/{rel_key}"
        run("aws", "s3", "cp", str(path), target, *s3_cp_args(args.sse_kms_key_id))
        manifest_entries.append(
            {
                "path": rel_key,
                "s3_key": f"{prefix}/{rel_key}",
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    manifest = {
        "repository": args.github_repository,
        "repository_key": repo_name,
        "branch": branch_raw,
        "branch_key": encoded_branch_key,
        "commit_folder": short_commit,
        "artifact_folder": f"{target_arch}/offline",
        "commit": args.github_sha,
        "run_id": args.github_run_id,
        "run_attempt": args.github_run_attempt,
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": manifest_entries,
    }
    manifest_path = Path("_vulcan/offline-manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    run(
        "aws",
        "s3",
        "cp",
        str(manifest_path),
        f"s3://{args.bucket}/{prefix}/manifest.json",
        "--content-type",
        "application/json",
        *s3_cp_args(args.sse_kms_key_id),
    )

    if args.cloudfront_distribution_id:
        run(
            "aws",
            "cloudfront",
            "create-invalidation",
            "--distribution-id",
            args.cloudfront_distribution_id,
            "--paths",
            f"/{prefix}/*",
        )

    print(f"published_count={len(files)}")
    print(f"published_prefix=s3://{args.bucket}/{prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

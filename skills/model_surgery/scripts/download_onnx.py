#!/usr/bin/env python3
"""Download an ONNX model from a direct URL or Hugging Face Hub."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlretrieve


def infer_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    return name or "model.onnx"


def download_from_url(url: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(url, output)
    return output


def download_from_huggingface(repo_id: str, filename: str, output_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download

    output_dir.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(output_dir))
    return Path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ONNX from URL or Hugging Face Hub.")
    parser.add_argument("--url", type=str, help="Direct ONNX URL")
    parser.add_argument("--hf-repo", type=str, help="HF repo id, e.g. org/repo")
    parser.add_argument("--hf-file", type=str, help="HF file path, e.g. model.onnx")
    parser.add_argument("--output", type=Path, help="Output path for direct URL downloads")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Destination directory for downloaded files",
    )
    args = parser.parse_args()

    if args.url:
        output = args.output or (args.output_dir / infer_name_from_url(args.url))
        saved = download_from_url(args.url, output)
    elif args.hf_repo and args.hf_file:
        saved = download_from_huggingface(args.hf_repo, args.hf_file, args.output_dir)
    else:
        parser.error("Provide either --url OR both --hf-repo and --hf-file.")
        return 2

    print(saved.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
